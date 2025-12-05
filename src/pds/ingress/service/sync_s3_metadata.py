#!/usr/bin/env python3
"""
===================
sync_s3_metadata.py
===================

Lambda function which updates existing objects in S3 with metdata typically
added by either the DUM ingress client or the rclone utility.
"""
import argparse
import calendar
import concurrent.futures
import logging
import os
from datetime import datetime
from datetime import timezone

import boto3

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

s3 = boto3.client("s3")
paginator = s3.get_paginator("list_objects_v2")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(LOG_LEVELS.get(LOG_LEVEL.lower(), logging.INFO))


def update_last_modified_metadata(key, head_metadata):
    """
    Updates an S3 object's metadata dictionary to include fields added during
    rclone uploads.

    Parameters
    ----------
    key : str
        S3 object key. Used for logging.
    head_metadata : dict
        Dictionary of metadata for the S3 object as returned by head_object().

    Returns
    -------
    updated_metadata : dict
        Updated custom metadata dictionary including 'last_modified' and 'mtime' fields.

    """
    updated_metadata = head_metadata.get("Metadata", {}).copy()

    last_modified = updated_metadata.get("last_modified")
    mtime = updated_metadata.get("mtime")

    if not last_modified:
        # Use the mtime assigned by rclone
        if mtime:
            last_modified = datetime.fromtimestamp(float(mtime), tz=timezone.utc).isoformat()
        # Fall back to the S3 LastModified value
        else:
            last_modified = head_metadata["LastModified"].replace(tzinfo=timezone.utc).isoformat()

        updated_metadata["last_modified"] = last_modified
        logger.info(
            "Updating object %s with updated_metadata['last_modified']=%s", key, str(updated_metadata["last_modified"])
        )

    if not mtime:
        # Convert ISO 8601 to epoch time for the mtime field
        epoch_last_modified = calendar.timegm(datetime.fromisoformat(updated_metadata["last_modified"]).timetuple())
        updated_metadata["mtime"] = str(epoch_last_modified)
        logger.info("Updating object %s with updated_metadata['mtime']=%s", key, str(updated_metadata["mtime"]))

    return updated_metadata


def update_md5_metadata(key, head_metadata):
    """
    Updates an S3 object's metadata dictionary to include the 'md5' field.

    Parameters
    ----------
    key : str
        S3 object key. Used for logging.
    head_metadata : dict
        Dictionary of metadata for the S3 object as returned by head_object().

    Returns
    -------
    updated_metadata : dict
        Updated custom metadata dictionary including 'md5' field.

    """
    updated_metadata = head_metadata.get("Metadata", {}).copy()

    try:
        # Use the Etag as the MD5 checksum, stripping any surrounding quotes
        # Note this is only valid for non-multipart uploads
        etag = head_metadata["ETag"].strip('"')
        updated_metadata["md5"] = etag
        logger.info("Updating object %s with updated_metadata['md5']=%s", key, str(updated_metadata["md5"]))
    except Exception as err:
        logger.error("Failed to retrieve ETag for object %s, reason: %s", key, str(err))

    return updated_metadata


def process_s3_object(bucket_name, key):
    """
    Processes a single S3 object to see if it requires metadata updates.

    Parameters
    ----------
    bucket_name : str
        Name of the S3 bucket.
    key : str
        S3 object key.

    Returns
    -------
    key : str
        The S3 object key.
    status : str
        Status of the operation: 'updated', 'skipped', or 'failed'.

    """
    try:
        update_made = False
        head_metadata = s3.head_object(Bucket=bucket_name, Key=key)
        metadata_dict = head_metadata.get("Metadata", {})

        if "mtime" not in metadata_dict or "last_modified" not in metadata_dict:
            head_metadata["Metadata"] = update_last_modified_metadata(key, head_metadata)
            update_made = True

        if "md5" not in metadata_dict:
            head_metadata["Metadata"] = update_md5_metadata(key, head_metadata)
            update_made = True

        if update_made:
            s3.copy_object(
                Bucket=bucket_name,
                Key=key,
                CopySource={"Bucket": bucket_name, "Key": key},
                Metadata=head_metadata["Metadata"],
                MetadataDirective="REPLACE",
            )
            return key, "updated"
        else:
            logger.debug("Skipping object %s, no updates required", key)
            return key, "skipped"
    except Exception as err:
        logger.error("Failed to update metadata for object %s, reason: %s", key, str(err))
        return key, "failed"


def _process_batch(bucket_name, keys_batch, num_workers, context, timeout_buffer_ms):
    """
    Process a batch of S3 object keys.

    Parameters
    ----------
    bucket_name : str
        Name of the S3 bucket.
    keys_batch : list
        List of S3 object keys to process.
    num_workers : int
        Number of worker threads to use.
    context : object
        Lambda context for timeout checking.
    timeout_buffer_ms : int
        Buffer time in milliseconds before timeout.

    Returns
    -------
    updated : list
        List of keys that were updated.
    skipped : list
        List of keys that were skipped.
    failed : list
        List of keys that failed.

    """
    # Use sets internally to guarantee uniqueness, then convert back to lists for callers
    updated = set()
    skipped = set()
    failed = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        # Submit all tasks for this batch
        future_to_key = {executor.submit(process_s3_object, bucket_name, key): key for key in keys_batch}

        for future in concurrent.futures.as_completed(future_to_key):
            # Check Lambda remaining time
            if context and context.get_remaining_time_in_millis() < timeout_buffer_ms:
                logger.warning("Approaching Lambda timeout, cancelling remaining tasks in batch.")
                for f in future_to_key:
                    f.cancel()
                break

            key = future_to_key[future]
            try:
                result_key, status = future.result()
                if status == "updated":
                    updated.add(result_key)
                elif status == "skipped":
                    skipped.add(result_key)
                else:
                    failed.add(result_key)
            except Exception as err:
                logger.error("Exception processing key %s: %s", key, str(err))
                failed.add(key)

    # Convert back to lists to preserve the public API
    return list(updated), list(skipped), list(failed)


def update_s3_objects_metadata(context, bucket_name, prefix=None, timeout_buffer_ms=5000, batch_size=1000):
    """
    Recursively iterates over all objects in an S3 bucket and updates their
    metadata to include fields added during rclone uploads, if not already present.

    Processes objects in batches to avoid memory exhaustion.

    Parameters
    ----------
    context : object, optional
        Object containing details of the AWS context in which the Lambda was
        invoked. Used to check remaining execution time. If None, no time
        checks are performed.
    bucket_name : str
        Name of the S3 bucket.
    prefix : str, optional
        S3 key path to start traversal from.
    timeout_buffer_ms : int, optional
        Buffer time in milliseconds to stop processing before Lambda timeout.
    batch_size : int, optional
        Number of objects to process in each batch. Defaults to 1000.

    Returns
    -------
    updated : list
        List of S3 object keys that were updated.
    skipped : list
        List of S3 object keys that were skipped because they already had the
        required metadata.
    failed : list
        List of S3 object keys that failed to be updated due to errors.
    unprocessed : list
        List of S3 object keys that were not processed due to Lambda timeout.

    """
    logger.info("Starting S3 metadata update service")

    pagination_params = {"Bucket": bucket_name}

    if prefix:
        pagination_params["Prefix"] = prefix

    updated = []
    skipped = []
    failed = []
    unprocessed = []

    num_cores = max(os.cpu_count(), 1)
    logger.info("Available CPU cores: %d", num_cores)
    logger.info("Processing in batches of %d objects to avoid memory issues", batch_size)

    # Process objects in batches as they're discovered
    current_batch = []
    total_processed = 0
    should_stop = False

    logger.info("Indexing and processing objects in bucket %s with prefix %s", bucket_name, prefix or "")

    for page in paginator.paginate(**pagination_params):
        if should_stop:
            # Add remaining keys from current page to unprocessed
            for obj in page.get("Contents", []):
                if obj["Key"] not in current_batch:
                    unprocessed.append(obj["Key"])
            break

        for obj in page.get("Contents", []):
            key = obj["Key"]
            current_batch.append(key)

            # Process batch when it reaches the batch size
            if len(current_batch) >= batch_size:
                batch_updated, batch_skipped, batch_failed = _process_batch(
                    bucket_name, current_batch, num_cores, context, timeout_buffer_ms
                )
                updated.extend(batch_updated)
                skipped.extend(batch_skipped)
                failed.extend(batch_failed)
                total_processed += len(current_batch)
                logger.info(
                    "Processed batch: %d objects (total: %d, updated: %d, skipped: %d, failed: %d)",
                    len(current_batch),
                    total_processed,
                    len(updated),
                    len(skipped),
                    len(failed),
                )
                current_batch = []

                # Check if we should stop due to timeout
                if context and context.get_remaining_time_in_millis() < timeout_buffer_ms:
                    logger.warning("Approaching Lambda timeout, stopping processing.")
                    should_stop = True
                    # Add remaining keys from current page to unprocessed
                    for remaining_obj in page.get("Contents", []):
                        if remaining_obj["Key"] not in current_batch:
                            unprocessed.append(remaining_obj["Key"])
                    break

    # Process any remaining objects in the final batch
    if current_batch and not should_stop:
        batch_updated, batch_skipped, batch_failed = _process_batch(
            bucket_name, current_batch, num_cores, context, timeout_buffer_ms
        )
        updated.extend(batch_updated)
        skipped.extend(batch_skipped)
        failed.extend(batch_failed)
        total_processed += len(current_batch)
        logger.info("Processed final batch of %d objects", len(current_batch))
    elif current_batch:
        # Add remaining batch to unprocessed if we stopped early
        unprocessed.extend(current_batch)

    logger.info(
        "Processing complete. Total processed: %d (updated: %d, skipped: %d, failed: %d, unprocessed: %d)",
        total_processed,
        len(updated),
        len(skipped),
        len(failed),
        len(unprocessed),
    )

    return updated, skipped, failed, unprocessed


def lambda_handler(event, context):
    """
    Entrypoint for this Lambda function. Derives the S3 bucket name and prefix
    from the event, then iterates over all objects within the location to update
    their metadata for compliance with rclone-uploaded objects.

    Parameters
    ----------
    event : dict
        Dictionary containing details of the event that triggered the Lambda.
    context : object, optional
        Object containing details of the AWS context in which the Lambda was
        invoked. Used to check remaining execution time. If None, no time
        checks are performed.

    Returns
    -------
    response : dict
        JSON-compliant dictionary containing the results of the request.

    """
    bucket_name = event["bucket_name"]
    prefix = event.get("prefix", None)
    batch_size = int(event.get("batch_size", os.getenv("BATCH_SIZE", "1000")))

    updated, skipped, failed, unprocessed = update_s3_objects_metadata(
        context, bucket_name, prefix, batch_size=batch_size
    )

    result = {
        "statusCode": 200,
        "body": {
            "message": "S3 Object Metadata update complete",
            "bucket_name": bucket_name,
            "prefix": prefix,
            "processed": len(updated) + len(skipped) + len(failed),
            "unprocessed": len(unprocessed),
            "updated": len(updated),
            "skipped": len(skipped),
            "failed": len(failed),
        },
    }

    logger.info("S3 Object Metadata update result:\n%s", result)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Invoke S3 metadata sync outside of Lambda.")
    parser.add_argument("bucket", help="S3 bucket name")
    parser.add_argument("prefix", help="S3 prefix")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch size for processing (default: %(default)d)",
    )
    args = parser.parse_args()

    event = {"bucket_name": args.bucket, "prefix": args.prefix, "batch_size": args.batch_size}
    lambda_handler(event, None)

"""
===================
sync_s3_metadata.py
===================

Lambda function which updates existing objects in S3 with metdata typically
added by the rclone utility.
"""
import calendar
import concurrent.futures
import logging
import os
from datetime import datetime

import boto3


s3 = boto3.client("s3")
paginator = s3.get_paginator("list_objects_v2")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def update_s3_object_metadata(metadata_dict):
    """
    Updates an S3 object's metadata dictionary to include fields added during
    rclone uploads.

    Parameters
    ----------
    metadata_dict : dict
        Dictionary of existing metadata for an S3 object. Must include
        'last_modified' field.

    Returns
    -------
    updated_metadata : dict
        Updated metadata dictionary including 'mtime' field.

    """
    last_modified = metadata_dict["last_modified"]

    epoch_last_modified = calendar.timegm(datetime.fromisoformat(last_modified).timetuple())

    updated_metadata = metadata_dict.copy()
    updated_metadata["mtime"] = str(epoch_last_modified)

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
        head = s3.head_object(Bucket=bucket_name, Key=key)
        metadata_dict = head.get("Metadata", {})

        if "mtime" in metadata_dict:
            logger.debug(f"Object {key} already has required metadata. Skipping.")
            return key, "skipped"

        try:
            updated_metadata = update_s3_object_metadata(metadata_dict)
        except KeyError as err:
            logger.error(f"Missing expected metadata key for object {key}: {err}")
            return key, "failed"

        logger.debug(f"Updating object {key} with {updated_metadata['mtime']=}")

        s3.copy_object(
            Bucket=bucket_name,
            Key=key,
            CopySource={"Bucket": bucket_name, "Key": key},
            Metadata=updated_metadata,
            MetadataDirective="REPLACE",
        )
        return key, "updated"
    except Exception as err:
        logger.error(f"Failed to update metadata for object {key}, reason: {err}")
        return key, "failed"


def update_s3_objects_metadata(context, bucket_name, prefix=None, timeout_buffer_ms=5000):
    """
    Recursively iterates over all objects in an S3 bucket and updates their
    metadata to include fields added during rclone uploads, if not already present.

    Parameters
    ----------
    context : object
        Object containing details of the AWS context in which the Lambda was
        invoked.
    bucket_name : str
        Name of the S3 bucket.
    prefix : str, optional
        S3 key path to start traversal from.
    timeout_buffer_ms : int, optional
        Buffer time in milliseconds to stop processing before Lambda timeout.

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
    pagination_params = {"Bucket": bucket_name}

    if prefix:
        pagination_params["Prefix"] = prefix

    updated = []
    skipped = []
    failed = []
    unprocessed = []

    keys = []

    for page in paginator.paginate(**pagination_params):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
            unprocessed.append(obj["Key"])

    num_cores = max(os.cpu_count(), 1)

    logger.info(f"Available CPU cores: {num_cores}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
        futures = [executor.submit(process_s3_object, bucket_name, key) for key in keys]

        for future in concurrent.futures.as_completed(futures):
            # Check Lambda remaining time
            if context.get_remaining_time_in_millis() < timeout_buffer_ms:
                logger.warning("Approaching Lambda timeout, cancelling remaining tasks.")
                for f in futures:
                    f.cancel()
                break

            key, status = future.result()

            if status == "updated":
                updated.append(key)
            elif status == "skipped":
                skipped.append(key)
            else:
                failed.append(key)

            unprocessed.remove(key)

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
    context : object
        Object containing details of the AWS context in which the Lambda was
        invoked.

    Returns
    -------
    response : dict
        JSON-compliant dictionary containing the results of the request.

    """
    bucket_name = event["bucket_name"]
    prefix = event.get("prefix", None)

    updated, skipped, failed, unprocessed = update_s3_objects_metadata(context, bucket_name, prefix)

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

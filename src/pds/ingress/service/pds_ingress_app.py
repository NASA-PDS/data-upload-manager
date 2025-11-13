"""
==================
pds_ingress_app.py
==================

Lambda function which acts as the PDS Ingress Service, mapping local file paths
to their destinations in S3.
"""
import base64
import concurrent.futures
import json
import logging
import os
from datetime import datetime
from datetime import timezone
from http import HTTPStatus
from math import ceil
from os.path import join

import boto3
import botocore
from botocore.exceptions import ClientError

# When deployed to AWS, these imports need to absolute
try:
    from util.config_util import bucket_for_path
    from util.config_util import initialize_bucket_map
    from util.log_util import LOG_LEVELS
    from util.log_util import SingleLogFilter
# When running the unit tests, these imports need to be relative
except ModuleNotFoundError:
    from .util.config_util import bucket_for_path
    from .util.config_util import initialize_bucket_map
    from .util.log_util import LOG_LEVELS
    from .util.log_util import SingleLogFilter

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger = logging.getLogger()
logger.setLevel(LOG_LEVELS.get(LOG_LEVEL.lower(), logging.INFO))
logger.addFilter(SingleLogFilter())

logger.info("Loading function PDS Ingress Service")

if os.getenv("ENDPOINT_URL", None):
    logger.info("Using S3 endpoint URL from envvar: %s", os.environ["ENDPOINT_URL"])
    s3_client = boto3.client("s3", endpoint_url=os.environ["ENDPOINT_URL"])
else:
    s3_client = boto3.client("s3")

MAX_UPLOAD_SIZE = 5000000000  # 5 GB single file upload limit for S3
CHUNK_SIZE = 50000000  # 50 MB chunk size for multipart uploads


def get_dum_version():
    """
    Reads the DUM package version number from the VERSION.txt file bundled with
    this Lambda function.

    Returns
    -------
    version : str
        The version string read from VERSION.txt

    """
    logger.info("Searching Lambda root for version file")

    version_location = os.getenv("VERSION_LOCATION", "config")
    version_file = os.getenv("VERSION_FILE", "VERSION.txt")

    lambda_root = os.environ["LAMBDA_TASK_ROOT"]

    version_path = join(lambda_root, version_location, version_file)

    if not os.path.exists(version_path):
        raise RuntimeError(f"No version file found at location {version_path}")

    with open(version_path, "rb") as infile:
        version = infile.read().decode("utf-8").strip()

    logger.info("Read version %s from %s", version, version_path)

    return version


def check_client_version(client_version, service_version):
    """
    Compares the DUM version sent by the client script with the version number
    bundled with this Lambda function. The results of the check do not affect
    whether the request is processed or not, but are logged for troubleshooting
    or debugging purposes.

    Parameters
    ----------
    client_version : str
        The client version parsed from the HTTP request header.
    service_version : str
        The lambda service function version parsed from the bundled version file.

    """
    # Check if the client version is in sync with what this function expects
    # A mismatch might not necessarily imply the request cannot be serviced, but it needs to be logged
    if not client_version:
        logger.warning("No DUM version provided by client, cannot guarantee request compatibility")
    elif client_version != service_version:
        logger.warning(
            "Version mismatch between client (%s) and service (%s), cannot guarantee request compatibility",
            client_version,
            service_version,
        )
    else:
        logger.info("DUM client version (%s) matches ingress service", client_version)


def check_bucket_access(bucket_name, bucket_type):
    """
    Verifies that the given S3 bucket exists and this Lambda has permissions
    to perform at least a HEAD operation.

    Parameters
    ----------
    bucket_name : str
        Name of bucket to check.
    bucket_type : str
        Descriptive type ("staging" or "archive").

    Returns
    -------
    bool
        True if bucket exists and we have permission.
        False if bucket does not exist.

    Raises
    ------
    ClientError
        On 403 or unexpected errors.
    """
    try:
        # Bucket exists and is accessible
        s3_client.head_bucket(Bucket=bucket_name)
        logger.info("%s bucket '%s' is accessible", bucket_type, bucket_name)
        return True

    except botocore.exceptions.ClientError as e:
        code = e.response["Error"]["Code"]

        # Bucket not found
        if code == "404":
            logger.error(
                "%s bucket '%s' does not exist (404 Not Found)",
                bucket_type.capitalize(),
                bucket_name,
            )
            return False

        # Bucket exists but access is forbidden
        if code == "403":
            logger.error(
                "%s bucket '%s' exists but access is forbidden (403). "
                "Bucket policy/IAM require correction.",
                bucket_type.capitalize(),
                bucket_name,
            )
            return False

        # Unexpected error when checking bucket
        logger.exception(
            "Unexpected error when checking %s bucket '%s' (%s)",
            bucket_type.capitalize(),
            bucket_name,
            code,
        )
        return False   # Always return boolean (never None)


def file_exists_in_bucket(bucket_name, object_key, md5_digest, base64_md5_digest, file_size, last_modified):
    """
    Checks if the file already exists in the given S3 bucket and matches the same
    content (MD5 + size + modified time).

    Parameters
    ----------
    bucket_name : str
        The S3 bucket name to check.
    object_key : str
        The object key to check.
    md5_digest : str
        MD5 hash digest of the file (hex).
    base64_md5_digest : str
        Base64 encoded MD5 of the same file.
    file_size : int
        File size in bytes.
    last_modified : float
        Unix timestamp of the local file.

    Returns
    -------
    bool
        True if the same file already exists, False otherwise.
    """
    try:
        object_head = s3_client.head_object(Bucket=bucket_name, Key=object_key)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        else:
            # Some other kind of unexpected error
            raise

    object_length = int(object_head["ContentLength"])
    object_last_modified = object_head["LastModified"]

    # Read metadata of S3 object
    meta = object_head.get("Metadata", {})

    if "md5chksum" in meta:
        object_md5 = meta["md5chksum"]
        request_md5 = base64_md5_digest
    elif "md5" in meta:
        object_md5 = meta["md5"]
        request_md5 = md5_digest
    # If neither is present, fall back to the ETag value, which should be the same as the hex MD5
    else:
        logger.warning("Missing MD5 for %s/%s, falling back to ETag", bucket_name, object_key)
        object_md5 = object_head["ETag"][1:-1]  # strip embedded quotes
        request_md5 = md5_digest

    request_length = int(file_size)
    request_last_modified = datetime.fromtimestamp(last_modified, tz=timezone.utc)

    logger.debug("bucket_name=%s", bucket_name)
    logger.debug("object_key=%s", object_key)
    logger.debug("object_length=%d", object_length)
    logger.debug("object_last_modified=%s", object_last_modified)
    logger.debug("object_md5=%s", object_md5)
    logger.debug("request_length=%d", request_length)
    logger.debug("request_last_modified=%s", request_last_modified)
    logger.debug("request_md5=%s", request_md5)

    if object_length != request_length:
        return False
    if not object_md5:
        logger.info("No usable MD5 for %s/%s (multipart or missing), treating as existing", bucket_name, object_key)
        return True

    return (
            object_length == request_length
            and object_md5 == request_md5
            and object_last_modified >= request_last_modified
    )


def should_upload_file(
        staging_bucket,
        archive_bucket,
        object_key,
        md5_digest,
        base64_md5_digest,
        file_size,
        last_modified,
        force_overwrite,
):
    """
    Determines whether the file should be uploaded to the staging bucket.

    Upload is skipped if the same file already exists in *either* staging or archive bucket,
    unless 'force_overwrite' is True.

    Parameters
    ----------
    staging_bucket : str
        Name of the staging S3 bucket to check.
    archive_bucket : str
        Name of the archive S3 bucket to check.
    object_key : str
        Object key location within the bucket.
    md5_digest : str
        MD5 hash digest of the file (hex).
    base64_md5_digest : str
        Base64 encoded MD5 digest.
    file_size : int
        File size in bytes.
    last_modified : float
        Unix timestamp of the file.
    force_overwrite : bool
        Whether to always overwrite the file.

    Returns
    -------
    bool
        True if upload should occur, False otherwise.
    """
    if force_overwrite:
        logger.debug("Force overwrite enabled for %s", object_key)
        return True

    file_exists_in_staging = False
    file_exists_in_archive = False

    # Check staging bucket first, then archive only if not found in staging
    if file_exists_in_bucket(staging_bucket, object_key, md5_digest, base64_md5_digest, file_size, last_modified):
        file_exists_in_staging = True
        logger.debug("File %s found in staging bucket %s", object_key, staging_bucket)
    elif file_exists_in_bucket(archive_bucket, object_key, md5_digest, base64_md5_digest, file_size, last_modified):
        file_exists_in_archive = True
        logger.debug("File %s found in archive bucket %s", object_key, archive_bucket)

    if file_exists_in_staging or file_exists_in_archive:
        logger.info(
            "File %s already exists in staging (%s) or archive (%s)",
            object_key,
            staging_bucket,
            archive_bucket,
        )
        return False

    return True


def generate_presigned_upload_url(
    bucket_info,
    object_key,
    md5_digest,
    base64_md5_digest,
    file_size,
    last_modified,
    client_version,
    service_version,
    expires_in=3000,
):
    """
    Generates a presigned URL suitable for uploading to the S3 location
    corresponding to the provided bucket name and object key.

    Parameters
    ----------
    bucket_info : dict
        Dictionary containing information about the destination bucket.
    object_key : str
        Object key location within the S3 bucket to be uploaded to.
    md5_digest : str
        MD5 hash digest corresponding to the file to generate a URL for.
    base64_md5_digest : str
        Base64 encoded version of the MD5 hash digest corresponding to the file
        to generate a URL for.
    file_size : int
        Size in bytes of the incoming version of the file.
    last_modified : float
        Last modified time of the incoming version of the file as a Unix Epoch.
    client_version : str
        Version of the DUM client used to initiate the ingress reqeust.
    service_version : str
        Version of the DUM lambda service used to process this ingress request.
    expires_in : int, optional
        Expiration time of the generated URL in seconds. After this time,
        the URL should no longer be valid. Defaults to 3000 seconds.

    Returns
    -------
    url : str
        The generated presigned upload URL corresponding to the requested S3
        location.

    """
    client_method = "put_object"
    method_parameters = {
        "Bucket": bucket_info["name"],
        "Key": object_key,
        "ContentLength": file_size,
        "Metadata": {
            "md5": md5_digest,
            "last_modified": datetime.fromtimestamp(last_modified, tz=timezone.utc).isoformat(),
            "dum_client_version": client_version,
            "dum_service_version": service_version,
            # The following fields are included for rclone compatibility
            "mtime": str(last_modified),
        },
    }

    # We only want to include an MD5 if the requested file length is non-zero,
    # AWS will reject the request otherwise.
    if file_size > 0:
        method_parameters["ContentMD5"] = base64_md5_digest

    if bucket_info.get("storage_class"):
        method_parameters["StorageClass"] = bucket_info["storage_class"]

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod=client_method, Params=method_parameters, ExpiresIn=expires_in
        )

        logger.info("Generated presigned URL: %s", url)
    except ClientError:
        logger.exception("Failed to generate a presigned URL for %s", join(bucket_info["name"], object_key))
        raise

    return url


def process_multipart_upload(
    bucket_info,
    object_key,
    file_size,
    md5_digest,
    base64_md5_digest,
    last_modified,
    client_version,
    service_version,
    expires_in=3600,
):
    """
    Initiates a multipart upload request for the provided S3 bucket/key location.
    This function also derives the presigned URLs for each upload part request
    based on the size of the file, as well as URLs the client can use to either
    complete or prematurely terminate the multipart upload request.

    Parameters
    ----------
    bucket_info : dict
        Dictionary containing information about the destination bucket.
    object_key : str
        Object key location within the S3 bucket to be uploaded to.
    file_size : int
        Size of the file to be multipart uploaded, in bytes.
    md5_digest : str
        MD5 hash digest corresponding to the file to generate URLs for.
    base64_md5_digest : str
        Base64 encoded version of the MD5 hash digest corresponding to the file
        to generate URLs for.
    last_modified : float
        Last modified time of the incoming version of the file as a Unix Epoch.
    client_version : str
        Version of the DUM client used to initiate the ingress reqeust.
    service_version : str
        Version of the DUM lambda service used to process this ingress request.
    expires_in: int, optional
        Expiration time of the generated URL in seconds. After this time,
        the URL should no longer be valid. Defaults to 3600 seconds.

    Returns
    -------
    signed_urls : list
        List of pre-signed URLs for each part of the multipart upload.
    complete_upload_url : str
        Pre-signed URL for the client to complete the multipart upload.
    abort_upload_url : str
        Pre-signed URL for the client to abort the multipart upload.
    num_parts : int
        The total number of parts in the multipart upload.

    """
    # Initiate the multi-part upload request
    response = s3_client.create_multipart_upload(
        Bucket=bucket_info["name"],
        Key=object_key,
        Metadata={
            "md5": md5_digest,
            "last_modified": datetime.fromtimestamp(last_modified, tz=timezone.utc).isoformat(),
            "dum_client_version": client_version,
            "dum_service_version": service_version,
            # The following fields are included for rclone compatibility
            # Note that md5chksum is required for multipart objects only
            "md5chksum": base64_md5_digest,
            "mtime": str(last_modified),
        },
    )

    # This upload ID will be required for all subsequent requests related to
    # this multipart upload
    upload_id = response["UploadId"]

    num_parts = int(ceil(file_size / CHUNK_SIZE))

    logger.info(f"Generating pre-signed URLs for {num_parts} file parts, {upload_id=}")

    signed_urls = []

    try:
        # Generate the pre-signed URLs for each part of the upload
        for part_num in range(1, num_parts + 1):  # part numbers use 1-based index
            method_parameters = {
                "Bucket": bucket_info["name"],
                "Key": object_key,
                "UploadId": upload_id,
                "PartNumber": part_num,
            }

            try:
                signed_urls.append(
                    s3_client.generate_presigned_url(
                        ClientMethod="upload_part", Params=method_parameters, ExpiresIn=expires_in
                    )
                )
            except ClientError:
                logger.exception(
                    "Failed to generate a multipart presigned URL for %s", join(bucket_info["name"], object_key)
                )
                raise

        # Create pre-signed URLs for the client to complete (or abort) the multipart upload
        method_parameters = {"Bucket": bucket_info["name"], "Key": object_key, "UploadId": upload_id}

        complete_upload_url = s3_client.generate_presigned_url(
            ClientMethod="complete_multipart_upload", Params=method_parameters, ExpiresIn=expires_in, HttpMethod="POST"
        )

        logger.info("Generated multipart upload complete presigned URL: %s", complete_upload_url)

        abort_upload_url = s3_client.generate_presigned_url(
            ClientMethod="abort_multipart_upload", Params=method_parameters, ExpiresIn=expires_in, HttpMethod="POST"
        )

        logger.info("Generated multipart upload abort presigned URL: %s", abort_upload_url)
    except Exception:
        logger.exception("Aborting multipart upload for upload_id=%s due to error", upload_id)
        s3_client.abort_multipart_upload(Bucket=bucket_info["name"], Key=object_key, UploadId=upload_id)
        raise

    return signed_urls, complete_upload_url, abort_upload_url, num_parts


def process_ingress_request(ingress_request, request_index, node_bucket_map, request_event):
    """
    Processes a single ingress request and derives the appropriate S3 upload
    URL based on the request contents and the bucket map configuration.

    Parameters
    ----------
    ingress_request : dict
        Dictionary containing details of the ingress request to be processed.
    request_index : int
        Index of the request within the batch of requests being processed.
    node_bucket_map : dict
        Bucket map configuration for the requestor node.
    request_event : dict
        Event that triggered the Lambda invocation.

    Returns
    -------
    result : dict
        JSON-compliant dictionary containing the results of processing the
        ingress request.
    """
    ingress_path = ingress_request.get("ingress_path")
    trimmed_path = ingress_request.get("trimmed_path")
    md5_digest = ingress_request.get("md5")
    file_size = ingress_request.get("size")
    last_modified = ingress_request.get("last_modified")

    request_headers = request_event["headers"]
    request_node = request_event["queryStringParameters"]["node"]
    client_version = request_headers.get("ClientVersion", None)
    service_version = get_dum_version()
    force_overwrite = bool(int(request_headers.get("ForceOverwrite", False)))

    # Convert MD5 from hex to base64 (AWS format)
    base64_md5_digest = base64.b64encode(bytes.fromhex(md5_digest)).decode()

    if not all(field is not None for field in (ingress_path, trimmed_path, md5_digest, file_size, last_modified)):
        logger.error("One or more missing fields in request index %d", request_index)
        raise RuntimeError

    logger.info("Processing request for %s (index %d)", trimmed_path, request_index)

    # Get bucket info for staging and archive
    staging_bucket_info = bucket_for_path(node_bucket_map, trimmed_path, logger, bucket_type="staging")
    archive_bucket_info = bucket_for_path(node_bucket_map, trimmed_path, logger, bucket_type="archive")

    destination_bucket = staging_bucket_info["name"]
    archive_bucket = archive_bucket_info["name"]

    #
    # Verify access to both staging and archive buckets.
    # Staging bucket must exist and be readable by this Lambda.
    # Archive bucket must also be accessible to determine whether the file
    # already exists. Fail early if either bucket cannot be accessed.
    #
    staging_ok = check_bucket_access(destination_bucket, "staging")
    archive_ok = check_bucket_access(archive_bucket, "archive")

    # Staging bucket is required
    if not staging_ok:
        logger.error(
            "Staging bucket %s does not exist or cannot be accessed",
            destination_bucket,
        )
        return {
            "result": HTTPStatus.NOT_FOUND,
            "trimmed_path": trimmed_path,
            "ingress_path": ingress_path,
            "s3_url": None,
            "bucket": destination_bucket,
            "key": None,
            "message": (
                f"Staging bucket {destination_bucket} does not exist or cannot be accessed"
            ),
        }

    # Archive bucket must also be accessible to correctly evaluate deduplication state
    if not archive_ok:
        logger.error(
            "Archive bucket %s does not exist or cannot be accessed",
            archive_bucket,
        )
        return {
            "result": HTTPStatus.FORBIDDEN,
            "trimmed_path": trimmed_path,
            "ingress_path": ingress_path,
            "s3_url": None,
            "bucket": archive_bucket,
            "key": None,
            "message": (
                f"Archive bucket {archive_bucket} cannot be accessed. "
                f"Verify that cross-account permissions are configured"
            ),
        }

    object_key = join(request_node.lower(), trimmed_path)

    if should_upload_file(
            destination_bucket,
            archive_bucket,
            object_key,
            md5_digest,
            base64_md5_digest,
            int(file_size),
            float(last_modified),
            force_overwrite,
    ):
        # Multipart upload path
        if file_size >= MAX_UPLOAD_SIZE:
            logger.info("%s exceeds maximum upload size, initiating multi-part upload", object_key)

            signed_urls, complete_url, abort_url, num_parts = process_multipart_upload(
                staging_bucket_info,
                object_key,
                file_size,
                md5_digest,
                base64_md5_digest,
                float(last_modified),
                client_version,
                service_version,
            )

            return {
                "result": HTTPStatus.OK,
                "trimmed_path": trimmed_path,
                "ingress_path": ingress_path,
                "s3_urls": signed_urls,
                "bucket": destination_bucket,
                "key": object_key,
                "upload_complete_url": complete_url,
                "upload_abort_url": abort_url,
                "num_parts": num_parts,
                "chunk_size": CHUNK_SIZE,
                "message": "Multipart upload request initiated",
            }

        # Single-part upload
        s3_url = generate_presigned_upload_url(
            staging_bucket_info,
            object_key,
            md5_digest,
            base64_md5_digest,
            file_size,
            float(last_modified),
            client_version,
            service_version,
        )

        return {
            "result": HTTPStatus.OK,
            "trimmed_path": trimmed_path,
            "ingress_path": ingress_path,
            "md5": md5_digest,
            "base64_md5": base64_md5_digest,
            "s3_url": s3_url,
            "bucket": destination_bucket,
            "key": object_key,
            "message": "Request success",
        }

    #
    # File already exists in staging or archive — upload not needed
    #
    logger.info(
        "File %s already exists in bucket %s or archive %s and should not be overwritten",
        object_key,
        destination_bucket,
        archive_bucket,
    )

    return {
        "result": HTTPStatus.NO_CONTENT,
        "trimmed_path": trimmed_path,
        "ingress_path": ingress_path,
        "s3_url": None,
        "bucket": destination_bucket,
        "key": object_key,
        "message": "File already exists",
    }


def lambda_handler(event, context):
    """
    Entrypoint for this Lambda function. Derives the appropriate S3 upload URI
    location based on the contents of the ingress request.

    Parameters
    ----------
    event : dict
        Dictionary containing details of the event that triggered the Lambda.
    context : dict
        Dictionary containing details of the AWS context in which the Lambda was
        invoked. Currently unused by this function.

    Returns
    -------
    response : dict
        JSON-compliant dictionary containing the results of the request.

    """
    # Read the version number assigned to this function
    service_version = get_dum_version()

    # Read the bucket map configured for the service
    bucket_map = initialize_bucket_map(logger)

    # Parse request details from event object
    body = json.loads(event["body"])
    headers = event["headers"]

    request_node = event["queryStringParameters"].get("node")

    if not request_node:
        logger.error("No request node ID provided in queryStringParameters")
        raise RuntimeError

    client_version = headers.get("ClientVersion", None)

    check_client_version(client_version, service_version)

    node_bucket_map = bucket_map["NODES"].get(request_node.upper())

    if not node_bucket_map:
        logger.exception("No bucket map entries configured for node ID %s", request_node)
        raise RuntimeError

    results = []

    num_cores = max(os.cpu_count(), 1)

    logger.info(f"Available CPU cores: {num_cores}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
        # Iterate over all batched requests
        futures = {
            executor.submit(process_ingress_request, ingress_request, request_index, node_bucket_map, event)
            for request_index, ingress_request in enumerate(body)
        }

        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    #
    # Determine top-level HTTP status for the entire batch.
    # If ANY request fails (403, 404, other), return that status code so the DUM
    # client immediately understands the request failed and will not hang.
    #
    batch_status = HTTPStatus.OK
    for result in results:
        if result["result"] not in (HTTPStatus.OK, HTTPStatus.NO_CONTENT):
            batch_status = result["result"]
            break

    return {
        "statusCode": batch_status,
        "body": json.dumps(results),
    }

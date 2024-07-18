"""
==================
pds_ingress_app.py
==================

Lambda function which acts as the PDS Ingress Service, mapping local file paths
to their destinations in S3.
"""
import json
import logging
import os
from datetime import datetime
from datetime import timezone
from os.path import join

import boto3
import botocore
import yaml
from botocore.exceptions import ClientError

s3_client = boto3.client("s3")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

LEVEL_MAP = {
    "CRITICAL": logging.CRITICAL,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

logger = logging.getLogger()
logger.setLevel(LEVEL_MAP.get(LOG_LEVEL.upper(), logging.INFO))

logger.info("Loading function PDS Ingress Service")

s3_client = boto3.client("s3")


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


def initialize_bucket_map():
    """
    Parses the YAML bucket map file for use with the current service invocation.
    The bucket map location is derived from the OS environment. Currently,
    only the bucket map bundled with this Lambda function is supported.

    Returns
    -------
    bucket_map : dict
        Contents of the parsed bucket map YAML config file.

    Raises
    ------
    RuntimeError
        If the bucket map cannot be found at the configured location.

    """
    bucket_map_location = os.getenv("BUCKET_MAP_LOCATION", "config")
    bucket_map_file = os.getenv("BUCKET_MAP_FILE", "bucket-map.yaml")

    bucket_map_path = join(bucket_map_location, bucket_map_file)

    # TODO: add support for bucket map locations that are s3 or http URI's
    if bucket_map_path.startswith("s3://"):
        bucket_map = {}
    elif bucket_map_path.startswith(("http://", "https://")):
        bucket_map = {}
    else:
        logger.info("Searching Lambda root for bucket map")

        lambda_root = os.environ["LAMBDA_TASK_ROOT"]

        bucket_map_path = join(lambda_root, bucket_map_path)

        if not os.path.exists(bucket_map_path):
            raise RuntimeError(f"No bucket map found at location {bucket_map_path}")

        with open(bucket_map_path, "r") as infile:
            bucket_map = yaml.safe_load(infile)

    logger.info("Bucket map %s loaded", bucket_map_path)
    logger.debug(str(bucket_map))

    return bucket_map


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


def bucket_exists(destination_bucket):
    """
    Checks if the destination bucket read from the bucket-map actually exists or not.

    Parameters
    ----------
    destination_bucket : str
        Name of the S3 bucket to check for.

    Returns
    -------
    True if the bucket exists, False otherwise

    """
    try:
        s3_client.head_bucket(Bucket=destination_bucket)
    except botocore.exceptions.ClientError as e:
        logger.warning("Check for bucket %s returned code %s", destination_bucket, e.response["Error"]["Code"])
        return False

    return True


def should_overwrite_file(destination_bucket, object_key, md5_digest, file_size, last_modifed, force_overwrite):
    """
    Determines if the file requested for ingress already exists in the S3
    location we plan to upload to, and whether it should be overwritten with a
    new version based on file info provided in the request headers.

    Parameters
    ----------
    destination_bucket : str
        Name of the S3 bucket to be uploaded to.
    object_key : str
        Object key location within the S3 bucket to be uploaded to.
    md5_digest : str
        MD5 hash digest of the incoming version of the file.
    file_size : int
        Size in bytes of the incoming version of the file.
    last_modifed : float
        Last modified time of the incoming version of the file as a Unix Epoch.
    force_overwrite : bool
        Flag indiciating whether to always overwrite with the incoming verisons of file.

    Returns
    -------
    True if overwrite (or write) should occur, False otherwise.

    """
    # First, check if the client has specified the "force overwite" option
    if force_overwrite:
        logger.debug("Client has specified force overwrite")
        return True

    # Next, check if the file already exists within the S3 bucket designated by
    # the bucket map
    try:
        object_head = s3_client.head_object(Bucket=destination_bucket, Key=object_key)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            # File does not already exist, safe to write
            return True
        else:
            # Some other kind of unexpected error
            raise

    object_length = int(object_head["ContentLength"])
    object_last_modified = object_head["LastModified"]
    object_md5 = object_head["ETag"][1:-1]  # strip embedded quotes

    logger.debug("object_length=%d", object_length)
    logger.debug("object_last_modified=%s", object_last_modified)
    logger.debug("object_md5=%s", object_md5)

    request_length = file_size
    request_last_modified = datetime.fromtimestamp(last_modifed, tz=timezone.utc)
    request_md5 = md5_digest

    logger.debug("request_length=%d", request_length)
    logger.debug("request_last_modified=%s", request_last_modified)
    logger.debug("request_md5=%s", request_md5)

    # If the request object differs from current version in S3 (newer, different contents),
    # then it should be overwritten
    return not (
        object_length == request_length and object_md5 == request_md5 and object_last_modified >= request_last_modified
    )


def generate_presigned_upload_url(bucket_name, object_key, expires_in=1000):
    """
    Generates a presigned URL suitable for uploading to the S3 location
    corresponding to the provided bucket name and object key.

    Parameters
    ----------
    bucket_name : str
        Name of the S3 bucket to be uploaded to.
    object_key : str
        Object key location within the S3 bucket to be uploaded to.
    expires_in : int
        Expiration time of the generated URL in seconds. After this time,
        the URL should no longer be valid.

    Returns
    -------
    url : str
        The generated presigned upload URL corresponding to the requested S3
        location.

    """
    client_method = "put_object"
    method_parameters = {"Bucket": bucket_name, "Key": object_key}

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod=client_method, Params=method_parameters, ExpiresIn=expires_in
        )

        logger.info("Generated presigned URL: %s", url)
    except ClientError:
        logger.exception("Failed to generate a presigned URL for %s", join(bucket_name, object_key))
        raise

    return url


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
    bucket_map = initialize_bucket_map()

    # Parse request details from event object
    body = json.loads(event["body"])
    headers = event["headers"]
    force_overwrite = bool(int(headers.get("ForceOverwrite", False)))
    request_node = event["queryStringParameters"].get("node")

    if not request_node:
        logger.error("No request node ID provided in queryStringParameters")
        raise RuntimeError

    client_version = headers.get("ClientVersion", None)

    check_client_version(client_version, service_version)

    node_bucket_map = bucket_map["MAP"]["NODES"].get(request_node.upper())

    if not node_bucket_map:
        logger.exception("No bucket map entries configured for node ID %s", request_node)
        raise RuntimeError

    result = []

    # Iterate over all batched requests
    for request_index, ingress_request in enumerate(body):
        ingress_path = ingress_request.get("ingress_path")
        trimmed_path = ingress_request.get("trimmed_path")
        md5_digest = ingress_request.get("md5")
        file_size = ingress_request.get("size")
        last_modifed = ingress_request.get("last_modified")

        if not all(field is not None for field in (ingress_path, trimmed_path, md5_digest, file_size, last_modifed)):
            logger.error("One or more missing fields in request index %d", request_index)
            raise RuntimeError

        logger.info("Processing request for %s (index %d)", trimmed_path, request_index)

        prefix_key = trimmed_path.split(os.sep)[0]

        if prefix_key in node_bucket_map:
            destination_bucket = node_bucket_map[prefix_key]
            logger.info("Resolved bucket location %s for prefix %s", destination_bucket, prefix_key)
        else:
            destination_bucket = node_bucket_map["default"]
            logger.warning(
                "No bucket location configured for prefix %s, using default bucket %s", prefix_key, destination_bucket
            )

        if not bucket_exists(destination_bucket):
            result.append(
                {
                    "result": 404,
                    "local_url": trimmed_path,
                    "s3_url": None,
                    "message": f"Mapped bucket {destination_bucket} does not exist or has insufficient access permisisons",
                }
            )
        else:
            object_key = join(request_node.lower(), trimmed_path)

            if should_overwrite_file(
                destination_bucket, object_key, md5_digest, int(file_size), float(last_modifed), force_overwrite
            ):
                s3_url = generate_presigned_upload_url(destination_bucket, object_key)

                result.append(
                    {
                        "result": 200,
                        "trimmed_path": trimmed_path,
                        "ingress_path": ingress_path,
                        "s3_url": s3_url,
                        "message": "Request success",
                    }
                )
            else:
                logger.info(
                    "File %s already exists in bucket %s and should not be overwritten", object_key, destination_bucket
                )

                result.append(
                    {"result": 204, "trimmed_path": trimmed_path, "s3_url": None, "message": "File already exists"}
                )

    return {"statusCode": 200, "body": json.dumps(result)}

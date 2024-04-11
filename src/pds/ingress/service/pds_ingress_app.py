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
from os.path import join

import boto3
import yaml
from botocore.exceptions import ClientError

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

    logger.info(f"Bucket map {bucket_map_path} loaded")
    logger.debug(str(bucket_map))

    return bucket_map


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
    expires_in : str
        Expiration time of the generated URL in seconds. After this time,
        the URL should no longer be valid.

    Returns
    -------
    url : str
        The generated presigned upload URL corresponding to the requested S3
        location.

    """
    s3_client = boto3.client("s3")
    client_method = "put_object"
    method_parameters = {"Bucket": bucket_name, "Key": object_key}

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod=client_method, Params=method_parameters, ExpiresIn=expires_in
        )

        logger.info(f"Generated presigned URL: {url}")
    except ClientError:
        logger.exception(f"Failed to generate a presigned URL for {join(bucket_name, object_key)}")
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
    # Read the bucket map configured for the service
    bucket_map = initialize_bucket_map()

    # Parse request details from event object
    body = json.loads(event["body"])
    local_url = body.get("url")
    request_node = event["queryStringParameters"].get("node")

    if not local_url or not request_node:
        logger.exception("Both a local URL and request Node ID must be provided")
        raise RuntimeError

    logger.info(f"Processing request from node {request_node} for local url {local_url}")

    node_bucket_map = bucket_map["MAP"]["NODES"].get(request_node.upper())

    if not node_bucket_map:
        logger.exception(f"No bucket map entries configured for Node ID {request_node}")
        raise RuntimeError

    prefix_key = local_url.split(os.sep)[0]

    if prefix_key in node_bucket_map:
        destination_bucket = node_bucket_map[prefix_key]
        logger.info(f"Resolved bucket location {destination_bucket} for prefix {prefix_key}")
    else:
        destination_bucket = node_bucket_map["default"]
        logger.warning(
            f"No bucket location configured for prefix {prefix_key}, using default bucket {destination_bucket}"
        )

    object_key = join(request_node.lower(), local_url)

    s3_url = generate_presigned_upload_url(destination_bucket, object_key)

    return {"statusCode": 200, "body": json.dumps(s3_url)}

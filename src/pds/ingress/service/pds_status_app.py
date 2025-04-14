"""
=================
pds_status_app.py
=================

Lambda function used to status an Ingress request based on a user-provided
manifest. For each file included in a provided manifest, this function will
derive the Ingress status of said file in S3 and return a report to the user.
"""
# TODO refactor duplicated code into shared module(s) with pds_ingress_app.py

import json
import logging
import os
from os.path import join

import boto3
import botocore
from botocore.exceptions import ClientError

from util.config_util import initialize_bucket_map
from util.log_util import SingleLogFilter, LOG_LEVELS

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger = logging.getLogger()
logger.setLevel(LOG_LEVELS.get(LOG_LEVEL.lower(), logging.INFO))
logger.addFilter(SingleLogFilter())

logger.info("Loading function PDS Ingress Status Service")

if os.getenv("ENDPOINT_URL", None):
    logger.info("Using endpoint URL from envvar: %s", os.environ["ENDPOINT_URL"])
    s3_client = boto3.client("s3", endpoint_url=os.environ["ENDPOINT_URL"])
    ses_client = boto3.client('ses', endpoint_url=os.environ["ENDPOINT_URL"])
else:
    s3_client = boto3.client("s3")
    ses_client = boto3.client("ses")


def parse_manifests(records):
    """
    Parses the manifest and associated attributes from each record returned
    from polling the status queue.

    Parameters
    ----------
    records : list of dict
        List of the message records from the status queue. Each record will
        be parsed into its own seperate manifest request.

    Returns
    -------
    manifests : list of tuple
        List of 3-tuples containing the requesting node ID, return email address,
        and parsed manifest object for each provided record.

    """
    manifests = []

    for record in records:
        body = record["body"]

        try:
            manifest = json.loads(body)
        except Exception as err:
            logger.exception(f"Failed to parse manifiest from message body, reason: {str(err)}")
            raise RuntimeError

        # TODO: validation on expected attributes
        message_attributes = record["messageAttributes"]
        return_email = message_attributes["email"]["stringValue"]
        request_node = message_attributes["node"]["stringValue"]

        manifests.append((request_node, return_email, manifest))

    return manifests

def process_manifest(request_node, manifest, bucket_map):
    """
    Processes the provided manifest by deriving an ingest status for each
    path within the manifest.

    Parameters
    ----------
    request_node : str
        PDS node identifier associated to the provided manifest.
    manifest : dict
        Parsed manifest containing a number of paths to status with associated
        information (md5, size and last modified time)
    bucket_map : dict
        The parsed bucket map configuration used to determine where to look for
        files in S3

    Returns
    -------
    results : dict
        Result dictionary mapping each path in the provided manifest to the
        ingress status of said path.

    """
    results = {}

    node_bucket_map = bucket_map["MAP"]["NODES"].get(request_node.upper())

    if not node_bucket_map:
        logger.exception("No bucket map entries configured for node ID %s", request_node)
        raise RuntimeError

    for trimmed_path, file_info in manifest.items():
        prefix_key = trimmed_path.split(os.sep)[0]

        if prefix_key in node_bucket_map:
            destination_bucket = node_bucket_map[prefix_key]
        else:
            destination_bucket = node_bucket_map["default"]

        object_key = join(request_node.lower(), trimmed_path)

        ingress_status = get_ingress_status(destination_bucket, object_key, file_info)

        results[trimmed_path] = ingress_status

    return results

def get_ingress_status(destination_bucket, object_key, file_info):
    """
    Derives an ingress status for the file referenced by the provided
    S3 bucket and key combination.

    The derived ingress status can be one of the following:
        "Missing" : the provided file location does not actually exist in S3
        "Modified" : the provided file location exists in S3, but there is a mismatch
                     between the provided file metadata and what is stored in S3
        "Uploaded" : the provided file location exists in S3, and all provided
                     file metadata matches what is stored in S3

    Parameters
    ----------
    destination_bucket : str
        Name of the S3 bucket to status.
    object_key : str
        Object key to use in conjuction with the bucket.
    file_info : dict
        Dictionary containing file metadata dervied from the requestor's version
        of the file. This includes file size, an md5 hash, and the last modified time.

    Returns
    -------
    ingress_status : str
        One of the ingress status string values described above.

    """
    try:
        object_head = s3_client.head_object(Bucket=destination_bucket, Key=object_key)
    except botocore.exceptions.ClientError as e:
        if e.response["Error"]["Code"] == "404":
            # File does not exist in S3
            ingress_status = "Missing"
            return ingress_status
        else:
            # Some other kind of unexpected error
            raise

    object_length = int(object_head["ContentLength"])
    object_last_modified = object_head["Metadata"]["last_modified"]
    object_md5 = object_head["Metadata"]["md5"]

    request_length = file_info["size"]
    request_last_modified = file_info["last_modified"]
    request_md5 = file_info["md5"]

    if not (
        object_length == request_length and object_md5 == request_md5 and object_last_modified == request_last_modified
    ):
        ingress_status = "Modified"
    else:
        ingress_status = "Uploaded"

    return ingress_status


def lambda_handler(event, context):
    """
    Entrypoint for this Lambda function. Processes the latest messages from
    the status queue, and returns a status report for each new message.

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
    bucket_map = initialize_bucket_map(logger)

    # Get the manifest contents from the SQS event
    records = event["Records"]
    manifests = parse_manifests(records)

    for request_node, return_email, manifest in manifests:
        results = process_manifest(request_node, manifest, bucket_map)

        # TODO: retest when SES is configured
        # response = ses_client.send_email(
        #    Destination={
        #        'ToAddresses': [return_email]
        #    },
        #    Message={
        #        'Body': {
        #            'Text': {
        #                'Charset': 'UTF-8',
        #                'Data': json.dumps(results, indent=4)
        #            }
        #        },
        #        'Subject': {
        #            'Charset': 'UTF-8',
        #            'Data': 'PDS Ingress Status'
        #        }
        #    },
        #    Source='pds_status_app@jpl.nasa.gov'
        # )

        # logger.debug('SES response: %s', response)
        logger.info('Results: %s', results)

    # TODO: implement "batchItemFailures" https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html#services-sqs-batchfailurereporting
    return {
        'statusCode': 200
    }

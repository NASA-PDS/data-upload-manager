"""
=================
pds_status_app.py
=================

Lambda function used to status an Ingress request based on a user-provided
manifest. For each file included in a provided manifest, this function will
derive the Ingress status of said file in S3 and return a report to the user.
"""
import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from os.path import join

import boto3
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

logger.info("Loading function PDS Ingress Status Service")

if os.getenv("ENDPOINT_URL", None):
    logger.info("Using endpoint URL from envvar: %s", os.environ["ENDPOINT_URL"])
    s3_client = boto3.client("s3", endpoint_url=os.environ["ENDPOINT_URL"])
    ssm_client = boto3.client("ssm", endpoint_url=os.environ["ENDPOINT_URL"])
else:
    s3_client = boto3.client("s3")
    ssm_client = boto3.client("ssm")

EXPECTED_ATTRIBUTE_KEYS = ("email", "node")
"""The keys expected within the messageAttributes section of an SQS record."""


def parse_manifest(record):
    """
    Parses the manifest and associated attributes from each record returned
    from polling the status queue.

    Parameters
    ----------
    record : dict
        A single message record from the status queue. The record is parsed into
        its own seperate manifest request.

    Returns
    -------
    manifest : tuple
        3-tuple containing the requesting node ID, return email address,
        and parsed manifest object for each provided record.

    """
    body = record["body"]

    try:
        manifest = json.loads(body)
    except Exception as err:
        logger.exception(f"Failed to parse manifiest from message body, reason: {str(err)}")
        raise RuntimeError

    message_attributes = record["messageAttributes"]

    if not all(expected_key in message_attributes for expected_key in EXPECTED_ATTRIBUTE_KEYS):
        logger.exception(f"One or more missing keys from messageAttributes: {str(message_attributes.keys())}")
        raise RuntimeError

    return_email = json.loads(message_attributes["email"]["stringValue"])
    request_node = json.loads(message_attributes["node"]["stringValue"])

    return request_node, return_email, manifest


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
        bucket_info = bucket_for_path(node_bucket_map, trimmed_path, logger)

        destination_bucket = bucket_info["name"]

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
    except ClientError as e:
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


def send_email(message_body, return_email):
    """
    Sends the provided message body to the provided return email address.

    Email is sent via AWS SMTP endpoint, which requires credentials pulled by
    this function from the AWS SSM Parameter store.

    Parameters
    ----------
    message_body : str
        Body of the email message to send.
    return_email : str
        Email address to send to.

    Raises
    ------
    RuntimeError
        If the expected SMTP endpoint parameters are not successfully pulled
        from the SSM Parameter store.

    """
    smtp_config = {}

    # Pull the required SMTP endpoint parameters from SSM
    smtp_config_ssm_key_path = os.environ["SMTP_CONFIG_SSM_KEY_PATH"]
    response = ssm_client.get_parameters_by_path(Path=smtp_config_ssm_key_path, Recursive=True)

    # Map SSM parameter values to unique portion of the SSM key name
    for ssm_parameter in response["Parameters"]:
        smtp_config[ssm_parameter["Name"].split("/")[-1]] = ssm_parameter["Value"]

    expected_fields = ("username", "password", "server", "sender")

    if not all(field in smtp_config for field in expected_fields):
        raise RuntimeError(
            f"Unexpected SMTP configuration from SSM, expected {expected_fields}, got {list(smtp_config.keys())}"
        )

    # Create the email payload
    message = MIMEText(message_body)
    message["Subject"] = "PDS Data Upload Manager Status Service Request"
    message["From"] = smtp_config["sender"]
    message["To"] = return_email

    # Send the email via SMTP endpoint
    endpoint_host, endpoint_port = smtp_config["server"].split(":")

    with smtplib.SMTP(endpoint_host, int(endpoint_port)) as endpoint:
        endpoint.starttls()
        endpoint.login(smtp_config["username"], smtp_config["password"])
        endpoint.sendmail(smtp_config["sender"], return_email, message.as_string())


def lambda_handler(event, context):
    """
    Entrypoint for this Lambda function. Processes the latest messages from
    the status queue, and returns a status report for each new message.

    Notes
    -----
    This handler utilizes the Batched Item Failures mechanism between Lambda
    and SQS to ensure that only failed records are reprocessed.

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

    batch_item_failures = []
    sqs_batch_response = {"statusCode": 200}

    # Get the manifest contents from the SQS event
    for idx, record in enumerate(event["Records"]):
        try:
            request_node, return_email, manifest = parse_manifest(record)

            results = process_manifest(request_node, manifest, bucket_map)
            logger.debug("Results: %s", results)

            message_body = json.dumps(results, indent=4)
            send_email(message_body, return_email)
        except Exception as err:
            logger.exception(f"Failed to parse manifest from record index {idx}, reason: {str(err)}")
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    # Inform SQS about any partial failures so we don't reprocess the full
    # set of records over again.
    if batch_item_failures:
        sqs_batch_response["batchItemFailures"] = batch_item_failures

    return sqs_batch_response

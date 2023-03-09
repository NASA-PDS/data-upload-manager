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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.info("Loading function APIGatewayCustomIntegrationTestFunction")

S3_PREFIX = "cumulus-pds-public"


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
    # Parse request details from event object
    local_url = event.get("url")
    request_node = event.get("node")

    if not local_url or not request_node:
        raise RuntimeError("Both a local URL and request node ID must be provided")

    logger.info(f"Processing request from node {request_node} for local url {local_url}")

    filename = os.path.basename(local_url)

    if "collection" in filename.lower():
        product_type = "collections"
    elif "bundle" in filename.lower():
        product_type = "bundles"
    else:
        product_type = "unknown"

    s3_uri = f"s3://{S3_PREFIX}/{product_type}/{request_node.lower()}/{filename}"

    logger.info(f"Derived S3 URI {s3_uri}")

    return {"statusCode": 200, "body": json.dumps(s3_uri)}

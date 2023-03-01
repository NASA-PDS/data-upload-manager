
import logging
import json
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.info("Loading function APIGatewayCustomIntegrationTestFunction")

S3_PREFIX = "cumulus-pds-public"

def lambda_handler(event, context):
    # Parse request details from event object
    local_url    = event.get('url')
    request_node = event.get('node')

    if not local_url or not request_node:
        raise RuntimeError('Both a local URL and request node ID must be provided')

    logger.info(f'Processing request from node {request_node} for local url {local_url}')

    filename = os.path.basename(local_url)

    if 'collection' in filename.lower():
        product_type = 'collections'
    elif 'bundle' in filename.lower():
        product_type = 'bundles'
    else:
        product_type = 'unknown'

    s3_uri = f"s3://{S3_PREFIX}/{product_type}/{request_node.lower()}/{filename}"

    logger.info(f'Derived S3 URI {s3_uri}')

    return {
        'statusCode': 200,
        'body': json.dumps(s3_uri)
    }


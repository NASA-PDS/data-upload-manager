#!/usr/bin/env python3

import argparse
import json
import logging
import os
import requests
import subprocess
import sys

logger = logging.getLogger(__name__)

AWS_REGION = "us-west-2"
AWS_API_GATEWAY_ID = "x1u5w6z8eb"
AWS_API_GATEWAY_STAGE = "test"
AWS_API_GATEWAY_URL_TEMPLATE = "https://{id}.execute-api.{region}.amazonaws.com/{stage}/request"


def request_file_for_ingress(ingress_file_path, node_id):
    """
    Submits a request for file ingress to the PDS Ingress App API.

    Parameters
    ----------
    ingress_file_path : str
    node_id : str

    Returns
    -------
    s3_ingress_url : str

    """
    logger.info(f"Requesting ingress of file {ingress_file_path} for node ID {node_id}")

    api_gateway_url = AWS_API_GATEWAY_URL_TEMPLATE.format(id=AWS_API_GATEWAY_ID,
                                                          region=AWS_REGION,
                                                          stage=AWS_API_GATEWAY_STAGE)

    logger.info(f"Submitting ingress request to {api_gateway_url}")

    params = {"node": node_id}
    payload = {"url": ingress_file_path}
    headers = {"content-type": "application/json", "x-amz-docs-region": AWS_REGION}

    try:
        response = requests.post(
            api_gateway_url, params=params, data=json.dumps(payload), headers=headers
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        logger.error(f"Ingress request failed, reason: {str(err)}")
        sys.exit(1)

    logger.info(f'Raw content returned from request: {response.text}')

    json_response = response.json()

    s3_ingress_uri = json.loads(json_response["body"])

    return s3_ingress_uri


def ingress_file_to_s3(ingress_file_path, s3_ingress_uri):
    """
    Copies the local file path to the S3 location returned from the Ingress App.

    Parameters
    ----------
    ingress_file_path : str
    s3_ingress_uri : str

    """
    logger.info(f"Ingesting {ingress_file_path} to {s3_ingress_uri}")

    result = subprocess.run(
        ["aws", "s3", "cp", "--quiet", "--no-progress",
         ingress_file_path, s3_ingress_uri],
        capture_output=True, text=True
    )

    if result.returncode:
        raise RuntimeError(
            f"S3 copy failed, reason: {result.stderr}"
        )

    logger.info("Ingest complete")


def main():
    """
    Main entry point for the pds-ingress-client.py script.

    """
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-n', '--node', type=str, default="sbn",
                        help='PDS node identifier')
    parser.add_argument('ingress_file', type=str,
                        help='Path to the file to ingest to s3')

    args = parser.parse_args()

    ingress_file_path = os.path.abspath(args.ingress_file)

    if not os.path.exists(ingress_file_path):
        raise ValueError(f"Ingress file path {ingress_file_path} does not exist")

    node_id = args.node

    s3_ingress_uri = request_file_for_ingress(ingress_file_path, node_id)

    ingress_file_to_s3(ingress_file_path, s3_ingress_uri)


if __name__ == '__main__':
    main()
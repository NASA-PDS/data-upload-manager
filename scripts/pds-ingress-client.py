#!/usr/bin/env python3

import argparse
import json
import logging
import os
import requests
import subprocess

from src.pds.ingress.util.config_util import ConfigUtil

logger = logging.getLogger(__name__)


def request_file_for_ingress(ingress_file_path, node_id, api_gateway_config):
    """
    Submits a request for file ingress to the PDS Ingress App API.

    Parameters
    ----------
    ingress_file_path : str
        Local path to the file to request ingress for.
    node_id : str
        PDS node identifier.
    api_gateway_config : dict
        Dictionary or dictionary-like containing key/value pairs used to
        configure the API Gateway endpoint url.

    Returns
    -------
    s3_ingress_uri : str
        The S3 URI returned from the Ingress service lambda, which identifies
        the location in S3 the client should upload the file to.

    Raises
    ------
    RuntimeError
        If the request to the Ingress Service fails.

    """
    logger.info(f"Requesting ingress of file {ingress_file_path} for node ID {node_id}")

    # Extract the API Gateway configuration params
    api_gateway_template = api_gateway_config["url_template"]
    api_gateway_id = api_gateway_config["id"]
    api_gateway_region = api_gateway_config["region"]
    api_gateway_stage = api_gateway_config["stage"]
    api_gateway_resource = api_gateway_config["resource"]

    api_gateway_url = api_gateway_template.format(id=api_gateway_id,
                                                  region=api_gateway_region,
                                                  stage=api_gateway_stage,
                                                  resource=api_gateway_resource)

    logger.info(f"Submitting ingress request to {api_gateway_url}")

    params = {"node": node_id}
    payload = {"url": ingress_file_path}
    headers = {"content-type": "application/json", "x-amz-docs-region": api_gateway_region}

    try:
        response = requests.post(
            api_gateway_url, params=params, data=json.dumps(payload), headers=headers
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as err:
        raise RuntimeError(f"Ingress request failed, reason: {str(err)}")

    logger.debug(f'Raw content returned from request: {response.text}')

    json_response = response.json()

    s3_ingress_uri = json.loads(json_response["body"])

    logger.info(f"S3 URI for request: {s3_ingress_uri}")

    return s3_ingress_uri


def ingress_file_to_s3(ingress_file_path, s3_ingress_uri):
    """
    Copies the local file path to the S3 location returned from the Ingress App.

    Parameters
    ----------
    ingress_file_path : str
        Local path to the file to be copied to S3.
    s3_ingress_uri : str
        The S3 URI location for upload returned from the Ingress Service lambda
        function.

    Raises
    ------
    RuntimeError
        If the S3 upload fails for any reason.

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

    parser.add_argument('-c', '--config-path', type=str, default=None,
                        help=f'Path to the INI config for use with this client. '
                             f'If not provided, the default config '
                             f'({ConfigUtil.default_config_path()}) is used.')
    parser.add_argument('-n', '--node', type=str, default="sbn",
                        help='PDS node identifier')
    parser.add_argument('ingress_file', type=str,
                        help='Path to the file to ingest to s3')

    args = parser.parse_args()

    config = ConfigUtil.get_config(args.config_path)

    ingress_file_path = os.path.abspath(args.ingress_file)

    if not os.path.exists(ingress_file_path):
        raise ValueError(f"Ingress file path {ingress_file_path} does not exist")

    node_id = args.node

    s3_ingress_uri = request_file_for_ingress(ingress_file_path, node_id, config["API_GATEWAY"])

    ingress_file_to_s3(ingress_file_path, s3_ingress_uri)


if __name__ == '__main__':
    main()
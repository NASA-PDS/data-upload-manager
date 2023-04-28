#!/usr/bin/env python3

import argparse
import json
import logging
import requests
import subprocess

from pds.ingress.util.auth_util import AuthUtil
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.node_util import NodeUtil
from pds.ingress.util.path_util import PathUtil

logger = logging.getLogger(__name__)


def request_file_for_ingress(ingress_file_path, node_id, api_gateway_config, bearer_token):
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
    bearer_token : str
        The Bearer token authorizing the current user to access the Ingress
        Lambda function.

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

    params = {"node": node_id, "node_name": NodeUtil.node_id_to_long_name[node_id]}
    payload = {"url": ingress_file_path}
    headers = {"Authorization": bearer_token,
               "content-type": "application/json",
               "x-amz-docs-region": api_gateway_region}

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


def setup_argparser():
    """
    Helper function to perform setup of the ArgumentParser for the Ingress client
    script.

    Returns
    -------
    parser : argparse.ArgumentParser
        The command-line argument parser for use with the pds-ingress-client.py
        script.

    """
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-c', '--config-path', type=str, default=None,
                        help=f'Path to the INI config for use with this client. '
                             f'If not provided, the default config '
                             f'({ConfigUtil.default_config_path()}) is used.')
    parser.add_argument('-n', '--node', type=str.lower, required=True,
                        choices=NodeUtil.permissible_node_ids(),
                        help='PDS node identifier of the ingress requestor. '
                             'This value is used by the Ingress service to derive '
                             'the S3 upload location. Argument is case-insensitive.')
    parser.add_argument('--prefix', '-p', type=str, default=None,
                        help='Specify a path prefix to be trimmed from each '
                             'resolved ingest path such that is is not included '
                             'with the request to the Ingress Service. '
                             'For example, specifying --prefix "/home/user" would '
                             'modify paths such as "/home/user/bundle/file.xml" '
                             'to just "bundle/file.xml". This can be useful for '
                             'controlling which parts of a directory structure '
                             'should be included with the S3 upload location returned '
                             'by the Ingress Service.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Derive the full set of ingress paths without '
                             'performing any submission requests to the server.')
    parser.add_argument('ingress_paths', type=str, nargs='+',
                        metavar='file_or_dir',
                        help='One or more paths to the files to ingest to S3. '
                             'For each directory path is provided, this script will '
                             'automatically derive all sub-paths for inclusion with '
                             'the ingress request.')

    return parser

def main():
    """
    Main entry point for the pds-ingress-client.py script.

    Raises
    ------
    ValueError
        If a username and password are not defined within the parsed config,
        and dry-run is not enabled.

    """
    # TODO: create module to perform logger setup based on INI setting/user arg
    logging.basicConfig(level=logging.DEBUG)

    parser = setup_argparser()

    args = parser.parse_args()

    config = ConfigUtil.get_config(args.config_path)

    # Derive the full list of ingress paths based on the set of paths requested
    # by the user
    resolved_ingress_paths = PathUtil.resolve_ingress_paths(args.ingress_paths)

    node_id = args.node

    if not args.dry_run:
        cognito_config = config["COGNITO"]

        # TODO: add support for command-line username/password?
        if not cognito_config["username"] and cognito_config["password"]:
            raise ValueError(
                "Username and Password must be specified in the COGNITO portion of the INI config"
            )

        authentication_result = AuthUtil.perform_cognito_authentication(cognito_config)

        bearer_token = AuthUtil.create_bearer_token(authentication_result)

        for resolved_ingress_path in resolved_ingress_paths:
            # Remove path prefix if one was configured
            trimmed_path = PathUtil.trim_ingress_path(resolved_ingress_path, args.prefix)

            s3_ingress_uri = request_file_for_ingress(
                trimmed_path, node_id, config["API_GATEWAY"], bearer_token
            )

            ingress_file_to_s3(resolved_ingress_path, s3_ingress_uri)
    else:
        logger.info("Dry run requested, skipping ingress request submission.")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3

import argparse
import json
import logging
import os
import requests
import subprocess

from src.pds.ingress.util.config_util import ConfigUtil
from src.pds.ingress.util.node_util import NodeUtil

logger = logging.getLogger(__name__)


def resolve_ingress_paths(user_paths, resolved_paths=None, prefix=None):
    """
    Iterates over the list of user-provided paths to derive the final
    set of file paths to request ingress for.

    Parameters
    ----------
    user_paths : list of str
        The collection of user-requested paths to include with the ingress
        request. Can be any combination of file and directory paths.
    resolved_paths : list of str, optional
        The list of paths resolved so far. For top-level callers, this should
        be left as None.
    prefix : str
        Path prefix to trim from each resolved path, if present.

    Returns
    -------
    resolved_paths : list of str
        The list of all paths resolved from walking the set of user-provided
        paths.

    """
    # Initialize the list of resolved paths if necessary
    resolved_paths = resolved_paths or list()

    for user_path in user_paths:
        abs_user_path = os.path.abspath(user_path)

        if not os.path.exists(abs_user_path):
            logger.warning(f'Encountered path ({abs_user_path}) that does not '
                           f'actually exist, skipping...')
            continue

        if os.path.isfile(abs_user_path):
            logger.debug(f'Resolved path {abs_user_path}')

            # Remove path prefix if one was configured
            if prefix and abs_user_path.startswith(prefix):
                abs_user_path = abs_user_path.replace(prefix, "")

                # Trim any leading slash if one was left after removing prefix
                if abs_user_path.startswith("/"):
                    abs_user_path = abs_user_path[1:]

                logger.debug(f"Removed prefix {prefix}, new path: {abs_user_path}")

            resolved_paths.append(abs_user_path)
        elif os.path.isdir(abs_user_path):
            logger.debug(f'Resolving directory {abs_user_path}')
            for grouping in os.walk(abs_user_path, topdown=True):
                dirpath, _, filenames = grouping

                # TODO: add option to include hidden files
                # TODO: add support for include/exclude path filters
                product_paths = [
                    os.path.join(dirpath, filename)
                    for filename in filter(lambda name: not name.startswith('.'), filenames)
                ]

                resolved_paths = resolve_ingress_paths(
                    product_paths, resolved_paths, prefix=prefix
                )
        else:
            logger.warning(
                f"Encountered path ({abs_user_path}) that is neither a file nor "
                f"directory, skipping..."
            )

    return resolved_paths


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

    params = {"node": node_id, "node_name": NodeUtil.node_id_to_long_name[node_id]}
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

    """
    # TODO: create module to perform logger setup based on INI setting/user arg
    logging.basicConfig(level=logging.DEBUG)

    parser = setup_argparser()

    args = parser.parse_args()

    config = ConfigUtil.get_config(args.config_path)

    # Derive the full list of ingress paths based on the set of paths requested
    # by the user
    resolved_ingress_paths = resolve_ingress_paths(
        args.ingress_paths, prefix=args.prefix
    )

    node_id = args.node

    if not args.dry_run:
        for resolved_ingress_path in resolved_ingress_paths:
            s3_ingress_uri = request_file_for_ingress(
                resolved_ingress_path, node_id, config["API_GATEWAY"]
            )

            ingress_file_to_s3(resolved_ingress_path, s3_ingress_uri)
    else:
        logger.info("Dry run requested, skipping ingress request submission.")


if __name__ == '__main__':
    main()

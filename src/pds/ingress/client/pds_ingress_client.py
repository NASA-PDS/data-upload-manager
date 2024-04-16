#!/usr/bin/env python3
"""
==================
pds_ingress_client
==================

Client side script used to perform ingress request to the DUM service in AWS.
"""
import argparse
import hashlib
import json
import os

import backoff
import pds.ingress.util.log_util as log_util
import requests
from joblib import delayed
from joblib import Parallel
from pds.ingress.util.auth_util import AuthUtil
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.log_util import get_log_level
from pds.ingress.util.log_util import get_logger
from pds.ingress.util.node_util import NodeUtil
from pds.ingress.util.path_util import PathUtil

PARALLEL = Parallel(require="sharedmem")


def fatal_code(err: requests.exceptions.RequestException) -> bool:
    """Only retry for common transient errors"""
    return 400 <= err.response.status_code < 500


def backoff_logger(details):
    """Log details about the current backoff/retry"""
    logger = get_logger(__name__)
    logger.warning(
        f"Backing off {details['target']} function for {details['wait']:0.1f} "
        f"seconds after {details['tries']} tries."
    )
    logger.warning(f"Total time elapsed: {details['elapsed']:0.1f} seconds.")


def _perform_ingress(ingress_path, node_id, prefix, bearer_token, api_gateway_config):
    """
    Performs an ingress request and transfer to S3 using credentials obtained from
    Cognito. This helper function is intended for use with a Joblib parallelized
    loop.

    Parameters
    ----------
    ingress_path : str
        Path to the file to request ingress for.
    node_id : str
        The PDS Node Identifier to associate with the ingress request.
    prefix : str
        Global path prefix to trim from the ingress path before making the
        ingress request.
    bearer_token : str
        JWT Bearer token string obtained from a successful authentication to
        Cognito.
    api_gateway_config : dict
        Dictionary containing configuration details for the API Gateway instance
        used to request ingress.

    """
    logger = get_logger(__name__)

    # TODO: slurping entire file could be problematic for large files,
    #       investigate alternative if/when necessary
    with open(ingress_path, "rb") as object_file:
        object_body = object_file.read()

    # Remove path prefix if one was configured
    trimmed_path = PathUtil.trim_ingress_path(ingress_path, prefix)

    try:
        s3_ingress_url = request_file_for_ingress(object_body, trimmed_path, node_id, api_gateway_config, bearer_token)

        ingress_file_to_s3(object_body, trimmed_path, s3_ingress_url)
    except Exception as err:
        # Only log the error as a warning, so we don't bring down the entire
        # transfer process
        logger.warning(f"{trimmed_path} : Ingress failed, reason: {str(err)}")


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
    on_backoff=backoff_logger,
    interval=15,
)
def request_file_for_ingress(object_body, ingress_file_path, node_id, api_gateway_config, bearer_token):
    """
    Submits a request for file ingress to the PDS Ingress App API.

    Parameters
    ----------
    object_body : bytes
        Contents of the file to be copied to S3.
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
    s3_ingress_url : str
        The presigned S3 URL returned from the Ingress service lambda, which
        identifies the location in S3 the client should upload the file to and
        includes temporary credentials to allow the client to upload to
        S3 via an HTTP PUT.

    Raises
    ------
    RuntimeError
        If the request to the Ingress Service fails.

    """
    logger = get_logger(__name__)

    logger.info(f"{ingress_file_path} : Requesting ingress for node ID {node_id}")

    # Extract the API Gateway configuration params
    api_gateway_template = api_gateway_config["url_template"]
    api_gateway_id = api_gateway_config["id"]
    api_gateway_region = api_gateway_config["region"]
    api_gateway_stage = api_gateway_config["stage"]
    api_gateway_resource = api_gateway_config["resource"]

    api_gateway_url = api_gateway_template.format(
        id=api_gateway_id, region=api_gateway_region, stage=api_gateway_stage, resource=api_gateway_resource
    )

    # Calculate the MD5 checksum of the file payload
    md5_digest = hashlib.md5(object_body).hexdigest()

    # Get the size and last modified time of the file
    file_size = os.stat(ingress_file_path).st_size
    last_modified_time = os.path.getmtime(ingress_file_path)

    params = {"node": node_id, "node_name": NodeUtil.node_id_to_long_name[node_id]}
    payload = {"url": ingress_file_path}
    headers = {
        "Authorization": bearer_token,
        "UserGroup": NodeUtil.node_id_to_group_name(node_id),
        "ContentMD5": md5_digest,
        "ContentLength": str(file_size),
        "LastModified": str(last_modified_time),
        "content-type": "application/json",
        "x-amz-docs-region": api_gateway_region,
    }

    response = requests.post(api_gateway_url, params=params, data=json.dumps(payload), headers=headers)
    response.raise_for_status()

    s3_ingress_url = json.loads(response.text)

    logger.debug(f"{ingress_file_path} : Got URL for ingress path {s3_ingress_url.split('?')[0]}")

    return s3_ingress_url


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
    on_backoff=backoff_logger,
    interval=15,
)
def ingress_file_to_s3(object_body, trimmed_path, s3_ingress_url):
    """
    Copies the local file path to the S3 location returned from the Ingress App.

    Parameters
    ----------
    object_body : bytes
        Contents of the file to be copied to S3.
    trimmed_path : str
        Trimmed version of the ingress file path. Used for logging purposes.
    s3_ingress_url : str
        The presigned S3 URL used for upload returned from the Ingress Service
        Lambda function.

    Raises
    ------
    RuntimeError
        If the S3 upload fails for any reason.

    """
    logger = get_logger(__name__)

    logger.info(f"{trimmed_path} : Ingesting to {s3_ingress_url.split('?')[0]}")

    response = requests.put(s3_ingress_url, data=object_body)
    response.raise_for_status()

    logger.info(f"{trimmed_path} : Ingest complete")


def setup_argparser():
    """
    Helper function to perform setup of the ArgumentParser for the Ingress client
    script.

    Returns
    -------
    parser : argparse.ArgumentParser
        The command-line argument parser for use with the pds-ingress-client
        script.

    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument(
        "-c",
        "--config-path",
        type=str,
        default=None,
        help=f"Path to the INI config for use with this client. "
        f"If not provided, the default config "
        f"({ConfigUtil.default_config_path()}) is used.",
    )
    parser.add_argument(
        "-n",
        "--node",
        type=str.lower,
        required=True,
        choices=NodeUtil.permissible_node_ids(),
        help="PDS node identifier of the ingress requestor. "
        "This value is used by the Ingress service to derive "
        "the S3 upload location. Argument is case-insensitive.",
    )
    parser.add_argument(
        "--prefix",
        "-p",
        type=str,
        default=None,
        help="Specify a path prefix to be trimmed from each "
        "resolved ingest path such that is is not included "
        "with the request to the Ingress Service. "
        'For example, specifying --prefix "/home/user" would '
        'modify paths such as "/home/user/bundle/file.xml" '
        'to just "bundle/file.xml". This can be useful for '
        "controlling which parts of a directory structure "
        "should be included with the S3 upload location returned "
        "by the Ingress Service.",
    )
    parser.add_argument(
        "--num-threads",
        "-t",
        type=int,
        default=-1,
        help="Specify the number of threads to use when uploading "
        "files to S3 in parallel. By default, all available "
        "cores are used.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Derive the full set of ingress paths without " "performing any submission requests to the server.",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        default=None,
        choices=["warn", "warning", "info", "debug"],
        help="Sets the Logging level for logged messages. If not "
        "provided, the logging level set in the INI config "
        "is used instead.",
    )
    parser.add_argument(
        "ingress_paths",
        type=str,
        nargs="+",
        metavar="file_or_dir",
        help="One or more paths to the files to ingest to S3. "
        "For each directory path is provided, this script will "
        "automatically derive all sub-paths for inclusion with "
        "the ingress request.",
    )

    return parser


def main():
    """
    Main entry point for the pds-ingress-client script.

    Raises
    ------
    ValueError
        If a username and password are not defined within the parsed config,
        and dry-run is not enabled.

    """
    parser = setup_argparser()

    args = parser.parse_args()

    config = ConfigUtil.get_config(args.config_path)

    logger = get_logger(__name__, log_level=get_log_level(args.log_level))

    logger.info(f"Loaded config file {args.config_path}")

    # Derive the full list of ingress paths based on the set of paths requested
    # by the user
    resolved_ingress_paths = PathUtil.resolve_ingress_paths(args.ingress_paths)

    node_id = args.node

    if not args.dry_run:
        cognito_config = config["COGNITO"]

        # TODO: add support for command-line username/password?
        if not cognito_config["username"] and cognito_config["password"]:
            raise ValueError("Username and Password must be specified in the COGNITO portion of the INI config")

        authentication_result = AuthUtil.perform_cognito_authentication(cognito_config)

        bearer_token = AuthUtil.create_bearer_token(authentication_result)

        # Set the bearer token on the CloudWatchHandler singleton, so it can
        # be used to authenticate submissions to the CloudWatch Logs API endpoint
        log_util.CLOUDWATCH_HANDLER.bearer_token = bearer_token
        log_util.CLOUDWATCH_HANDLER.node_id = node_id

        # Perform uploads in parallel using the number of requested threads
        PARALLEL.n_jobs = args.num_threads

        PARALLEL(
            delayed(_perform_ingress)(resolved_ingress_path, node_id, args.prefix, bearer_token, config["API_GATEWAY"])
            for resolved_ingress_path in resolved_ingress_paths
        )

        # Flush all logged statements to CloudWatch Logs
        log_util.CLOUDWATCH_HANDLER.flush()
    else:
        logger.info("Dry run requested, skipping ingress request submission.")


if __name__ == "__main__":
    main()

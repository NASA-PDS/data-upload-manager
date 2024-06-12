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
import sched
import time
from datetime import datetime
from datetime import timezone
from threading import Thread

import backoff
import pds.ingress.util.log_util as log_util
import requests
from joblib import delayed
from joblib import Parallel
from pds.ingress import __version__
from pds.ingress.util.auth_util import AuthUtil
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.log_util import get_log_level
from pds.ingress.util.log_util import get_logger
from pds.ingress.util.node_util import NodeUtil
from pds.ingress.util.path_util import PathUtil

BEARER_TOKEN = None
"""Placeholder for authentication bearer token used to authenticate to API gateway"""

PARALLEL = Parallel(require="sharedmem")

REFRESH_SCHEDULER = sched.scheduler(time.time, time.sleep)
"""Scheduler object used to periodically refresh the Cognito authentication token"""

SUMMARY_TABLE = {
    "uploaded": set(),
    "skipped": set(),
    "failed": set(),
    "transferred": 0,
    "start_time": time.time(),
    "end_time": None,
}
"""Stores the information for use with the Summary report"""


def fatal_code(err: requests.exceptions.RequestException) -> bool:
    """Only retry for common transient errors"""
    if err.response is not None:
        return 400 <= err.response.status_code < 500
    else:
        # No response to interrogate, so default to no retry
        return True


def backoff_logger(details):
    """Log details about the current backoff/retry"""
    logger = get_logger(__name__)
    logger.warning(
        f"Backing off {details['target']} function for {details['wait']:0.1f} "
        f"seconds after {details['tries']} tries."
    )
    logger.warning(f"Total time elapsed: {details['elapsed']:0.1f} seconds.")


def _perform_ingress(ingress_path, node_id, prefix, force_overwrite, api_gateway_config):
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
    force_overwrite : bool
        Determines whether pre-existing versions of files on S3 should be
        overwritten or not.
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
        s3_ingress_url = request_file_for_ingress(
            object_body, ingress_path, trimmed_path, node_id, force_overwrite, api_gateway_config
        )

        if s3_ingress_url:
            ingress_file_to_s3(object_body, ingress_path, trimmed_path, s3_ingress_url)
            SUMMARY_TABLE["uploaded"].add(trimmed_path)
        else:
            SUMMARY_TABLE["skipped"].add(trimmed_path)
    except Exception as err:
        # Only log the error as a warning, so we don't bring down the entire
        # transfer process
        reason = err.response.json() if isinstance(err, requests.exceptions.HTTPError) else str(err)
        logger.warning(f"{trimmed_path} : Ingress failed, reason: {reason}")
        SUMMARY_TABLE["failed"].add(trimmed_path)
    finally:
        logger.debug(f"Deallocating memory for {trimmed_path} ({len(object_body)} bytes)")
        del object_body


def _schedule_token_refresh(refresh_token, token_expiration, offset=60):
    """
    Schedules a refresh of the Cognito authentication token using the provided
    refresh token. This function is inteded to be executed with a separate daemon
    thread to prevent blocking on the main thread.

    Parameters
    ----------
    refresh_token : str
        The refresh token provided by Cognito.
    token_expiration : int
        Time in seconds before the current authentication token is expected to
        expire.
    offset : int, optional
        Offset in seconds to subtract from the token expiration duration to ensure
        a refresh occurs some time before the expiration deadline. Defaults to
        60 seconds.

    """
    # Offset the expiration, so we refresh a bit ahead of time
    delay = max(token_expiration - offset, offset)

    REFRESH_SCHEDULER.enter(delay, priority=1, action=_token_refresh_event, argument=(refresh_token,))

    # Kick off scheduler
    # Since this function should be running in a seperate thread, it should be
    # safe to block until the scheduler fires the next refresh event
    REFRESH_SCHEDULER.run(blocking=True)


def _token_refresh_event(refresh_token):
    """
    Callback event evoked when refresh scheduler kicks off a Cognito token refresh.
    This function will submit the refresh request to Cognito, and if successful,
    schedules the next refresh interval.

    Parameters
    ----------
    refresh_token : str
        The refresh token provided by Cognito.

    """
    global BEARER_TOKEN

    logger = get_logger(__name__)

    logger.debug("_token_refresh_event fired")

    config = ConfigUtil.get_config()

    cognito_config = config["COGNITO"]

    # Submit the token refresh request via boto3
    authentication_result = AuthUtil.refresh_auth_token(cognito_config, refresh_token)

    # Update the authentication token referenced by each ingress worker thread,
    # as well as the Cloudwatch logger
    BEARER_TOKEN = AuthUtil.create_bearer_token(authentication_result)
    log_util.CLOUDWATCH_HANDLER.bearer_token = BEARER_TOKEN

    # Schedule the next refresh iteration
    expiration = authentication_result["ExpiresIn"]

    _schedule_token_refresh(refresh_token, expiration)


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
    on_backoff=backoff_logger,
    interval=15,
)
def request_file_for_ingress(object_body, ingress_path, trimmed_path, node_id, force_overwrite, api_gateway_config):
    """
    Submits a request for file ingress to the PDS Ingress App API.

    Parameters
    ----------
    object_body : bytes
        Contents of the file to be copied to S3.
    ingress_path : str
        Local path to the file to request ingress for.
    trimmed_path : str
        Ingress path with any user-configured prefix removed
    node_id : str
        PDS node identifier.
    force_overwrite : bool
        Determines whether pre-existing versions of files on S3 should be
        overwritten or not.
    api_gateway_config : dict
        Dictionary or dictionary-like containing key/value pairs used to
        configure the API Gateway endpoint url.

    Returns
    -------
    s3_ingress_url : str
        The presigned S3 URL returned from the Ingress service lambda, which
        identifies the location in S3 the client should upload the file to and
        includes temporary credentials to allow the client to upload to
        S3 via an HTTP PUT. If this file already exists in S3 and should not
        be overwritten, this function will return None instead.

    Raises
    ------
    RuntimeError
        If the request to the Ingress Service fails.

    """
    global BEARER_TOKEN

    logger = get_logger(__name__)

    logger.info(f"{trimmed_path} : Requesting ingress for node ID {node_id}")

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
    file_size = os.stat(ingress_path).st_size
    last_modified_time = os.path.getmtime(ingress_path)

    params = {"node": node_id, "node_name": NodeUtil.node_id_to_long_name[node_id]}
    payload = {"url": trimmed_path}
    headers = {
        "Authorization": BEARER_TOKEN,
        "UserGroup": NodeUtil.node_id_to_group_name(node_id),
        "ContentMD5": md5_digest,
        "ContentLength": str(file_size),
        "LastModified": str(last_modified_time),
        "ForceOverwrite": str(int(force_overwrite)),
        "ClientVersion": __version__,
        "content-type": "application/json",
        "x-amz-docs-region": api_gateway_region,
    }

    response = requests.post(api_gateway_url, params=params, data=json.dumps(payload), headers=headers)
    response.raise_for_status()

    # Ingress request successful
    if response.status_code == 200:
        s3_ingress_url = json.loads(response.text)

        logger.debug(f"{trimmed_path} : Got URL for ingress path {s3_ingress_url.split('?')[0]}")

        return s3_ingress_url
    # Ingress service indiciates file already exists in S3 and should not be overwritten
    elif response.status_code == 204:
        logger.info(f"{trimmed_path} : File already exists unchanged on S3, skipping ingress")

        return None
    else:
        raise RuntimeError(f"Unexpected status code ({response.status_code}) returned from ingress request")


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=300,
    giveup=fatal_code,
    on_backoff=backoff_logger,
    interval=15,
)
def ingress_file_to_s3(object_body, ingress_path, trimmed_path, s3_ingress_url):
    """
    Copies the local file path to the S3 location returned from the Ingress App.

    Parameters
    ----------
    object_body : bytes
        Contents of the file to be copied to S3.
    ingress_path : str
        Local path to the file to be ingressed.
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

    # Update total number of bytes transferrred
    SUMMARY_TABLE["transferred"] += os.stat(ingress_path).st_size


def print_ingress_summary():
    """Prints the summary report for last execution of the client script."""
    logger = get_logger(__name__)

    num_uploaded = len(SUMMARY_TABLE["uploaded"])
    num_skipped = len(SUMMARY_TABLE["skipped"])
    num_failed = len(SUMMARY_TABLE["failed"])
    start_time = SUMMARY_TABLE["start_time"]
    end_time = SUMMARY_TABLE["end_time"]
    transferred = SUMMARY_TABLE["transferred"]

    title = f"Ingress Summary Report for {str(datetime.now())}"

    logger.info(title)
    logger.info("-" * len(title))
    logger.info("Uploaded: %d file(s)", num_uploaded)
    logger.info("Skipped: %d file(s)", num_skipped)
    logger.info("Failed: %d file(s)", num_failed)
    logger.info("Total: %d files(s)", num_uploaded + num_skipped + num_failed)
    logger.info("Time elapsed: %.2f seconds", end_time - start_time)
    logger.info("Bytes tranferred: %d", transferred)


def create_report_file(args):
    """
    Writes a detailed report for the last transfer in JSON format to disk.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command-line arguments, including the path to write the
        summary report to. A listing of all provided arguments is included in
        the report file.

    """
    logger = get_logger(__name__)

    report = {
        "Arguments": str(args),
        "Start Time": str(datetime.fromtimestamp(SUMMARY_TABLE["start_time"], tz=timezone.utc)),
        "Finish Time": str(datetime.fromtimestamp(SUMMARY_TABLE["end_time"], tz=timezone.utc)),
        "Uploaded": list(sorted(SUMMARY_TABLE["uploaded"])),
        "Total Uploaded": len(SUMMARY_TABLE["uploaded"]),
        "Skipped": list(sorted(SUMMARY_TABLE["skipped"])),
        "Total Skipped": len(SUMMARY_TABLE["skipped"]),
        "Failed": list(sorted(SUMMARY_TABLE["failed"])),
        "Total Failed": len(SUMMARY_TABLE["failed"]),
        "Bytes Transferred": SUMMARY_TABLE["transferred"],
    }

    report["Total Files"] = report["Total Uploaded"] + report["Total Skipped"] + report["Total Failed"]

    try:
        logger.info("Writing JSON summary report to %s", args.report_path)
        with open(args.report_path, "w") as outfile:
            json.dump(report, outfile, indent=4)
    except OSError as err:
        logger.warning("Failed to write summary report to %s, reason: %s", args.report_path, str(err))


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
        "--force-overwrite",
        "-f",
        action="store_true",
        help="By default, the DUM service determines if a given file has already been "
        "ingested to the PDS Cloud and has not changed. If so, ingress of the "
        "file is skipped. Use this flag to override this behavior and forcefully "
        "overwrite any existing versions of files within the PDS Cloud.",
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
        "--report-path",
        "-r",
        type=str,
        default=None,
        help="Specify a path to write a JSON summary report containing "
        "the full listing of all files ingressed, skipped or failed. "
        "By default, no report is created.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Derive the full set of ingress paths without performing any submission requests to the server.",
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
        "--version",
        action="version",
        version=f"Data Upload Manager v{__version__}",
        help="Print the Data Upload Manager release version and exit.",
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
    global BEARER_TOKEN

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

        BEARER_TOKEN = AuthUtil.create_bearer_token(authentication_result)

        # Set the bearer token on the CloudWatchHandler singleton, so it can
        # be used to authenticate submissions to the CloudWatch Logs API endpoint
        log_util.CLOUDWATCH_HANDLER.bearer_token = BEARER_TOKEN
        log_util.CLOUDWATCH_HANDLER.node_id = node_id

        # Schedule automatic refresh of the Cognito token prior to expiration within
        # a separate thread. Since this thread will not allocate any
        # resources, we can designate the thread as a daemon, so it will not
        # preempt completion of the main thread.
        refresh_thread = Thread(
            target=_schedule_token_refresh,
            name="token_refresh",
            args=(authentication_result["RefreshToken"], authentication_result["ExpiresIn"]),
            daemon=True,
        )
        refresh_thread.start()

        # Perform uploads in parallel using the number of requested threads
        PARALLEL.n_jobs = args.num_threads

        PARALLEL(
            delayed(_perform_ingress)(
                resolved_ingress_path, node_id, args.prefix, args.force_overwrite, config["API_GATEWAY"]
            )
            for resolved_ingress_path in resolved_ingress_paths
        )

        # Capture completion time of transfer
        SUMMARY_TABLE["end_time"] = time.time()

        # Print the summary table
        print_ingress_summary()

        # Create the JSON report file, if requested
        if args.report_path:
            create_report_file(args)

        # Flush all logged statements to CloudWatch Logs
        log_util.CLOUDWATCH_HANDLER.flush()
    else:
        logger.info("Dry run requested, skipping ingress request submission.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
==================
pds_ingress_client
==================

Client side script used to perform ingress request to the DUM service in AWS.
"""
import argparse
import json
import os
import sched
import sys
import time
from collections import defaultdict
from datetime import datetime
from datetime import timezone
from http import HTTPStatus
from itertools import chain
from threading import Thread

import backoff
import pds.ingress.util.log_util as log_util
import requests
from joblib import delayed
from joblib import Parallel
from more_itertools import chunked as batched
from pds.ingress import __version__
from pds.ingress.util.auth_util import AuthUtil
from pds.ingress.util.backoff_util import fatal_code
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.hash_util import md5_for_path
from pds.ingress.util.log_util import get_log_level
from pds.ingress.util.log_util import get_logger
from pds.ingress.util.node_util import NodeUtil
from pds.ingress.util.path_util import PathUtil
from pds.ingress.util.progress_util import close_batch_progress_bars
from pds.ingress.util.progress_util import get_available_batch_progress_bar
from pds.ingress.util.progress_util import get_ingress_total_progress_bar
from pds.ingress.util.progress_util import get_manifest_progress_bar
from pds.ingress.util.progress_util import get_path_progress_bar
from pds.ingress.util.progress_util import get_upload_progress_bar_for_batch
from pds.ingress.util.progress_util import init_batch_progress_bars
from pds.ingress.util.progress_util import release_batch_progress_bar
from requests.exceptions import RequestException
from tqdm.utils import CallbackIOWrapper

BEARER_TOKEN = None
"""Placeholder for authentication bearer token used to authenticate to API gateway"""

PARALLEL = Parallel(require="sharedmem")
"""Joblib backend used to parallelize the various for-loops within this script"""

REFRESH_SCHEDULER = sched.scheduler(time.time, time.sleep)
"""Scheduler object used to periodically refresh the Cognito authentication token"""

SUMMARY_TABLE = dict()
"""Stores the information for use with the Summary report"""

MANIFEST = dict()
"""Stores the file ingress manifest within memory"""

EXPECTED_MANIFEST_KEYS = ("ingress_path", "md5", "size", "last_modified")
"""The keys we expect to find assigned to each mapping within a read manifest"""


def initialize_summary_table():
    """Initialzes the global summary table to its default state."""
    global SUMMARY_TABLE

    SUMMARY_TABLE = {
        "uploaded": defaultdict(set),
        "skipped": defaultdict(set),
        "failed": defaultdict(set),
        "transferred": 0,
        "start_time": time.time(),
        "end_time": None,
        "batch_size": 0,
        "num_batches": 0,
    }


def prepare_batches(batched_ingress_paths, prefix):
    """
    Prepares each batch of files for ingress in parallel via the joblib library.

    Parameters
    ----------
    batched_ingress_paths : list of lists
        List containing all ingress file requests separated into equal batches.
    prefix : str
        Path prefix value to trim from each ingress path to derive the path
        structure to be used in S3.

    Returns
    -------
    request_batches : list of list
        The provided request batches, augmented with information required to
        perform each batch ingress request.

    """
    logger = get_logger("prepare_batches")

    try:
        with get_manifest_progress_bar(total=len(batched_ingress_paths)) as pbar:
            request_batches = PARALLEL(
                (
                    delayed(_prepare_batch_for_ingress)(ingress_path_batch, prefix, batch_index, pbar)
                    for batch_index, ingress_path_batch in enumerate(batched_ingress_paths)
                ),
            )
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt received, halting ingress...")
        sys.exit(1)  # Give up any further processing, including generation of report file

    return request_batches


def perform_ingress(request_batches, node_id, force_overwrite, api_gateway_config):
    """
    Performs an ingress request and transfer to S3 using credentials obtained
    from Cognito.

    Parameters
    ----------
    request_batches : list of iterables
        Paths to the files to request ingress for, divided into batches sized
        based on the configured batch size.
    node_id : str
        The PDS Node Identifier to associate with the ingress request.
    force_overwrite : bool
        Determines whether pre-existing versions of files on S3 should be
        overwritten or not.
    api_gateway_config : dict
        Dictionary containing configuration details for the API Gateway instance
        used to request ingress.

    """
    logger = get_logger("perform_ingress")

    try:
        with get_ingress_total_progress_bar(total=len(request_batches)) as pbar:
            PARALLEL(
                (
                    delayed(_process_batch)(
                        batch_index, request_batch, node_id, force_overwrite, api_gateway_config, pbar
                    )
                    for batch_index, request_batch in enumerate(request_batches)
                ),
            )
    except KeyboardInterrupt:
        logger.warning("Keyboard interrupt received, halting ingress...")
        return  # return so we can still output a report file


def _process_batch(batch_index, request_batch, node_id, force_overwrite, api_gateway_config, total_pbar):
    """
    Performs the steps to process a single batch of ingress requests.
    This helper function is intended for use with a Joblib parallelized loop.

    Parameters
    ----------
    batch_index : int
        Index of the batch to be processed within the full list of batches.
    request_batch : list
        Single batch of to the files to request ingress for, sized based on the
        configured batch size.
    node_id : str
        The PDS Node Identifier to associate with the ingress request.
        ingress request.
    force_overwrite : bool
        Determines whether pre-existing versions of files on S3 should be
        overwritten or not.
    api_gateway_config : dict
        Dictionary containing configuration details for the API Gateway instance
        used to request ingress.
    total_pbar : tqdm.tqdm_asyncio
        Total Ingress progress bar to update once the current batch has been
        fully processed.

    """
    logger = get_logger("_process_batch", console=False)

    # Get an avaialble Batch progress bar to update while iterating through this
    # current batch
    batch_pbar = get_available_batch_progress_bar(total=len(request_batch), desc=f"Batch index {batch_index}")

    try:
        response_batch = request_batch_for_ingress(
            request_batch, batch_index, node_id, force_overwrite, api_gateway_config
        )

        for ingress_response in response_batch:
            try:
                ingress_file_to_s3(ingress_response, batch_index, batch_pbar)
                batch_pbar.update()
            except RequestException as err:
                # If here, the HTTP request error was unrecoverable by a backoff/retry
                trimmed_path = ingress_response.get("trimmed_path")
                SUMMARY_TABLE["failed"][batch_index].add(trimmed_path)

                logger.error(
                    "Batch %d : Ingress failed for %s, HTTP code: %s\n HTTP response text:\n%s",
                    batch_index,
                    trimmed_path,
                    str(err.response.status_code) if err.response else "None",
                    err.response.text if err.response else "None",
                )
    except Exception as err:
        logger.error("Ingress failed, reason: %s", str(err))
        raise
    finally:
        total_pbar.update()
        release_batch_progress_bar(batch_pbar)


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

    logger = get_logger("_token_refresh_event", console=False, cloudwatch=False)

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


def _prepare_batch_for_ingress(ingress_path_batch, prefix, batch_index, batch_pbar):
    """
    Performs information gathering on each file contained within an ingress
    request batch, including file size, last modified time, and MD5 hash.

    Parameters
    ----------
    ingress_path_batch : list of str
        List of the files to gather information on prior to ingress request.
    prefix : str
        Path prefix to remove from each path in the provided batch.
    batch_index : int
        Index of the current batch within the full list of batched paths.
    batch_pbar : tqdm.tqdm_asyncio
        Batch progress bar associated to the batch to be ingressed.

    Returns
    -------
    request_batch : list of dict
        List of dictionaries, with one entry for each file path in the provided
        request batch. Each dictionary contains the information gathered about
        the file.

    """
    global MANIFEST

    logger = get_logger("_prepare_batch_for_ingress", console=False)

    logger.info("Batch %d : Preparing for ingress", batch_index)
    start_time = time.time()

    request_batch = []

    for ingress_path in ingress_path_batch:
        # Remove path prefix if one was configured
        trimmed_path = PathUtil.trim_ingress_path(ingress_path, prefix)

        if trimmed_path in MANIFEST:
            # Pull file data from pre-existing manifest
            manifest_entry = MANIFEST[trimmed_path]
            md5_digest = manifest_entry["md5"]
            file_size = manifest_entry["size"]
            last_modified_time = time.mktime(datetime.fromisoformat(manifest_entry["last_modified"]).timetuple())
        else:
            # Calculate the MD5 checksum of the file payload
            md5_digest = md5_for_path(ingress_path).hexdigest()

            # Get the size and last modified time of the file
            file_size = os.stat(ingress_path).st_size
            last_modified_time = os.path.getmtime(ingress_path)

            # Update manifest with new entry
            MANIFEST[trimmed_path] = {
                "ingress_path": ingress_path,
                "md5": md5_digest,
                "size": file_size,
                "last_modified": datetime.fromtimestamp(last_modified_time, tz=timezone.utc).isoformat(),
            }

        request_batch.append(
            {
                "ingress_path": ingress_path,
                "trimmed_path": trimmed_path,
                "md5": md5_digest,
                "size": file_size,
                "last_modified": last_modified_time,
            }
        )

    batch_pbar.update()
    elapsed_time = time.time() - start_time
    logger.info("Batch %d : Prep completed in %.2f seconds", batch_index, elapsed_time)

    return request_batch


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=60,
    giveup=fatal_code,
    logger="request_batch_for_ingress",
    interval=15,
)
def request_batch_for_ingress(request_batch, batch_index, node_id, force_overwrite, api_gateway_config):
    """
    Submits a batch of ingress requests to the PDS Ingress App API.

    Parameters
    ----------
    request_batch : list of dict
        List of dictionaries containing an entry for each file to request ingest for.
        Each entry contains information about the file to be ingested.
    batch_index : int
        Index of the current batch within the full list of batched paths.
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
    response_batch : list of dict
        The list of responses from the Ingress Lambda service.

    """
    global BEARER_TOKEN

    logger = get_logger("request_batch_for_ingress", console=False)

    logger.info("Batch %d : Requesting ingress", batch_index)
    start_time = time.time()

    # Extract the API Gateway configuration params
    api_gateway_template = api_gateway_config["url_template"]
    api_gateway_id = api_gateway_config["id"]
    api_gateway_region = api_gateway_config["region"]
    api_gateway_stage = api_gateway_config["stage"]
    api_gateway_resource = api_gateway_config["resource"]

    api_gateway_url = api_gateway_template.format(
        id=api_gateway_id, region=api_gateway_region, stage=api_gateway_stage, resource=api_gateway_resource
    )

    params = {"node": node_id, "node_name": NodeUtil.node_id_to_long_name[node_id]}
    headers = {
        "Authorization": BEARER_TOKEN,
        "UserGroup": NodeUtil.node_id_to_group_name(node_id),
        "ForceOverwrite": str(int(force_overwrite)),
        "ClientVersion": __version__,
        "content-type": "application/json",
        "x-amz-docs-region": api_gateway_region,
    }

    response = requests.post(
        api_gateway_url, params=params, data=json.dumps(request_batch), headers=headers, timeout=600
    )
    elapsed_time = time.time() - start_time

    # Ingress request successful
    if response.status_code == HTTPStatus.OK:
        response_batch = response.json()

        logger.info("Batch %d : Ingress request completed in %.2f seconds", batch_index, elapsed_time)

        return response_batch
    else:
        response.raise_for_status()


@backoff.on_exception(
    backoff.constant,
    requests.exceptions.RequestException,
    max_time=60,
    giveup=fatal_code,
    logger="ingress_file_to_s3",
    interval=15,
)
def ingress_file_to_s3(ingress_response, batch_index, batch_pbar):
    """
    Copies the local file path using the pre-signed S3 URL returned from the
    Ingress Lambda App.

    Parameters
    ----------
    ingress_response : dict
        Dictionary containing the information returned from the Ingress Lambda
        App required to upload the local file to S3.
    batch_index : int
        Index of the batch that the ingressed file was assigned to. Used for
        tracking within the summary table.
    batch_pbar : tqdm.tqdm_asyncio
        The Batch progress bar instance used to obtain the corresponding File
        Upload progress sub-bar.

    Raises
    ------
    RuntimeError
        If an unexpected response is received from the Ingress Lambda app.

    """
    logger = get_logger("ingress_file_to_s3", console=False)

    response_result = int(ingress_response.get("result", -1))
    trimmed_path = ingress_response.get("trimmed_path")

    if response_result == HTTPStatus.OK:
        s3_ingress_url = ingress_response.get("s3_url")

        logger.info("Batch %d : Ingesting %s to %s", batch_index, trimmed_path, s3_ingress_url.split("?")[0])

        ingress_path = ingress_response.get("ingress_path")

        if not ingress_path:
            raise ValueError("No ingress path provided with response for %s", trimmed_path)

        # Include the base64-encoded MD5 hash so AWS can perform its own
        # integrity check on the uploaded file
        headers = {"Content-MD5": ingress_response.get("base64_md5")}

        # Initialize the file upload progress subbar attached to the batch progress bar
        upload_pbar = get_upload_progress_bar_for_batch(
            batch_pbar, total=os.stat(ingress_path).st_size, filename=os.path.basename(ingress_path)
        )

        with open(ingress_path, "rb") as infile:
            # Wrap file I/O with our upload bar to automatically track file upload progress
            wrapped_file = CallbackIOWrapper(upload_pbar.update, infile, "read")
            response = requests.put(s3_ingress_url, data=wrapped_file, headers=headers)
            response.raise_for_status()

        logger.info("Batch %d : %s Ingest complete", batch_index, trimmed_path)
        SUMMARY_TABLE["uploaded"][batch_index].add(trimmed_path)

        # Update total number of bytes transferrred
        SUMMARY_TABLE["transferred"] += os.stat(ingress_path).st_size
    elif response_result == HTTPStatus.NO_CONTENT:
        logger.info(
            "Batch %d : Skipping ingress for %s, reason %s", batch_index, trimmed_path, ingress_response.get("message")
        )
        SUMMARY_TABLE["skipped"][batch_index].add(trimmed_path)
    elif response_result == HTTPStatus.NOT_FOUND:
        logger.warning(
            "Batch %d : Ingress failed for %s, reason: %s", batch_index, trimmed_path, ingress_response.get("message")
        )
        SUMMARY_TABLE["failed"][batch_index].add(trimmed_path)
    else:
        logger.error("Batch %d : Unexepected response code (%d) from Ingress service", batch_index, response_result)
        raise RuntimeError


def print_ingress_summary():
    """Prints the summary report for last execution of the client script."""
    logger = get_logger("print_ingress_summary")

    num_uploaded = sum(len(batch) for batch in SUMMARY_TABLE["uploaded"].values())
    num_skipped = sum(len(batch) for batch in SUMMARY_TABLE["skipped"].values())
    num_failed = sum(len(batch) for batch in SUMMARY_TABLE["failed"].values())
    start_time = SUMMARY_TABLE["start_time"]
    end_time = SUMMARY_TABLE["end_time"]
    transferred = SUMMARY_TABLE["transferred"]

    title = f"Ingress Summary Report for {str(datetime.now())}"

    logger.info("")  # Blank line to distance report from any progress bar cleanup
    logger.info(title)
    logger.info("-" * len(title))
    logger.info("Uploaded: %d file(s)", num_uploaded)
    logger.info("Skipped: %d file(s)", num_skipped)
    logger.info("Failed: %d file(s)", num_failed)
    logger.info("Total: %d files(s)", num_uploaded + num_skipped + num_failed)
    logger.info("Time elapsed: %.2f seconds", end_time - start_time)
    logger.info("Bytes tranferred: %d", transferred)


def read_manifest_file(manifest_path):
    """
    Reads manifest contents, including file checksums, from the provided
    path. The contents of the read manifest will be used to supply file information
    for any files in the current request which are already specified within the
    read manifest.

    Notes
    -----
    This function also validates the contents of the read manifest to ensure
    the contents conform to the format expected by this version of the DUM client.
    If the read manifest does not conform, it's contents are discarded so that
    a new conforming version will be written to disk.

    Parameters
    ----------
    manifest_path : str
        Path to the manifest JSON file

    """
    global MANIFEST

    logger = get_logger("read_manifest_path")

    with open(manifest_path, "r") as infile:
        MANIFEST = json.load(infile)

    # Verify the contents of the read manifest conform to what we expect for this version of DUM
    if not all(key in manifest_entry for manifest_entry in MANIFEST.values() for key in EXPECTED_MANIFEST_KEYS):
        logger.warning("Provided manifest %s does not conform to expected format.", manifest_path)
        logger.warning("A new manifest will be generated for this execution.")
        MANIFEST.clear()


def write_manifest_file(manifest_path):
    """
    Commits the contents of the Ingress Manifest to the provided path on disk
    in JSON format.

    This function performs some manual whitespace formatting to promote
    readability of the output JSON file.

    Parameters
    ----------
    manifest_path : str
        Path on disk to commit the Ingress Manifest file to.

    """
    with open(manifest_path, "w") as outfile:
        outfile.write("{\n")

        for index, (k, v) in enumerate(sorted(MANIFEST.items())):
            outfile.write(f'"{k}": {json.dumps(v)}')

            # Can't have a trailing comma on last dictionary entry in JSON
            if index < len(MANIFEST) - 1:
                outfile.write(",")

            outfile.write("\n")
        outfile.write("}")


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
    logger = get_logger("create_report_file")

    uploaded = list(sorted(chain(*SUMMARY_TABLE["uploaded"].values())))
    skipped = list(sorted(chain(*SUMMARY_TABLE["skipped"].values())))
    failed = list(sorted(chain(*SUMMARY_TABLE["failed"].values())))

    report = {
        "Arguments": str(args),
        "Batch Size": SUMMARY_TABLE["batch_size"],
        "Total Batches": SUMMARY_TABLE["num_batches"],
        "Start Time": str(datetime.fromtimestamp(SUMMARY_TABLE["start_time"], tz=timezone.utc)),
        "Finish Time": str(datetime.fromtimestamp(SUMMARY_TABLE["end_time"], tz=timezone.utc)),
        "Uploaded": uploaded,
        "Total Uploaded": len(uploaded),
        "Skipped": skipped,
        "Total Skipped": len(skipped),
        "Failed": failed,
        "Total Failed": len(failed),
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
        "--log-path",
        type=str,
        default=None,
        help="Specify a file path to write logging statements to. These will include "
        "some of the messages logged to the console, as well as additional "
        "messages about the status of each file/batch transfer. By default, "
        "the log file is created in a temporary location if this parameter "
        "is not provided. If provided, this argument takes precedence over "
        "what is provided for OTHER.log_file_path in the INI config.",
    )
    parser.add_argument(
        "--manifest-path",
        type=str,
        default=None,
        help="Specify a file path to a JSON manifiest of all files indexed "
        "for inclusion in the current ingress request. If the provided path is "
        "not an existing file, then the manifest will be written to that "
        "location. If the path already exists, this script will read the manifiest, "
        "and skip checksum generation for any paths that are already specified. "
        "If not provided, no manifiest is written or read.",
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


def main(args):
    """
    Main entry point for the pds-ingress-client script.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command-line arguments.

    Raises
    ------
    ValueError
        If a username and password are not defined within the parsed config,
        and dry-run is not enabled.

    """
    global BEARER_TOKEN

    # Note: this should always get called first to ensure the Config singleton is
    #       fully initialized before used in any calls to get_logger
    config = ConfigUtil.get_config(args.config_path)

    if args.log_path:
        config["OTHER"]["log_file_path"] = os.path.abspath(args.log_path)

    logger = get_logger("main", log_level=get_log_level(args.log_level))

    logger.info("Starting PDS Data Upload Manager Client v%s", __version__)
    logger.info("Loaded config file %s", args.config_path)
    logger.info("Logging to file %s", log_util.FILE_HANDLER.baseFilename)

    # Derive the full list of ingress paths based on the set of paths requested
    # by the user
    logger.info("Determining paths for ingress...")
    with get_path_progress_bar(args.ingress_paths) as pbar:
        resolved_ingress_paths = PathUtil.resolve_ingress_paths(args.ingress_paths, pbar)

    node_id = args.node

    # Set the joblib pool size based on the number of "threads" requested
    PARALLEL.n_jobs = args.num_threads

    # Break the set of ingress paths into batches based on configured size
    batch_size = int(config["OTHER"].get("batch_size", fallback=1))

    batched_ingress_paths = list(batched(resolved_ingress_paths, batch_size))
    logger.info("Using batch size of %d", batch_size)
    logger.info("Request (%d files) split into %d batches", len(resolved_ingress_paths), len(batched_ingress_paths))

    if args.manifest_path and os.path.exists(args.manifest_path):
        logger.info("Reading existing manifest file %s", args.manifest_path)
        read_manifest_file(args.manifest_path)

    logger.info("Preparing batches for ingress...")
    request_batchs = prepare_batches(batched_ingress_paths, args.prefix)

    if args.manifest_path:
        logger.info("Writing manifest file to %s", os.path.abspath(args.manifest_path))
        write_manifest_file(os.path.abspath(args.manifest_path))

    if not args.dry_run:
        initialize_summary_table()

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

        try:
            init_batch_progress_bars(args.num_threads)
            perform_ingress(request_batchs, node_id, args.force_overwrite, config["API_GATEWAY"])
        finally:
            close_batch_progress_bars()

            # Capture completion time of transfer and batch configuration
            SUMMARY_TABLE["end_time"] = time.time()
            SUMMARY_TABLE["batch_size"] = batch_size
            SUMMARY_TABLE["num_batches"] = len(batched_ingress_paths)

            # Create the JSON report file, if requested
            if args.report_path:
                create_report_file(args)

            # Print the summary table
            print_ingress_summary()

            # Flush all logged statements to CloudWatch Logs
            log_util.CLOUDWATCH_HANDLER.flush()
    else:
        logger.info("Dry run requested, skipping ingress request submission.")


if __name__ == "__main__":
    parser = setup_argparser()
    args = parser.parse_args()
    main(args)

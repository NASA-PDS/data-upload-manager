#!/usr/bin/env python3
"""
==================
pds_ingress_client
==================

Client side script used to perform ingress request to the DUM service in AWS.
"""
import argparse
import calendar
import json
import os
import sched
import sys
import time
from datetime import datetime
from datetime import timezone
from http import HTTPStatus
from threading import Thread

import backoff
import pds.ingress.util.log_util as log_util
import requests
from joblib import delayed
from joblib import Parallel
from more_itertools import chunked as batched
from pds.ingress import __version__
from pds.ingress.util.auth_util import AuthUtil
from pds.ingress.util.backoff_util import backoff_handler
from pds.ingress.util.backoff_util import simulate_batch_request_failure
from pds.ingress.util.backoff_util import simulate_ingress_failure
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.hash_util import md5_for_path
from pds.ingress.util.log_util import Color
from pds.ingress.util.log_util import get_log_level
from pds.ingress.util.log_util import get_logger
from pds.ingress.util.node_util import NodeUtil
from pds.ingress.util.path_util import PathUtil
from pds.ingress.util.progress_util import close_batch_progress_bars
from pds.ingress.util.progress_util import close_ingress_total_progress_bar
from pds.ingress.util.progress_util import get_available_batch_progress_bar
from pds.ingress.util.progress_util import get_ingress_total_progress_bar
from pds.ingress.util.progress_util import get_manifest_progress_bar
from pds.ingress.util.progress_util import get_path_progress_bar
from pds.ingress.util.progress_util import get_upload_progress_bar_for_batch
from pds.ingress.util.progress_util import init_batch_progress_bars
from pds.ingress.util.progress_util import release_batch_progress_bar
from pds.ingress.util.progress_util import update_upload_pbar_filename
from pds.ingress.util.report_util import create_report_file
from pds.ingress.util.report_util import initialize_summary_table
from pds.ingress.util.report_util import parts_to_xml
from pds.ingress.util.report_util import print_ingress_summary
from pds.ingress.util.report_util import read_manifest_file
from pds.ingress.util.report_util import update_summary_table
from pds.ingress.util.report_util import write_manifest_file
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


def prepare_batches(batched_ingress_paths, prefix):
    """
    Prepares each batch of files for ingress in parallel via the joblib library.

    Parameters
    ----------
    batched_ingress_paths : list of lists
        List containing all ingress file requests separated into equal batches.
    prefix : dict
        Path prefix value to trim from each ingress path to derive the path
        structure to be used in S3. May be optionally mapped to a replacement value
        for the old prefix.

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
    global SUMMARY_TABLE  # noqa: F824

    logger = get_logger("_process_batch", console=False)

    # Get an avaialble Batch progress bar to update while iterating through this
    # current batch
    batch_pbar = get_available_batch_progress_bar(total=len(request_batch), desc=f"Requesting Batch {batch_index + 1}")

    try:
        response_batch = request_batch_for_ingress(
            request_batch, batch_index, node_id, force_overwrite, api_gateway_config
        )

        batch_pbar.desc = f"Uploading Batch {batch_index + 1}"
        batch_pbar.refresh()

        for ingress_response in response_batch:
            try:
                # If a single response contains multiple s3 URLs, then this is a multipart upload request
                if "s3_urls" in ingress_response:
                    ingress_multipart_file_to_s3(ingress_response, batch_index, batch_pbar)
                else:
                    ingress_file_to_s3(ingress_response, batch_index, batch_pbar)

                batch_pbar.update()
            except Exception as err:
                # If here, the HTTP request error was unrecoverable by a backoff/retry
                trimmed_path = ingress_response.get("trimmed_path")
                ingress_path = ingress_response.get("ingress_path")
                update_summary_table(SUMMARY_TABLE, "failed", ingress_path)

                logger.error("Batch %d : Ingress failed for %s, Reason: %s", batch_index, trimmed_path, str(err))

                continue  # Move to next file in the batch
    except Exception as err:
        # Hit an unrecoverable error while processing the batch
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
    prefix : dict
        Path prefix value to trim from each ingress path to derive the path
        structure to be used in S3. May be optionally mapped to a replacement value
        for the old prefix.
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
    global MANIFEST  # noqa: F824

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
            last_modified_time = calendar.timegm(datetime.fromisoformat(manifest_entry["last_modified"]).timetuple())
        else:
            # Calculate the MD5 checksum of the file payload
            md5_digest = md5_for_path(ingress_path).hexdigest()

            # Get the size and last modified time of the file
            file_size = os.stat(ingress_path).st_size
            last_modified_time = int(os.path.getmtime(ingress_path))

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


@backoff.on_exception(backoff.expo, Exception, max_time=120, on_backoff=backoff_handler, logger=None)
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
    global BEARER_TOKEN  # noqa: F824

    logger = get_logger("request_batch_for_ingress", console=False)

    logger.info("Batch %d : Requesting ingress", batch_index)
    start_time = time.time()

    # Extract the API Gateway configuration params
    api_gateway_template = api_gateway_config["url_template"]
    api_gateway_id = api_gateway_config["id"]
    api_gateway_region = api_gateway_config["region"]
    api_gateway_stage = api_gateway_config["stage"]
    api_gateway_resource = "request"

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

    # Simulate a random failure for the batch request if configured to do so
    with simulate_batch_request_failure(api_gateway_url.split("?")[0]):
        response = requests.post(
            api_gateway_url, params=params, data=json.dumps(request_batch), headers=headers, timeout=600
        )

    elapsed_time = time.time() - start_time

    #
    # SUCCESS PATH — 200 OK
    # The ingress request completed successfully and the Lambda returned
    # a valid response batch. Parse and return it to the caller.
    #
    if response.status_code == HTTPStatus.OK:
        response_batch = response.json()

        logger.info("Batch %d : Ingress request completed in %.2f seconds", batch_index, elapsed_time)

        return response_batch

    #
    # FAILURE PATH — ANY NON-200 RESPONSE
    # At this point the request did not succeed. This indicates either:
    #   • The user does not have permission (403), OR
    #   • The ingestion service experienced an internal failure (500), OR
    #   • Any other client/server error that prevents progress.
    #
    # All of these conditions require the client to stop immediately.
    #

    # Ensure progress bars are closed before printing the error message
    close_ingress_total_progress_bar()
    close_batch_progress_bars()

    # Use console-only logger so the user clearly sees the error message
    logger = get_logger(
        "request_batch_for_ingress",
        cloudwatch=False,
        console=True,
        file=True,
    )

    logger.error(Color.red("----------------------------------------------"))
    logger.error(Color.red_bold(
        f"Ingress request failed with HTTP status {response.status_code} ({response.reason})"
    ))

    #
    # Special handling for 403 (user is authenticated but not allowed)
    # This typically indicates an external access restriction, such as
    # the client’s IP address not being permitted to access the DUM
    # service through API Gateway/WAF.
    #
    if response.status_code == HTTPStatus.FORBIDDEN:
        logger.error(Color.red(
            "Access to the ingestion service was denied (403 Forbidden).\n"
            "This usually indicates that the current network is not "
            "authorized to access the DUM service.\n"
            "Please contact PDS Engineering with your network’s IP range."
        ))

    #
    # All other non-200 errors are treated as internal service failures.
    # These require assistance from PDS Engineering and should not be retried.
    #
    else:
        logger.error(Color.red(
            "The ingestion service encountered an internal error and could "
            "not process this request.\n"
            "Please contact PDS Engineering for assistance."
        ))

    # Fail fast — do not retry or continue processing further batches
    sys.exit(1)


@backoff.on_exception(backoff.expo, Exception, max_time=120, on_backoff=backoff_handler, logger=None)
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
    global SUMMARY_TABLE  # noqa: F824

    logger = get_logger("ingress_file_to_s3", console=False)

    response_result = int(ingress_response.get("result", -1))
    trimmed_path = ingress_response.get("trimmed_path")
    ingress_path = ingress_response.get("ingress_path")

    if response_result == HTTPStatus.OK:
        s3_ingress_url = ingress_response.get("s3_url")

        logger.info("Batch %d : Ingesting %s to %s", batch_index, trimmed_path, s3_ingress_url.split("?")[0])

        if not ingress_path:
            raise ValueError("No ingress path provided with response for %s", trimmed_path)

        file_length = os.stat(ingress_path).st_size

        headers = {
            "Content-Length": str(file_length),
        }

        # If the file is non-empty, include the base64-encoded MD5 hash so AWS
        # can perform its own integrity check on the uploaded file (AWS does
        # not support hash checks for empty files)
        if file_length > 0:
            headers["Content-MD5"] = ingress_response.get("base64_md5")

        # Initialize the file upload progress subbar attached to the batch progress bar
        upload_pbar = get_upload_progress_bar_for_batch(
            batch_pbar, total=os.stat(ingress_path).st_size, filename=os.path.basename(ingress_path)
        )

        # Simulate a random failure for the S3 ingress request if configured to do so
        with simulate_ingress_failure(s3_ingress_url.split("?")[0]):
            with open(ingress_path, "rb") as infile:
                # Wrap file I/O with our upload bar to automatically track file upload progress
                wrapped_file = CallbackIOWrapper(upload_pbar.update, infile, "read")

                # Only send the file data if the file is non-empty
                response = requests.put(s3_ingress_url, data=wrapped_file if file_length > 0 else b"", headers=headers)
                response.raise_for_status()

        logger.info("Batch %d : %s Ingest complete", batch_index, trimmed_path)
        update_summary_table(SUMMARY_TABLE, "uploaded", ingress_path)
        upload_pbar.reset()
    elif response_result == HTTPStatus.NO_CONTENT:
        Color.blue(
            f"Batch {batch_index} : Skipping ingress for {trimmed_path}, "
            f"reason {ingress_response.get('message')}"
        )
        update_summary_table(SUMMARY_TABLE, "skipped", ingress_path)

    elif response_result == HTTPStatus.NOT_FOUND:
        logger.warning(
            Color.yellow(
                f"Batch {batch_index} : Ingress failed for {trimmed_path}, "
                f"reason: {ingress_response.get('message')}"
            )
        )
        update_summary_table(SUMMARY_TABLE, "failed", ingress_path)

    else:
        logger.error(Color.red(
            f"Batch {batch_index} : Unexpected response code ({response_result}) "
            f"from Ingress service"
        ))
        raise RuntimeError


# noinspection PyUnreachableCode
@backoff.on_exception(backoff.expo, Exception, max_time=120, on_backoff=backoff_handler, logger=None)
def ingress_multipart_file_to_s3(ingress_response, batch_index, batch_pbar):
    """
    Performs an ingress request for a file that is too large to be uploaded
    in a single request. The file is instead uploaded in multiple parts using
    the list of pre-signed S3 URLs returned from the Ingress Service Lambda.

    Parameters
    ----------
    ingress_response : dict
        Dictionary containing the information returned from the Ingress Lambda
        App required to perform the multipart upload to S3.
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
    global SUMMARY_TABLE  # noqa: F824

    logger = get_logger("ingress_multipart_file_to_s3", console=False)

    response_result = int(ingress_response.get("result", -1))
    trimmed_path = ingress_response.get("trimmed_path")
    ingress_path = ingress_response.get("ingress_path")

    if response_result == HTTPStatus.OK:
        logger.info("Batch %d : Performing Multipart Upload for %s", batch_index, trimmed_path)

        s3_ingress_urls = ingress_response.get("s3_urls", [])
        upload_complete_url = ingress_response.get("upload_complete_url")
        upload_abort_url = ingress_response.get("upload_abort_url")
        chunk_size = ingress_response.get("chunk_size")

        upload_pbar = get_upload_progress_bar_for_batch(
            batch_pbar, total=os.stat(ingress_path).st_size, filename=os.path.basename(ingress_path)
        )

        # Open a handle to file to upload, wrap it so it updates the progress bar,
        # then create an iterator that reads the file in chunks of the size
        # specified by the ingress lambda
        file_handle = open(ingress_path, "rb")
        wrapped_file = CallbackIOWrapper(upload_pbar.update, file_handle, "read")
        chunk_iterator = iter(lambda: wrapped_file.read(chunk_size), b"")

        completed_parts = []

        try:
            for part_number, s3_ingress_url in enumerate(s3_ingress_urls, start=1):
                logger.info("Uploading part %d of %d for %s", part_number, len(s3_ingress_urls), trimmed_path)

                # Update the upload progress bar with the current part number
                update_upload_pbar_filename(
                    upload_pbar, f"{os.path.basename(ingress_path)} (Part {part_number}/{len(s3_ingress_urls)})"
                )

                # Simulate a random failure for the S3 ingress request if configured to do so
                with simulate_ingress_failure(s3_ingress_url.split("?")[0]):
                    # Submit a single chunk to AWS
                    response = requests.put(s3_ingress_url, data=next(chunk_iterator))
                    response.raise_for_status()

                completed_parts.append({"ETag": response.headers["ETag"], "PartNumber": part_number})
        except Exception as err:
            logger.error(Color.red(f"Failure occurred during Multipart upload, reason: {err}"))
            logger.error(Color.red(f"Aborting Multipart Upload for {trimmed_path}"))
            response = requests.post(upload_abort_url)
            response.raise_for_status()
            raise
        finally:
            file_handle.close()

        # Complete the multipart upload
        logger.info(Color.green_bold("Completing Multipart Upload for %s", trimmed_path))
        response = requests.post(upload_complete_url, data=parts_to_xml(completed_parts))
        response.raise_for_status()

        logger.info(Color.green_bold("Batch %d : %s Multipart Upload complete", batch_index, trimmed_path))
        update_summary_table(SUMMARY_TABLE, "uploaded", ingress_path)
    elif response_result == HTTPStatus.NO_CONTENT:
        logger.info(
            Color.blue_bold("Batch %d : Skipping ingress for %s, reason %s", batch_index, trimmed_path, ingress_response.get("message"))
        )
        update_summary_table(SUMMARY_TABLE, "skipped", ingress_path)
    elif response_result == HTTPStatus.NOT_FOUND:
        logger.warning(
            Color.red_bold("Batch %d : Ingress failed for %s, reason: %s", batch_index, trimmed_path, ingress_response.get("message"))
        )
        update_summary_table(SUMMARY_TABLE, "failed", ingress_path)
    else:
        logger.error(Color.red_bold("Batch %d : Unexepected response code (%d) from Ingress service", batch_index, response_result))
        raise RuntimeError


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
        "--weblogs",
        "-w",
        type=str,
        default=None,
        metavar="LOG_TYPE",
        help="Denotes the upload request as being for LOG_TYPE web logs. "
        "All uploaded files will be routed to a special S3 location reserved "
        "for web log files. LOG_TYPE denotes the type of web logs being "
        "uploaded, and becomes part of the destination upload path. "
        "If provided, --prefix must be provided as well.",
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
        "--include",
        "-i",
        type=str,
        action="append",
        default=list(),
        dest="includes",
        metavar="PATTERN",
        help="Specify a file path pattern to match against when determining "
        "which files should be included with an Ingress request. "
        "Unix-style wildcard patterns are supported. "
        "Include patterns are always applied prior to any Exclude patterns. "
        "This argument can be specified multiple times to configure multiple "
        "include patterns. Include patterns are evaluated in the order they provided.",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        type=str,
        action="append",
        default=list(),
        dest="excludes",
        metavar="PATTERN",
        help="Specify a file path pattern to match against when determining "
        "which files should be excluded from an Ingress request. "
        "Unix-style wildcard patterns are supported. "
        "Exclude patterns are always applied after any Include patterns. "
        "This argument can be specified multiple times to configure multiple "
        "exclude patterns. Exclude patterns are evaluated in the order they provided.",
    )
    parser.add_argument(
        "--num-threads",
        "-t",
        type=int,
        default=os.cpu_count(),
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
    global BEARER_TOKEN, MANIFEST, SUMMARY_TABLE

    # Note: this should always get called first to ensure the Config singleton is
    #       fully initialized before used in any calls to get_logger
    config = ConfigUtil.get_config(args.config_path)

    if args.log_path:
        config["OTHER"]["log_file_path"] = os.path.abspath(args.log_path)

    logger = get_logger("main", log_level=get_log_level(args.log_level))

    logger.info("Starting PDS Data Upload Manager Client v%s", __version__)
    logger.info("Loaded config file %s", args.config_path)
    logger.info("Logging to file %s", log_util.FILE_HANDLER.baseFilename)
    if args.force_overwrite:
        logger.info(Color.red_bold("Force-overwrite enabled: existing files will be overwritten."))

    # Derive the full list of ingress paths based on the set of paths requested
    # by the user
    logger.info("Determining paths for ingress...")
    with get_path_progress_bar(args.ingress_paths) as pbar:
        resolved_ingress_paths = PathUtil.resolve_ingress_paths(args.ingress_paths, args.includes, args.excludes, pbar)

    # Initialize the summary table, and populate the "unprocessed" table the set
    # of resolved ingress paths
    SUMMARY_TABLE = initialize_summary_table()
    update_summary_table(SUMMARY_TABLE, "unprocessed", resolved_ingress_paths)

    node_id = args.node

    # Set the joblib pool size based on the number of "threads" requested
    PARALLEL.n_jobs = args.num_threads

    # Break the set of ingress paths into batches based on configured size
    batch_size = int(config["OTHER"].get("batch_size", fallback=1))
    SUMMARY_TABLE["batch_size"] = batch_size

    batched_ingress_paths = list(batched(resolved_ingress_paths, batch_size))
    logger.info("Using batch size of %d", batch_size)
    logger.info("Request (%d files) split into %d batches", len(resolved_ingress_paths), len(batched_ingress_paths))
    SUMMARY_TABLE["num_batches"] = len(batched_ingress_paths)

    if args.manifest_path and os.path.exists(args.manifest_path):
        logger.info("Reading existing manifest file %s", args.manifest_path)
        MANIFEST = read_manifest_file(args.manifest_path)

    logger.info("Preparing batches for ingress...")

    # Set up the prefix mapping
    if args.weblogs:
        if not args.prefix:
            raise ValueError("When --weblogs is specified, --prefix must also be provided.")

        replacement_value = f"weblogs/{args.node}-{args.weblogs.lower()}"

        # Preserve trailing slash if one was provided in the original prefix
        if args.prefix.endswith("/"):
            replacement_value += "/"

        prefix = {"old": args.prefix, "new": replacement_value}
    else:
        # Replace prefix with empty string to remove it from the S3 path
        prefix = {"old": args.prefix, "new": ""}

    request_batchs = prepare_batches(batched_ingress_paths, prefix)

    if args.manifest_path:
        logger.info("Writing manifest file to %s", os.path.abspath(args.manifest_path))
        write_manifest_file(MANIFEST, os.path.abspath(args.manifest_path))

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

        try:
            init_batch_progress_bars(min(args.num_threads, len(request_batchs)))
            perform_ingress(request_batchs, node_id, args.force_overwrite, config["API_GATEWAY"])
        finally:
            close_batch_progress_bars()

        logger.info(Color.green_bold("All batches processed"))

        try:
            if len(SUMMARY_TABLE["failed"]) > 0:
                logger.info("----------------------------------------")
                logger.info("Reattempting ingress for failed files...")

                failed_ingresses = SUMMARY_TABLE["failed"]
                batched_failed_ingresses = list(batched(failed_ingresses, batch_size))
                failed_request_batchs = prepare_batches(batched_failed_ingresses, prefix)

                init_batch_progress_bars(min(args.num_threads, len(failed_request_batchs)))
                perform_ingress(failed_request_batchs, node_id, args.force_overwrite, config["API_GATEWAY"])
        finally:
            close_batch_progress_bars()

            # Flush all logged statements to CloudWatch Logs
            log_util.CLOUDWATCH_HANDLER.flush()
    else:
        logger.info(Color.blue("Dry run requested, skipping ingress request submission."))

    # Capture completion time
    SUMMARY_TABLE["end_time"] = time.time()

    # Create the JSON report file, if requested
    if args.report_path:
        create_report_file(args, SUMMARY_TABLE)

    # Print the summary table
    print_ingress_summary(SUMMARY_TABLE)


def console_main():
    """No argument entrypoint for use with setuptools"""
    parser = setup_argparser()
    args = parser.parse_args()
    main(args)


if __name__ == "__main__":
    console_main()

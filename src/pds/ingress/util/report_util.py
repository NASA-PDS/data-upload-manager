"""
==============
report_util.py
==============

Module containing functions related to output of various report files used
to track status of a DUM upload request.

"""
import json
import multiprocessing
import os
import time
from datetime import datetime
from datetime import timezone

from pds.ingress.util.log_util import Color
from pds.ingress.util.log_util import get_logger

REPORT_LOCK = multiprocessing.Lock()
"""Lock used to control write access to the summary table"""

EXPECTED_MANIFEST_KEYS = ("ingress_path", "md5", "size", "last_modified")
"""The keys we expect to find assigned to each mapping within a read manifest"""


def initialize_summary_table():
    """Returns a summary table initialized to its default state."""
    return {
        "uploaded": set(),
        "skipped": set(),
        "failed": set(),
        "unprocessed": set(),
        "transferred": 0,
        "start_time": time.time(),
        "end_time": None,
        "batch_size": 0,
        "num_batches": 0,
    }


def update_summary_table(summary_table, key, paths):
    """
    Updates the summary table with the provided key, index, and value.

    Parameters
    ----------
    summary_table : dict
        The summary table to update.
    key : str
        The key in the summary table to update (e.g., "uploaded", "skipped", "failed").
    paths : str or list of str
        The path value (or values) to add to the summary table for the specified key.
        Note, these paths should be the absolute paths to files that were processed,
        not the "trimmed" relative paths.

    """
    if key not in ("uploaded", "skipped", "failed", "unprocessed"):
        raise KeyError(f"Invalid key '{key}' provided for summary table update.")

    if key not in summary_table:
        raise KeyError(f"Key '{key}' not found in summary table.")

    if not isinstance(paths, list):
        paths = [paths]

    with REPORT_LOCK:
        summary_table[key].update(paths)

        if key == "uploaded":
            # Update total number of bytes transferrred for successful uploads
            summary_table["transferred"] += sum(os.stat(path).st_size for path in paths)

            # If this file or files previous failed, remove from the failed set
            summary_table["failed"] -= set(paths)

        # Prune any now-visted paths from the unprocessed set
        if key != "unprocessed":
            summary_table["unprocessed"] -= set(paths)


def color_count(label, count, color_func):
    """Returns a colorized text only when count > 0. Otherwise, returns plain text."""
    text = f"{label}: {count} file(s)"
    return color_func(text) if count > 0 else text


def print_ingress_summary(summary_table):
    """
    Prints the summary report for last execution of the client script.

    Parameters
    ----------
    summary_table : dict
        Dictionary containg the summarized results of DUM ingress reqeust.

    """
    logger = get_logger("print_ingress_summary")

    num_uploaded = len(summary_table["uploaded"])
    num_skipped = len(summary_table["skipped"])
    num_failed = len(summary_table["failed"])
    num_unprocessed = len(summary_table["unprocessed"])
    start_time = summary_table["start_time"]
    end_time = summary_table["end_time"]
    transferred = summary_table["transferred"]

    title = f"Ingress Summary Report for {str(datetime.now())}"

    logger.info("")  # Blank line to distance report from progress bar cleanup
    logger.info(Color.bold(title))
    logger.info(Color.bold("-" * len(title)))

    logger.info(color_count("Uploaded", num_uploaded, Color.green_bold))
    logger.info(color_count("Skipped", num_skipped, Color.blue))
    logger.info(color_count("Failed", num_failed, Color.red))
    logger.info(color_count("Unprocessed", num_unprocessed, Color.yellow))

    total = num_uploaded + num_skipped + num_failed + num_unprocessed
    logger.info(Color.bold(f"Total: {total} file(s)"))
    logger.info(Color.bold(f"Time elapsed: {end_time - start_time:.2f} seconds"))
    logger.info(Color.green(f"Bytes transferred: {transferred}"))


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
    logger = get_logger("read_manifest_path")

    with open(manifest_path, "r") as infile:
        manifest = json.load(infile)

    # Verify the contents of the read manifest conform to what we expect for this version of DUM
    if not all(key in manifest_entry for manifest_entry in manifest.values() for key in EXPECTED_MANIFEST_KEYS):
        logger.warning("Provided manifest %s does not conform to expected format.", manifest_path)
        logger.warning("A new manifest will be generated for this execution.")
        manifest.clear()

    return manifest


def write_manifest_file(manifest, manifest_path):
    """
    Commits the contents of the Ingress Manifest to the provided path on disk
    in JSON format.

    This function performs some manual whitespace formatting to promote
    readability of the output JSON file.

    Parameters
    ----------
    manifest : dict
        Dictionary containing the contents of the manifest to commit to disk.
    manifest_path : str
        Path on disk to commit the Ingress Manifest file to.

    """
    with open(manifest_path, "w") as outfile:
        outfile.write("{\n")

        for index, (k, v) in enumerate(sorted(manifest.items())):
            outfile.write(f'"{k}": {json.dumps(v)}')

            # Can't have a trailing comma on last dictionary entry in JSON
            if index < len(manifest) - 1:
                outfile.write(",")

            outfile.write("\n")
        outfile.write("}")


def create_report_file(args, summary_table):
    """
    Writes a detailed report for the last transfer in JSON format to disk.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command-line arguments, including the path to write the
        summary report to. A listing of all provided arguments is included in
        the report file.
    summary_table : dict
        Dictionary containg the summarized results of DUM ingress reqeust to
        write to disk.

    """
    logger = get_logger("create_report_file")

    uploaded = list(sorted(summary_table["uploaded"]))
    skipped = list(sorted(summary_table["skipped"]))
    failed = list(sorted(summary_table["failed"]))
    unprocessed = list(sorted(summary_table["unprocessed"]))

    report = {
        "Arguments": str(args),
        "Batch Size": summary_table["batch_size"],
        "Total Batches": summary_table["num_batches"],
        "Start Time": str(datetime.fromtimestamp(summary_table["start_time"], tz=timezone.utc)),
        "Finish Time": str(datetime.fromtimestamp(summary_table["end_time"], tz=timezone.utc)),
        "Uploaded": uploaded,
        "Total Uploaded": len(uploaded),
        "Skipped": skipped,
        "Total Skipped": len(skipped),
        "Failed": failed,
        "Total Failed": len(failed),
        "Unprocessed": unprocessed,
        "Total Unprocessed": len(unprocessed),
        "Bytes Transferred": summary_table["transferred"],
    }

    report["Total Files"] = (
        report["Total Uploaded"] + report["Total Skipped"] + report["Total Failed"] + report["Total Unprocessed"]
    )

    try:
        logger.info("Writing JSON summary report to %s", args.report_path)

        with open(args.report_path, "w") as outfile:
            json.dump(report, outfile, indent=4)
    except OSError as err:
        logger.warning("Failed to write summary report to %s, reason: %s", args.report_path, str(err))


def parts_to_xml(multi_parts):
    """
    Converts a list of multipart upload parts to an XML string for use
    as the body in a CompleteMultipartUpload request.

    Parameters
    ----------
    multi_parts : list
        List of dictionaries representing the parts of a multipart upload.
        Each dictionary should contain "PartNumber" and "ETag" keys.

    Returns
    -------
    parts_xml: str
        The XML string representing the multipart upload parts.

    """
    parts_xml = "<CompleteMultipartUpload>\n"

    for part in multi_parts:
        parts_xml += "  <Part>\n"
        parts_xml += "    <PartNumber>%d</PartNumber>\n" % part["PartNumber"]
        parts_xml += "    <ETag>%s</ETag>\n" % part["ETag"]
        parts_xml += "  </Part>\n"

    parts_xml += "</CompleteMultipartUpload>"

    return parts_xml

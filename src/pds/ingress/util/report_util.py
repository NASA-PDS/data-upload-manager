"""
==============
report_util.py
==============

Module containing functions related to output of various report files used
to track status of a DUM upload request.

"""
import json
import time
from collections import defaultdict
from datetime import datetime
from datetime import timezone
from itertools import chain

from pds.ingress.util.log_util import get_logger

EXPECTED_MANIFEST_KEYS = ("ingress_path", "md5", "size", "last_modified")
"""The keys we expect to find assigned to each mapping within a read manifest"""


def initialize_summary_table():
    """Returns a summary table initialized to its default state."""
    return {
        "uploaded": defaultdict(set),
        "skipped": defaultdict(set),
        "failed": defaultdict(set),
        "transferred": 0,
        "start_time": time.time(),
        "end_time": None,
        "batch_size": 0,
        "num_batches": 0,
    }


def print_ingress_summary(summary_table):
    """
    Prints the summary report for last execution of the client script.

    Parameters
    ----------
    summary_table : dict
        Dictionary containg the summarized results of DUM ingress reqeust.

    """
    logger = get_logger("print_ingress_summary")

    num_uploaded = sum(len(batch) for batch in summary_table["uploaded"].values())
    num_skipped = sum(len(batch) for batch in summary_table["skipped"].values())
    num_failed = sum(len(batch) for batch in summary_table["failed"].values())
    start_time = summary_table["start_time"]
    end_time = summary_table["end_time"]
    transferred = summary_table["transferred"]

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

    uploaded = list(sorted(chain(*summary_table["uploaded"].values())))
    skipped = list(sorted(chain(*summary_table["skipped"].values())))
    failed = list(sorted(chain(*summary_table["failed"].values())))

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
        "Bytes Transferred": summary_table["transferred"],
    }

    report["Total Files"] = report["Total Uploaded"] + report["Total Skipped"] + report["Total Failed"]

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

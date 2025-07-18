#!/usr/bin/env python3
import json
import os
import tempfile
import unittest
from argparse import Namespace
from collections import namedtuple
from datetime import datetime
from datetime import timezone
from importlib.resources import files
from os.path import abspath
from os.path import exists
from os.path import join
from unittest.mock import MagicMock
from unittest.mock import patch

import pds.ingress.util.report_util
from pds.ingress.util.report_util import create_report_file
from pds.ingress.util.report_util import initialize_summary_table
from pds.ingress.util.report_util import read_manifest_file
from pds.ingress.util.report_util import update_summary_table
from pds.ingress.util.report_util import write_manifest_file


class ReportUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Set up directories and files for testing"""
        cls.starting_dir = abspath(os.curdir)
        cls.test_dir = str(files("tests.pds.ingress").joinpath("util"))

        os.chdir(cls.test_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        """At completion re-establish starting directory"""
        os.chdir(cls.starting_dir)

    def setUp(self) -> None:
        """Create a temporary directory that each test can populate as necessary"""
        self.working_dir = tempfile.TemporaryDirectory(prefix="test_report_util_", suffix="_temp", dir=os.curdir)

    def tearDown(self) -> None:
        """Return to starting directory and delete temp dir"""
        os.chdir(self.test_dir)
        self.working_dir.cleanup()

    def test_manifest_file_read_write(self):
        """Test the read/write functions for manifest file creation"""
        dummy_manifest = {
            "path/to/sample/file.txt": {
                "ingress_path": "/absoulte/path/to/sample/file.txt",
                "md5": "deadbeefdeadbeefdeadbeefdeadbeef",
                "size": 1234,
                "last_modified": "2024-06-09T08:57:23+00:00",
            }
        }

        manifest_path = join(self.working_dir.name, "dummy_manifest.json")

        write_manifest_file(dummy_manifest, manifest_path)

        self.assertTrue(exists(manifest_path))

        read_manifest = read_manifest_file(manifest_path)

        self.assertDictEqual(dummy_manifest, read_manifest)

        # Create a manifest that does not conform to the expected format
        # Upon re-reading, we should detect this and return an empty manifest
        dummy_manifest = {
            "path/to/sample/file.txt": {
                "ingress_path": "/absoulte/path/to/sample/file.txt",
                "md5": "deadbeefdeadbeefdeadbeefdeadbeef",
                "size": 1234,
            }
        }

        write_manifest_file(dummy_manifest, manifest_path)

        self.assertTrue(exists(manifest_path))

        with self.assertLogs(level="WARNING") as cm:
            read_manifest = read_manifest_file(manifest_path)
            self.assertEqual(
                cm.output[-1], "WARNING:read_manifest_path:A new manifest will be generated for this execution."
            )

        self.assertTrue(len(read_manifest) == 0)

    def test_report_file_creation(self):
        """Test creation of the summary report file"""
        summary_table = initialize_summary_table()

        summary_table["uploaded"].add("path/to/uploaded.txt")
        summary_table["skipped"].add("path/to/skipped.txt")
        summary_table["failed"].add("path/to/failed.txt")
        summary_table["unprocessed"].add("path/to/unprocessed.txt")
        summary_table["transferred"] = 100
        summary_table["end_time"] = summary_table["start_time"]
        summary_table["batch_size"] = 10
        summary_table["num_batches"] = 2

        expected_report_path = join(self.working_dir.name, "dum_report.json")

        args = Namespace(
            config_path="config/mcp.test.ingress.config.ini",
            node="sbn",
            prefix="/absolute/",
            force_overwrite=True,
            num_threads=4,
            log_path="dum_log.txt",
            manifest_path="dum_manifest.json",
            report_path=expected_report_path,
            dry_run=False,
            log_level="info",
            ingress_paths=["/absolute/path/to"],
        )

        create_report_file(args, summary_table)

        self.assertTrue(exists(expected_report_path))

        with open(expected_report_path) as infile:
            read_summary = json.load(infile)

        self.assertIn("Arguments", read_summary)
        self.assertEqual(read_summary["Arguments"], str(args))

        self.assertIn("Batch Size", read_summary)
        self.assertEqual(read_summary["Batch Size"], 10)

        self.assertIn("Total Batches", read_summary)
        self.assertEqual(read_summary["Total Batches"], 2)

        self.assertIn("Start Time", read_summary)
        self.assertEqual(
            read_summary["Start Time"], str(datetime.fromtimestamp(summary_table["start_time"], tz=timezone.utc))
        )

        self.assertIn("Finish Time", read_summary)
        self.assertEqual(
            read_summary["Finish Time"], str(datetime.fromtimestamp(summary_table["end_time"], tz=timezone.utc))
        )

        self.assertIn("Uploaded", read_summary)
        self.assertIsInstance(read_summary["Uploaded"], list)
        self.assertEqual(len(read_summary["Uploaded"]), 1)
        self.assertListEqual(read_summary["Uploaded"], ["path/to/uploaded.txt"])

        self.assertIn("Total Uploaded", read_summary)
        self.assertEqual(read_summary["Total Uploaded"], 1)

        self.assertIn("Skipped", read_summary)
        self.assertIsInstance(read_summary["Skipped"], list)
        self.assertEqual(len(read_summary["Skipped"]), 1)
        self.assertListEqual(read_summary["Skipped"], ["path/to/skipped.txt"])

        self.assertIn("Total Skipped", read_summary)
        self.assertEqual(read_summary["Total Skipped"], 1)

        self.assertIn("Failed", read_summary)
        self.assertIsInstance(read_summary["Failed"], list)
        self.assertEqual(len(read_summary["Failed"]), 1)
        self.assertListEqual(read_summary["Failed"], ["path/to/failed.txt"])

        self.assertIn("Total Failed", read_summary)
        self.assertEqual(read_summary["Total Failed"], 1)

        self.assertIn("Unprocessed", read_summary)
        self.assertIsInstance(read_summary["Unprocessed"], list)
        self.assertEqual(len(read_summary["Unprocessed"]), 1)
        self.assertListEqual(read_summary["Unprocessed"], ["path/to/unprocessed.txt"])

        self.assertIn("Bytes Transferred", read_summary)
        self.assertEqual(read_summary["Bytes Transferred"], 100)

        self.assertIn("Total Files", read_summary)
        self.assertEqual(read_summary["Total Files"], 4)

    @patch.object(
        pds.ingress.util.report_util.os, "stat", MagicMock(return_value=namedtuple("MockStat", ["st_size"])(100))
    )
    def test_update_summary_table(self):
        """Test updating the summary table with new entries"""
        summary_table = initialize_summary_table()

        update_summary_table(
            summary_table, "unprocessed", ["path/to/file1.txt", "path/to/file2.txt", "path/to/file3.txt"]
        )

        self.assertEqual(len(summary_table["unprocessed"]), 3)
        self.assertIn("path/to/file1.txt", summary_table["unprocessed"])
        self.assertIn("path/to/file2.txt", summary_table["unprocessed"])
        self.assertIn("path/to/file3.txt", summary_table["unprocessed"])

        update_summary_table(summary_table, "uploaded", "path/to/file1.txt")
        update_summary_table(summary_table, "skipped", "path/to/file2.txt")
        update_summary_table(summary_table, "failed", "path/to/file3.txt")

        self.assertIn("path/to/file1.txt", summary_table["uploaded"])
        self.assertNotIn("path/to/file1.txt", summary_table["unprocessed"])
        self.assertEqual(summary_table["transferred"], 100)

        self.assertIn("path/to/file2.txt", summary_table["skipped"])
        self.assertNotIn("path/to/file2.txt", summary_table["unprocessed"])

        self.assertIn("path/to/file3.txt", summary_table["failed"])
        self.assertNotIn("path/to/file3.txt", summary_table["unprocessed"])

        self.assertEqual(len(summary_table["unprocessed"]), 0)

        update_summary_table(summary_table, "uploaded", "path/to/file3.txt")

        self.assertIn("path/to/file3.txt", summary_table["uploaded"])
        self.assertNotIn("path/to/file3.txt", summary_table["failed"])
        self.assertEqual(summary_table["transferred"], 200)

        with self.assertRaises(KeyError):
            update_summary_table(summary_table, "invalid_key", "path/to/file4.txt")

        summary_table.pop("uploaded")
        with self.assertRaises(KeyError):
            update_summary_table(summary_table, "uploaded", "path/to/file5.txt")


if __name__ == "__main__":
    unittest.main()

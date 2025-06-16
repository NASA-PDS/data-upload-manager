import json
import os
import unittest
from datetime import datetime
from datetime import timezone
from importlib.resources import files
from unittest.mock import MagicMock
from unittest.mock import patch

import botocore.client
import botocore.exceptions
import pds.ingress.service.pds_status_app
from pds.ingress.service.pds_status_app import get_ingress_status
from pds.ingress.service.pds_status_app import parse_manifest
from pds.ingress.service.pds_status_app import process_manifest


class PDSStatusAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = str(files("tests.pds.ingress").joinpath("service"))

    def setUp(self) -> None:
        # Set up environment variables to mock a default Lambda setup
        os.environ["LAMBDA_TASK_ROOT"] = self.test_dir

        os.environ["BUCKET_MAP_LOCATION"] = "config"
        os.environ["BUCKET_MAP_SCHEMA_LOCATION"] = "config"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map.yaml"
        os.environ["BUCKET_MAP_SCHEMA_FILE"] = "bucket-map.schema"
        os.environ["VERSION_LOCATION"] = "config"
        os.environ["VERSION_FILE"] = "VERSION.txt"
        os.environ["SMTP_CONFIG_SSM_KEY_PATH"] = "/fake/path/to/ssm"

        # Dummy manifest string for use with tests
        self.test_manifest = '{"gbo.ast.catalina.survey/calibration/703/2022/22Apr01/mflat.703.20210907.fits.fz": {"md5": "186699c0133422ce3eb6129d1fe41e30", "size": 17962560, "last_modified": "2024-08-19T20:36:50+00:00"}}'  # pragma: allowlist secret

    def test_parse_manifest(self):
        """Test parsing of manifest info from an SQS record"""
        test_record = {
            "body": self.test_manifest,
            "messageAttributes": {
                "email": {"stringValue": '"email@email.com"'},  # pragma: allowlist secret
                "node": {"stringValue": '"eng"'},
            },
        }

        request_node, return_email, parsed_manifest = parse_manifest(test_record)

        self.assertEqual(request_node, "eng")
        self.assertEqual(return_email, "email@email.com")  # pragma: allowlist secret
        self.assertDictEqual(json.loads(self.test_manifest), parsed_manifest)

        # Test with missing attributes
        test_record = {"body": self.test_manifest, "messageAttributes": {}}

        with self.assertRaises(RuntimeError):
            parse_manifest(test_record)

    def test_process_manifest(self):
        """Test processing of a parsed manifest"""
        parsed_manifest = json.loads(self.test_manifest)

        test_bucket_map = {"MAP": {"NODES": {"ENG": {"default": {"bucket": {"name": "pds-eng-staging-test"}}}}}}

        mock_get_ingress_status = MagicMock(return_value="Uploaded")
        expected_key = list(parsed_manifest.keys())[0]

        with patch.object(pds.ingress.service.pds_status_app, "get_ingress_status", mock_get_ingress_status):
            results = process_manifest("eng", parsed_manifest, test_bucket_map)

            self.assertIn(expected_key, results)
            self.assertEqual(results[expected_key], "Uploaded")

    def test_get_ingress_status(self):
        """Test statusing of files listed in a provided manifest"""
        parsed_manifest = json.loads(self.test_manifest)

        file_info = list(parsed_manifest.values())[0]

        # Setup mock return values for head_object, one which matches the requested
        # file exactly, one that does not and one indiciating the file is not in S3 at all
        match = {
            "ContentLength": str(file_info["size"]),
            "Metadata": {
                "md5": file_info["md5"],
                "last_modified": file_info["last_modified"],
            },
        }
        mismatch = {
            "ContentLength": "2",
            "Metadata": {
                "md5": "mismatchhash",
                "last_modified": datetime.now(tz=timezone.utc).isoformat(),
            },
        }
        missing = botocore.exceptions.ClientError(
            error_response={"Error": {"Code": "404"}}, operation_name="head_object"
        )

        mock_head_object = MagicMock(side_effect=[match, mismatch, missing])

        # First call should match, meaning file status should be "Uploaded"
        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            ingress_status = get_ingress_status("bucket-name", "key/to/mflat.703.20210907.fits.fz", file_info)
            self.assertEqual(ingress_status, "Uploaded")

        # Second call should not match, meaning file status should be "Modified"
        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            ingress_status = get_ingress_status("bucket-name", "key/to/mflat.703.20210907.fits.fz", file_info)
            self.assertEqual(ingress_status, "Modified")

        # Last call should raise ClientError with 404 status, meaning the file is not found in S3
        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            ingress_status = get_ingress_status("bucket-name", "key/to/mflat.703.20210907.fits.fz", file_info)
            self.assertEqual(ingress_status, "Missing")

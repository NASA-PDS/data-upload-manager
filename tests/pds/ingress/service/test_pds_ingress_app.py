import json
import os
import tempfile
import unittest
from datetime import datetime
from datetime import timezone
from functools import partial
from os.path import abspath
from os.path import join
from unittest.mock import MagicMock
from unittest.mock import patch

import boto3
import botocore.client
import botocore.exceptions
from pds.ingress import __version__
from pds.ingress.service.pds_ingress_app import check_client_version
from pds.ingress.service.pds_ingress_app import get_dum_version
from pds.ingress.service.pds_ingress_app import initialize_bucket_map
from pds.ingress.service.pds_ingress_app import lambda_handler
from pds.ingress.service.pds_ingress_app import logger as service_logger
from pds.ingress.service.pds_ingress_app import should_overwrite_file
from pkg_resources import resource_filename


class PDSIngressAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = resource_filename(__name__, "")

    def setUp(self) -> None:
        # Set up environment variables to mock a default Lambda setup
        os.environ["LAMBDA_TASK_ROOT"] = abspath(
            join(self.test_dir, os.pardir, os.pardir, os.pardir, os.pardir, "src", "pds", "ingress", "service")
        )
        os.environ["BUCKET_MAP_LOCATION"] = "config"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map.yaml"
        os.environ["VERSION_LOCATION"] = "config"
        os.environ["VERSION_FILE"] = "VERSION.txt"

    def test_get_dum_version(self):
        """Test parsing of the version number from the bundled VERSION.txt"""
        version = get_dum_version()

        # Version read from bundled file should always match what was parsed into
        # the __init__.py module for the pds.ingress package
        self.assertEqual(version, __version__)

    def test_default_bucket_map(self):
        """Test parsing of the default bucket map bundled with the Lambda function"""
        bucket_map = initialize_bucket_map()

        self.assertIsNotNone(bucket_map)
        self.assertIsInstance(bucket_map, dict)
        self.assertIn("MAP", bucket_map)
        self.assertIn("NODES", bucket_map["MAP"])
        self.assertIn("SBN", bucket_map["MAP"]["NODES"])
        self.assertIn("default", bucket_map["MAP"]["NODES"]["SBN"])
        self.assertEqual(bucket_map["MAP"]["NODES"]["SBN"]["default"], "nucleus-pds-public")

    def test_custom_bucket_map_from_file(self):
        """Test parsing of a non-default bucket map bundled with the Lambda function"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix="temp-bucket-map-", dir=self.test_dir
        ) as temp_bucket_file:
            temp_bucket_file.write(
                """
                MAP:
                  NODES:
                    ENG:
                      default: test-bucket-name
                """
            )

            temp_bucket_file.flush()

            os.environ["BUCKET_MAP_LOCATION"] = self.test_dir
            os.environ["BUCKET_MAP_FILE"] = os.path.basename(temp_bucket_file.name)
            os.environ["LAMBDA_TASK_ROOT"] = ""

            bucket_map = initialize_bucket_map()

            self.assertIsNotNone(bucket_map)
            self.assertIsInstance(bucket_map, dict)
            self.assertIn("MAP", bucket_map)
            self.assertIn("NODES", bucket_map["MAP"])
            self.assertIn("ENG", bucket_map["MAP"]["NODES"])
            self.assertIn("default", bucket_map["MAP"]["NODES"]["ENG"])
            self.assertEqual(bucket_map["MAP"]["NODES"]["ENG"]["default"], "test-bucket-name")

    def test_check_client_version(self):
        """Test the logging that occurs during the client version check"""
        # Check matching case
        with self.assertLogs(logger=service_logger, level="INFO") as cm:
            check_client_version(client_version=__version__, service_version=__version__)

        # Make sure we get the expected number of log messages
        self.assertEqual(len(cm.output), 1)

        # Logger object used in a deployed Lambda function comes with its own
        # built-in formatter, so we need to do a substring match here rather than
        # a straight comparison
        self.assertIn(f"DUM client version ({__version__}) matches ingress service", cm.output[0])

        # Check missing version from client
        with self.assertLogs(logger=service_logger, level="WARNING") as cm:
            check_client_version(client_version=None, service_version=__version__)

        self.assertEqual(len(cm.output), 1)
        self.assertIn("No DUM version provided by client", cm.output[0])

        # Check client/serivce mismatch
        with self.assertLogs(logger=service_logger, level="WARNING") as cm:
            check_client_version(client_version="0.0.0", service_version=__version__)

        self.assertEqual(len(cm.output), 1)
        self.assertIn(f"Version mismatch between client (0.0.0) and service ({__version__})", cm.output[0])

    # Hard-wire some fake credentials into the S3 client so botocore has something
    # to use in environments that have no credentials otherwise (such as GitHub Actions)
    boto3_client_w_creds = partial(
        boto3.client,
        aws_access_key_id="fake_access_key",
        aws_secret_access_key="fake_secret_key",
        aws_session_token="fake_session_token",
    )

    def mock_make_api_call(self, operation_name, kwarg):
        return {"ContentLength": 2, "LastModified": datetime.now(), "ETag": "0hashfakehashfakehashfake0"}

    @patch.object(boto3, "client", boto3_client_w_creds)
    @patch.object(botocore.client.BaseClient, "_make_api_call", mock_make_api_call)
    def test_lambda_handler(self):
        """Test the lambda_handler function with the default bucket map"""
        test_event = {
            "body": json.dumps({"url": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "sbn"},
            "headers": {
                "ContentLength": 1,
                "LastModified": os.path.getmtime(os.path.abspath(__file__)),
                "ContentMD5": "fakehashfakehashfakehash",
            },
        }

        context = {}  # Unused by lambda_handler

        response = lambda_handler(test_event, context)

        self.assertIsInstance(response, dict)
        self.assertIn("statusCode", response)
        self.assertEqual(response["statusCode"], 200)

        self.assertIn("body", response)

        response_body = json.loads(response["body"])
        response_url, signature_params = response_body.split("?")

        expected_url = "https://nucleus-pds-protected.s3.amazonaws.com/sbn/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"

        self.assertEqual(response_url, expected_url)

        # Ensure we got all the expected tokens in the security parameters (actual values don't matter)
        self.assertIn("AWSAccessKeyId=", signature_params)
        self.assertIn("Signature=", signature_params)
        self.assertIn("x-amz-security-token=", signature_params)
        self.assertIn("Expires=", signature_params)

        test_event = {
            "body": json.dumps({"url": "some.other.survey/bundle.some.other.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "sbn"},
            "headers": {
                "ContentLength": 1,
                "LastModified": os.path.getmtime(os.path.abspath(__file__)),
                "ContentMD5": "fakehashfakehashfakehash",
            },
        }

        response = lambda_handler(test_event, context)

        response_body = json.loads(response["body"])
        response_url, signature_params = response_body.split("?")

        expected_url = (
            "https://nucleus-pds-public.s3.amazonaws.com/sbn/some.other.survey/bundle.some.other.survey_v1.0.xml"
        )

        self.assertEqual(response_url, expected_url)

        self.assertIn("AWSAccessKeyId=", signature_params)
        self.assertIn("Signature=", signature_params)
        self.assertIn("x-amz-security-token=", signature_params)
        self.assertIn("Expires=", signature_params)

        test_event = {
            "body": json.dumps({"url": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "unk"},
            "headers": {
                "ContentLength": 1,
                "LastModified": os.path.getmtime(os.path.abspath(__file__)),
                "ContentMD5": "fakehashfakehashfakehash",
            },
        }

        with self.assertRaises(RuntimeError, msg="No bucket map entries configured for Node ID unk"):
            lambda_handler(test_event, context)

        test_event = {
            "body": json.dumps({}),
            "queryStringParameters": {"node": "eng"},
            "headers": {
                "ContentLength": 1,
                "LastModified": os.path.getmtime(os.path.abspath(__file__)),
                "ContentMD5": "fakehashfakehashfakehash",
            },
        }

        with self.assertRaises(RuntimeError, msg="Both a local URL and request Node ID must be provided"):
            lambda_handler(test_event, context)

    def test_should_overwrite_file(self):
        """Test check for overwrite of prexisting file in S3"""
        # Test inclusion of ForceOverwrite flag
        test_headers = {"ForceOverwrite": True}
        bucket = "sample_bucket"
        key = "path/to/sample_file"

        self.assertTrue(should_overwrite_file(bucket, key, test_headers))

        # Create sample data sent by client script
        test_headers = {
            "ContentLength": os.stat(os.path.abspath(__file__)).st_size,
            "ContentMD5": "validhash",
            "LastModified": os.path.getmtime(os.path.abspath(__file__)),
            "ForceOverwrite": False,
        }

        # Setup mock return values for head_object, one which matches the requested
        # file exactly, and one that does not
        match = {
            "ContentLength": test_headers["ContentLength"],
            "ETag": "0validhash0",
            "LastModified": datetime.fromtimestamp(test_headers["LastModified"], tz=timezone.utc),
        }
        mismatch = {"ContentLength": 2, "LastModified": datetime.now(tz=timezone.utc), "ETag": "0mismatchhash0"}

        mock_head_object = MagicMock(side_effect=[mismatch, match])

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # First call should not match, meaning file should be overwritten
            self.assertTrue(should_overwrite_file(bucket, key, test_headers))

            # Second call should match, meaning file should not be overwritten
            self.assertFalse(should_overwrite_file(bucket, key, test_headers))

        err = {"Error": {"Code": "404"}}
        mock_head_object = MagicMock(side_effect=botocore.exceptions.ClientError(err, "head_object"))

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # File not existing should always result in True
            self.assertTrue(should_overwrite_file(bucket, key, test_headers))

        err = {"Error": {"Code": "403"}}
        mock_head_object = MagicMock(side_effect=botocore.exceptions.ClientError(err, "head_object"))

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # Any type of exception from head_object other than file not found (404) should
            # get reraised
            self.assertRaises(botocore.exceptions.ClientError)


if __name__ == "__main__":
    unittest.main()

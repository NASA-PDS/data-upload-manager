import json
import os
import unittest
from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock
from unittest.mock import patch

# Needed before import of pds_ingress_app
os.environ["AWS_DEFAULT_REGION"] = "us-west-2"

import botocore.auth
import botocore.client
import botocore.exceptions
from pds.ingress import __version__
from pds.ingress.service.pds_ingress_app import check_client_version
from pds.ingress.service.pds_ingress_app import get_dum_version
from pds.ingress.service.pds_ingress_app import lambda_handler
from pds.ingress.service.pds_ingress_app import logger as service_logger
from pds.ingress.service.pds_ingress_app import should_overwrite_file
from importlib.resources import files


class PDSIngressAppTest(unittest.TestCase):
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

    def test_get_dum_version(self):
        """Test parsing of the version number from the bundled VERSION.txt"""
        version = get_dum_version()

        # Version read from bundled file should always match what was parsed into
        # the __init__.py module for the pds.ingress package
        self.assertEqual(version, __version__)

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

    def mock_make_api_call(self, operation_name, kwarg):
        return {"ContentLength": 2, "LastModified": datetime.now(), "ETag": "0hashfakehashfakehashfake0"}

    @patch.object(botocore.client.BaseClient, "_make_api_call", mock_make_api_call)
    def test_lambda_handler(self):
        """Test the lambda_handler function with the default bucket map"""
        test_event = {
            "body": json.dumps(
                [
                    {
                        "ingress_path": "/home/user/data/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "trimmed_path": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "md5": "deadbeefdeadbeefdeadbeef",
                        "size": 1,
                        "last_modified": os.path.getmtime(os.path.abspath(__file__)),
                    }
                ]
            ),
            "queryStringParameters": {"node": "sbn"},
            "headers": {"ClientVersion": __version__, "ForceOverwrite": False},
        }

        context = {}  # Unused by lambda_handler

        with patch.object(botocore.auth.HmacV1QueryAuth, "add_auth", MagicMock):
            response = lambda_handler(test_event, context)

        self.assertIn("statusCode", response)
        self.assertEqual(response["statusCode"], 200)

        self.assertIn("body", response)
        self.assertIsInstance(response["body"], str)

        body = json.loads(response["body"])

        self.assertIsInstance(body, list)
        self.assertEqual(len(body), 1)

        self.assertIsInstance(body[0], dict)
        self.assertIn("result", body[0])
        self.assertEqual(body[0]["result"], 200)

        self.assertIn("trimmed_path", body[0])
        self.assertEqual(body[0]["trimmed_path"], "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml")

        self.assertIn("ingress_path", body[0])
        self.assertEqual(
            body[0]["ingress_path"], "/home/user/data/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"
        )

        self.assertIn("message", body[0])
        self.assertEqual(body[0]["message"], "Request success")

        self.assertIn("s3_url", body[0])
        s3_url = body[0]["s3_url"]

        expected_url = "https://pds-sbn-staging-test.s3.amazonaws.com/sbn/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"
        self.assertTrue(s3_url.startswith(expected_url))

        test_event = {
            "body": json.dumps(
                [
                    {
                        "ingress_path": "/home/user/data/some.other.survey/bundle.some.other.survey_v1.0.xml",
                        "trimmed_path": "some.other.survey/bundle.some.other.survey_v1.0.xml",
                        "md5": "deadbeefdeadbeefdeadbeef",
                        "size": 1,
                        "last_modified": os.path.getmtime(os.path.abspath(__file__)),
                    }
                ]
            ),
            "queryStringParameters": {"node": "sbn"},
            "headers": {"ClientVersion": __version__, "ForceOverwrite": False},
        }

        with patch.object(botocore.auth.HmacV1QueryAuth, "add_auth", MagicMock):
            response = lambda_handler(test_event, context)

        self.assertIn("statusCode", response)
        self.assertEqual(response["statusCode"], 200)

        self.assertIn("body", response)
        self.assertIsInstance(response["body"], str)

        body = json.loads(response["body"])

        self.assertEqual(len(body), 1)

        s3_url = body[0]["s3_url"]

        expected_url = (
            "https://pds-sbn-staging-test.s3.amazonaws.com/sbn/some.other.survey/bundle.some.other.survey_v1.0.xml"
        )

        self.assertTrue(s3_url.startswith(expected_url))

        test_event = {
            "body": json.dumps(
                [
                    {
                        "ingress_path": "/home/user/data/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "trimmed_path": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "md5": "deadbeefdeadbeefdeadbeef",
                        "size": 1,
                        "last_modified": os.path.getmtime(os.path.abspath(__file__)),
                    }
                ]
            ),
            "queryStringParameters": {"node": "unk"},
            "headers": {"ClientVersion": __version__, "ForceOverwrite": False},
        }

        with self.assertRaises(RuntimeError, msg="No bucket map entries configured for Node ID unk"):
            lambda_handler(test_event, context)

        test_event = {
            "body": json.dumps(
                [
                    {
                        "ingress_path": "/home/user/data/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "trimmed_path": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml",
                        "md5": "deadbeefdeadbeefdeadbeef",
                        "size": 1,
                        "last_modified": os.path.getmtime(os.path.abspath(__file__)),
                    }
                ]
            ),
            "queryStringParameters": {},
            "headers": {"ClientVersion": __version__, "ForceOverwrite": False},
        }

        with self.assertRaises(RuntimeError, msg="No request node ID provided in queryStringParameters"):
            lambda_handler(test_event, context)

    def test_should_overwrite_file(self):
        """Test check for overwrite of prexisting file in S3"""
        # Test inclusion of ForceOverwrite flag
        bucket = "sample_bucket"
        key = "path/to/sample_file"
        md5_digest = "validhash"
        file_size = os.stat(os.path.abspath(__file__)).st_size
        last_modified = os.path.getmtime(os.path.abspath(__file__))

        self.assertTrue(should_overwrite_file(bucket, key, md5_digest, file_size, last_modified, force_overwrite=True))

        # Setup mock return values for head_object, one which matches the requested
        # file exactly, and one that does not
        match = {
            "ContentLength": file_size,
            "ETag": "0validhash0",
            "LastModified": datetime.fromtimestamp(last_modified, tz=timezone.utc),
        }
        mismatch = {"ContentLength": 2, "LastModified": datetime.now(tz=timezone.utc), "ETag": "0mismatchhash0"}

        mock_head_object = MagicMock(side_effect=[mismatch, match])

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # First call should not match, meaning file should be overwritten
            self.assertTrue(
                should_overwrite_file(bucket, key, md5_digest, file_size, last_modified, force_overwrite=False)
            )

            # Second call should match, meaning file should not be overwritten
            self.assertFalse(
                should_overwrite_file(bucket, key, md5_digest, file_size, last_modified, force_overwrite=False)
            )

        err = {"Error": {"Code": "404"}}
        mock_head_object = MagicMock(side_effect=botocore.exceptions.ClientError(err, "head_object"))

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # File not existing should always result in True
            self.assertTrue(
                should_overwrite_file(bucket, key, md5_digest, file_size, last_modified, force_overwrite=False)
            )

        err = {"Error": {"Code": "403"}}
        mock_head_object = MagicMock(side_effect=botocore.exceptions.ClientError(err, "head_object"))

        with patch.object(botocore.client.BaseClient, "_make_api_call", mock_head_object):
            # Any type of exception from head_object other than file not found (404) should
            # get reraised
            self.assertRaises(botocore.exceptions.ClientError)


if __name__ == "__main__":
    unittest.main()

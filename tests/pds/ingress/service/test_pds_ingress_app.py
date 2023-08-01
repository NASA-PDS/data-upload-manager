import json
import os
import tempfile
import unittest
from functools import partial
from os.path import abspath
from os.path import join
from unittest.mock import patch

import boto3
from pds.ingress.service.pds_ingress_app import initialize_bucket_map
from pds.ingress.service.pds_ingress_app import lambda_handler
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

    # Hard-wire some fake credentials into the S3 client so botocore has something
    # to use in environments that have no credentials otherwise (such as GitHub Actions)
    boto3_client_w_creds = partial(
        boto3.client,
        aws_access_key_id="fake_access_key",
        aws_secret_access_key="fake_secret_key",
        aws_session_token="fake_session_token",
    )

    @patch.object(boto3, "client", boto3_client_w_creds)
    def test_lambda_handler(self):
        """Test the lambda_handler function with the default bucket map"""
        test_event = {
            "body": json.dumps({"url": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "sbn"},
        }

        context = {}  # Unused by lambda_handler

        response = lambda_handler(test_event, context)

        self.assertIsInstance(response, dict)
        self.assertIn("statusCode", response)
        self.assertEqual(response["statusCode"], 200)

        self.assertIn("body", response)

        response_body = json.loads(response["body"])
        response_url, signature_params = response_body.split("?")

        expected_url = "https://nucleus-pds-protected.s3.amazonaws.com/SBN/gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"

        self.assertEqual(response_url, expected_url)

        # Ensure we got all the expected tokens in the security parameters (actual values don't matter)
        self.assertIn("AWSAccessKeyId=", signature_params)
        self.assertIn("Signature=", signature_params)
        self.assertIn("x-amz-security-token=", signature_params)
        self.assertIn("Expires=", signature_params)

        test_event = {
            "body": json.dumps({"url": "some.other.survey/bundle.some.other.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "sbn"},
        }

        response = lambda_handler(test_event, context)

        response_body = json.loads(response["body"])
        response_url, signature_params = response_body.split("?")

        expected_url = (
            "https://nucleus-pds-public.s3.amazonaws.com/SBN/some.other.survey/bundle.some.other.survey_v1.0.xml"
        )

        self.assertEqual(response_url, expected_url)

        self.assertIn("AWSAccessKeyId=", signature_params)
        self.assertIn("Signature=", signature_params)
        self.assertIn("x-amz-security-token=", signature_params)
        self.assertIn("Expires=", signature_params)

        test_event = {
            "body": json.dumps({"url": "gbo.ast.catalina.survey/bundle_gbo.ast.catalina.survey_v1.0.xml"}),
            "queryStringParameters": {"node": "unk"},
        }

        with self.assertRaises(RuntimeError, msg="No bucket map entries configured for Node ID unk"):
            lambda_handler(test_event, context)

        test_event = {"body": json.dumps({}), "queryStringParameters": {"node": "eng"}}

        with self.assertRaises(RuntimeError, msg="Both a local URL and request Node ID must be provided"):
            lambda_handler(test_event, context)


if __name__ == "__main__":
    unittest.main()

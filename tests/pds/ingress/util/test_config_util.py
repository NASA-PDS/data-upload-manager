#!/usr/bin/env python3
import logging
import os
import tempfile
import unittest
from importlib.resources import files
from os.path import join
from unittest.mock import patch

import pds.ingress.util.config_util
from pds.ingress.util.config_util import bucket_for_path
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.config_util import initialize_bucket_map
from pds.ingress.util.config_util import SanitizingConfigParser
from pds.ingress.util.config_util import strtobool
from pds.ingress.util.node_util import NodeUtil


class MockS3Client:
    """Mock implementation for the boto3 S3 client class"""

    def download_file(self, Bucket: str, Key: str, Filename: str):
        """Simulate download of the file"""
        with open(Filename, "w") as outfile:
            outfile.write(
                """
                MAP:
                  NODES:
                    ATM:
                      default:
                        bucket:
                          name: dummy-bucket
                    ENG:
                      default:
                        bucket:
                          name: dummy-bucket
                    GEO:
                      default:
                        bucket:
                          name: dummy-bucket
                    IMG:
                      default:
                        bucket:
                          name: dummy-bucket
                    NAIF:
                      default:
                        bucket:
                          name: dummy-bucket
                    PPI:
                      default:
                        bucket:
                          name: dummy-bucket
                    RMS:
                      default:
                        bucket:
                          name: dummy-bucket
                    RS:
                      default:
                        bucket:
                          name: dummy-bucket
                    SBN:
                      default:
                        bucket:
                          name: dummy-bucket
                      paths:
                        - prefix: path/to/archive/2022
                          bucket:
                            name: dummy-bucket
                            storage_class: STANDARD
                        - prefix: path/to/archive/2021
                          bucket:
                            name: dummy-bucket
                            storage_class: GLACIER
                """
            )


def mock_boto3_client(*args, **kwargs):
    """Mock implementation for boto3.client to always return the Mock S3 client class"""
    return MockS3Client()


class ConfigUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = str(files("tests.pds.ingress").joinpath("util"))

    def setUp(self) -> None:
        pds.ingress.util.config_util.CONFIG = None

        os.environ["BUCKET_MAP_LOCATION"] = "config"
        os.environ["BUCKET_MAP_SCHEMA_LOCATION"] = "config"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map.yaml"
        os.environ["BUCKET_MAP_SCHEMA_FILE"] = "bucket-map.schema"
        os.environ["VERSION_LOCATION"] = "config"
        os.environ["VERSION_FILE"] = "VERSION.txt"

    def test_default_ini_config(self):
        """Test with the default configuration file"""
        parser = ConfigUtil.get_config()

        self.assertIsInstance(parser, SanitizingConfigParser)

        self.assertEqual(
            parser["API_GATEWAY"]["url_template"], "https://{id}.execute-api.{region}.amazonaws.com/{stage}/{resource}"
        )
        self.assertEqual(parser["API_GATEWAY"]["id"], "abcdefghi")
        self.assertEqual(parser["API_GATEWAY"]["region"], "us-west-2")
        self.assertEqual(parser["API_GATEWAY"]["stage"], "test")

        self.assertEqual(parser["COGNITO"]["client_id"], "123456789")
        self.assertEqual(parser["COGNITO"]["username"], "cognito_user")
        self.assertEqual(parser["COGNITO"]["password"], "cognito_pass")
        self.assertEqual(parser["COGNITO"]["region"], "us-west-2")

        self.assertEqual(parser["OTHER"]["log_level"], "INFO")
        self.assertEqual(
            parser["OTHER"]["file_format"], "[%(asctime)s] %(levelname)s %(threadName)s %(funcName)s : %(message)s"
        )
        self.assertEqual(
            parser["OTHER"]["cloudwatch_format"], "%(levelname)s %(threadName)s %(funcName)s : %(message)s"
        )
        self.assertEqual(parser["OTHER"]["console_format"], "%(message)s")
        self.assertEqual(parser["OTHER"]["log_group_name"], "/pds/nucleus/dum/client-log-group")
        self.assertEqual(parser["OTHER"]["log_file_path"], "")

        self.assertEqual(parser["DEBUG"]["simulate_batch_request_failures"], "false")
        self.assertEqual(parser["DEBUG"]["batch_request_failure_rate"], "0")
        self.assertEqual(parser["DEBUG"]["batch_request_failure_class"], "requests.exceptions.HTTPError")
        self.assertEqual(parser["DEBUG"]["simulate_ingress_failures"], "false")
        self.assertEqual(parser["DEBUG"]["ingress_failure_rate"], "0")
        self.assertEqual(parser["DEBUG"]["ingress_failure_class"], "requests.exceptions.HTTPError")

        # Ensure the sanitizing config parser removed any quotes surrounding
        # values within the config
        self.assertFalse(parser["OTHER"]["cloudwatch_format"].startswith("'"))
        self.assertFalse(parser["OTHER"]["cloudwatch_format"].endswith("'"))

        self.assertFalse(parser["OTHER"]["log_group_name"].startswith('"'))
        self.assertFalse(parser["OTHER"]["log_group_name"].endswith('"'))

    def mock_default_ini_config_path(self):
        return join(self.test_dir, "data", "mock.localstack.config.ini")

    def test_is_localstack_context(self):
        """Tests for the ConfigUtil.is_localstack_context() function"""
        # Test with default config, which is not tailored for localstack
        self.assertFalse(ConfigUtil.is_localstack_context())

        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None

        # Retest using the mock localstack config in place of the default
        with patch.object(
            pds.ingress.util.config_util.ConfigUtil, "default_config_path", self.mock_default_ini_config_path
        ):
            self.assertTrue(ConfigUtil.is_localstack_context())

        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None

    def mock_nodebug_ini_config_path(self):
        return join(self.test_dir, "data", "mock.nodebug.config.ini")

    def test_missing_debug_section(self):
        """Test parsing and use of a config that does not have a [DEBUG] section"""
        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None

        with patch.object(
            pds.ingress.util.config_util.ConfigUtil, "default_config_path", self.mock_nodebug_ini_config_path
        ):
            config = ConfigUtil.get_config()

            self.assertIsInstance(config, SanitizingConfigParser)

            # Ensure the [DEBUG] section is not present
            self.assertNotIn("DEBUG", config.sections())

            self.assertEqual(
                config.get("DEBUG", "simulate_batch_request_failures", fallback="expected_fallback"),
                "expected_fallback",
            )
            self.assertEqual(
                config.get("DEBUG", "batch_request_failure_rate", fallback="expected_fallback"), "expected_fallback"
            )
            self.assertEqual(
                config.get("DEBUG", "batch_request_failure_class", fallback="expected_fallback"), "expected_fallback"
            )
            self.assertEqual(
                config.get("DEBUG", "simulate_ingress_failures", fallback="expected_fallback"), "expected_fallback"
            )
            self.assertEqual(
                config.get("DEBUG", "ingress_failure_rate", fallback="expected_fallback"), "expected_fallback"
            )
            self.assertEqual(
                config.get("DEBUG", "ingress_failure_class", fallback="expected_fallback"), "expected_fallback"
            )

    def test_default_bucket_map(self):
        """Test parsing of the default bucket map bundled with the Lambda function"""
        os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

        bucket_map = initialize_bucket_map(logging.getLogger())

        self.assertIsNotNone(bucket_map)
        self.assertIsInstance(bucket_map, dict)
        self.assertIn("MAP", bucket_map)
        self.assertIn("NODES", bucket_map["MAP"])
        self.assertIn("SBN", bucket_map["MAP"]["NODES"])
        self.assertIn("default", bucket_map["MAP"]["NODES"]["SBN"])
        self.assertIn("bucket", bucket_map["MAP"]["NODES"]["SBN"]["default"])
        self.assertIn("name", bucket_map["MAP"]["NODES"]["SBN"]["default"]["bucket"])
        self.assertEqual(bucket_map["MAP"]["NODES"]["SBN"]["default"]["bucket"]["name"], "pds-sbn-staging-test")

    def test_custom_bucket_map_from_file(self):
        """Test parsing of a non-default bucket map bundled with the Lambda function"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", prefix="temp-bucket-map-", dir=self.test_dir
        ) as temp_bucket_file:
            temp_bucket_file.write(
                """
                MAP:
                  NODES:
                    ATM:
                      default:
                        bucket:
                          name: test-bucket-name
                    ENG:
                      default:
                        bucket:
                          name: test-bucket-name
                    GEO:
                      default:
                        bucket:
                          name: test-bucket-name
                    IMG:
                      default:
                        bucket:
                          name: test-bucket-name
                    NAIF:
                      default:
                        bucket:
                          name: test-bucket-name
                    PPI:
                      default:
                        bucket:
                          name: test-bucket-name
                    RMS:
                      default:
                        bucket:
                          name: test-bucket-name
                    RS:
                      default:
                        bucket:
                          name: test-bucket-name
                    SBN:
                      default:
                        bucket:
                          name: test-bucket-name
                """
            )

            temp_bucket_file.flush()

            os.environ["BUCKET_MAP_LOCATION"] = self.test_dir
            os.environ["BUCKET_MAP_SCHEMA_LOCATION"] = os.path.join(self.test_dir, os.pardir, "service", "config")
            os.environ["BUCKET_MAP_FILE"] = os.path.basename(temp_bucket_file.name)
            os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

            bucket_map = initialize_bucket_map(logging.getLogger())

            self.assertIsNotNone(bucket_map)
            self.assertIsInstance(bucket_map, dict)
            self.assertIn("MAP", bucket_map)
            self.assertIn("NODES", bucket_map["MAP"])
            for node_name in NodeUtil.permissible_node_ids():
                self.assertIn(node_name.upper(), bucket_map["MAP"]["NODES"])
                self.assertIn("default", bucket_map["MAP"]["NODES"][node_name.upper()])
                self.assertEqual(
                    bucket_map["MAP"]["NODES"][node_name.upper()]["default"]["bucket"]["name"], "test-bucket-name"
                )

    @patch.object(pds.ingress.util.config_util.boto3, "client", mock_boto3_client)
    def test_bucket_map_from_s3(self):
        """Test reading of a bucket map file from an S3 location"""
        os.environ["BUCKET_MAP_LOCATION"] = "s3://test-bucket/path/to/bucket/map/"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map-from-s3.yaml"
        os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

        bucket_map = initialize_bucket_map(logging.getLogger())

        # Ensure the bucket map was "downloaded" where we expect
        expected_bucket_map_path = join(os.environ["LAMBDA_TASK_ROOT"], os.environ["BUCKET_MAP_FILE"])
        self.assertTrue(os.path.exists(expected_bucket_map_path))

        try:
            self.assertIsNotNone(bucket_map)
            self.assertIsInstance(bucket_map, dict)
            self.assertIn("MAP", bucket_map)
            self.assertIn("NODES", bucket_map["MAP"])
            for node_name in NodeUtil.permissible_node_ids():
                self.assertIn(node_name.upper(), bucket_map["MAP"]["NODES"])
                self.assertIn("default", bucket_map["MAP"]["NODES"][node_name.upper()])
                self.assertEqual(
                    bucket_map["MAP"]["NODES"][node_name.upper()]["default"]["bucket"]["name"], "dummy-bucket"
                )

            self.assertIn("paths", bucket_map["MAP"]["NODES"]["SBN"])
            self.assertEqual(len(bucket_map["MAP"]["NODES"]["SBN"]["paths"]), 2)
        finally:
            # Cleanup "downloaded" dummy bucket map file
            if os.path.exists(expected_bucket_map_path):
                os.unlink(expected_bucket_map_path)

    def test_bucket_for_path(self):
        """Tests for config_util.bucket_for_path()"""
        test_node_bucket_map = {
            "default": {"bucket": {"name": "default_path_bucket"}},
            "paths": [
                {"prefix": "full/path/to/object", "bucket": {"name": "full_path_bucket"}},
                {"prefix": "substring/path/to", "bucket": {"name": "substring_path_bucket"}},
                {"prefix": "wildcard/path/to/*", "bucket": {"name": "wildcard_path_bucket"}},
            ],
        }
        logger = logging.getLogger(__name__)

        bucket = bucket_for_path(test_node_bucket_map, "full/path/to/object", logger)

        self.assertIsInstance(bucket, dict)
        self.assertIn("name", bucket)
        self.assertEqual(bucket["name"], "full_path_bucket")

        bucket = bucket_for_path(test_node_bucket_map, "substring/path/to/object", logger)

        self.assertIsInstance(bucket, dict)
        self.assertIn("name", bucket)
        self.assertEqual(bucket["name"], "substring_path_bucket")

        bucket = bucket_for_path(test_node_bucket_map, "wildcard/path/to/test/object", logger)

        self.assertIsInstance(bucket, dict)
        self.assertIn("name", bucket)
        self.assertEqual(bucket["name"], "wildcard_path_bucket")

        bucket = bucket_for_path(test_node_bucket_map, "unknown/path/to/object", logger)

        self.assertIsInstance(bucket, dict)
        self.assertIn("name", bucket)
        self.assertEqual(bucket["name"], "default_path_bucket")

    def test_strtobool(self):
        """Tests for config_util.strtobool()"""
        self.assertTrue(strtobool("true"))
        self.assertTrue(strtobool("True"))
        self.assertTrue(strtobool("t"))
        self.assertTrue(strtobool("1"))
        self.assertTrue(strtobool("Yes"))
        self.assertFalse(strtobool("false"))
        self.assertFalse(strtobool("False"))
        self.assertFalse(strtobool("f"))
        self.assertFalse(strtobool("0"))
        self.assertFalse(strtobool("NO"))

        with self.assertRaises(ValueError):
            strtobool("invalid")


if __name__ == "__main__":
    unittest.main()

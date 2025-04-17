#!/usr/bin/env python3

import logging
import os
import tempfile
import unittest
from os.path import join
from unittest.mock import patch

from pkg_resources import resource_filename

import pds.ingress.util.config_util
from pds.ingress.util.config_util import bucket_for_path
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.config_util import SanitizingConfigParser
from pds.ingress.util.config_util import bucket_for_path
from pds.ingress.util.config_util import initialize_bucket_map
from pds.ingress.util.node_util import NodeUtil


class ConfigUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = resource_filename(__name__, "")

    def setUp(self) -> None:
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

        self.assertEqual(parser["AWS"]["profile"], "AWS_Profile_1234")

        self.assertEqual(
            parser["API_GATEWAY"]["url_template"], "https://{id}.execute-api.{region}.amazonaws.com/{stage}/{resource}"
        )
        self.assertEqual(parser["API_GATEWAY"]["id"], "abcdefghi")
        self.assertEqual(parser["API_GATEWAY"]["region"], "us-west-2")
        self.assertEqual(parser["API_GATEWAY"]["stage"], "test")
        self.assertEqual(parser["API_GATEWAY"]["resource"], "request")

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


if __name__ == "__main__":
    unittest.main()

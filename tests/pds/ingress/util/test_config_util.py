#!/usr/bin/env python3
import logging
import os
import tempfile
import unittest
from importlib.resources import files
from os.path import join
from unittest.mock import patch

import pds.ingress.util.config_util
from pds.ingress.util.config_util import (
    bucket_for_path,
    ConfigUtil,
    initialize_bucket_map,
    SanitizingConfigParser,
    strtobool,
)


# ----------------------------------------------------------------------
# Mock S3 client for bucket-map-from-S3 tests
# ----------------------------------------------------------------------
class MockS3Client:
    """Mock boto3 S3 client used when BUCKET_MAP_LOCATION is s3://"""

    def download_file(self, Bucket: str, Key: str, Filename: str):
        """Writes a valid BUCKET_MAP YAML file"""
        with open(Filename, "w") as outfile:
            outfile.write(
                """
                BUCKET_MAP:
                  NODES:
                    ATM:
                      buckets:
                        staging:
                          name: dummy-staging
                        archive:
                          name: dummy-archive

                    SBN:
                      buckets:
                        staging:
                          name: dummy-staging
                        archive:
                          name: dummy-archive
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
    return MockS3Client()


# ----------------------------------------------------------------------
# Test Suite
# ----------------------------------------------------------------------
class ConfigUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = str(files("tests.pds.ingress").joinpath("util"))

    def setUp(self) -> None:
        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None

        os.environ["BUCKET_MAP_LOCATION"] = "config"
        os.environ["BUCKET_MAP_SCHEMA_LOCATION"] = "config"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map.yaml"
        os.environ["BUCKET_MAP_SCHEMA_FILE"] = "bucket-map.schema"
        os.environ["VERSION_LOCATION"] = "config"
        os.environ["VERSION_FILE"] = "VERSION.txt"

    # ------------------------------------------------------------------
    # Default config.ini parsing
    # ------------------------------------------------------------------
    def test_default_ini_config(self):
        parser = ConfigUtil.get_config()

        self.assertIsInstance(parser, SanitizingConfigParser)
        self.assertEqual(parser["API_GATEWAY"]["region"], "us-west-2")
        self.assertEqual(parser["COGNITO"]["client_id"], "123456789")
        self.assertEqual(parser["OTHER"]["log_level"], "INFO")

    # ------------------------------------------------------------------
    # is_localstack_context()
    # ------------------------------------------------------------------
    def mock_default_ini_config_path(self):
        return join(self.test_dir, "data", "mock.localstack.config.ini")

    def test_is_localstack_context(self):
        self.assertFalse(ConfigUtil.is_localstack_context())

        pds.ingress.util.config_util.CONFIG = None
        with patch.object(
                pds.ingress.util.config_util.ConfigUtil,
                "default_config_path",
                self.mock_default_ini_config_path,
        ):
            self.assertTrue(ConfigUtil.is_localstack_context())

        pds.ingress.util.config_util.CONFIG = None

    # ------------------------------------------------------------------
    # Missing [DEBUG] config block
    # ------------------------------------------------------------------
    def mock_nodebug_ini_config_path(self):
        return join(self.test_dir, "data", "mock.nodebug.config.ini")

    def test_missing_debug_section(self):
        pds.ingress.util.config_util.CONFIG = None

        with patch.object(
                pds.ingress.util.config_util.ConfigUtil,
                "default_config_path",
                self.mock_nodebug_ini_config_path,
        ):
            config = ConfigUtil.get_config()
            self.assertNotIn("DEBUG", config.sections())
            self.assertEqual(config.get("DEBUG", "simulate_ingress_failures", fallback="fallback"), "fallback")

    # ------------------------------------------------------------------
    # Validate default bucket map (schema + YAML)
    # ------------------------------------------------------------------
    def test_default_bucket_map(self):
        os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

        bucket_map = initialize_bucket_map(logging.getLogger())

        self.assertIsInstance(bucket_map, dict)
        self.assertIn("NODES", bucket_map)

        sbn = bucket_map["NODES"]["SBN"]
        self.assertIn("buckets", sbn)
        self.assertIn("staging", sbn["buckets"])
        self.assertIn("name", sbn["buckets"]["staging"])

    # ------------------------------------------------------------------
    # Custom bucket map loaded from temp file
    # ------------------------------------------------------------------
    def test_custom_bucket_map_from_file(self):
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".yaml", prefix="tmp-bucket-map-", dir=self.test_dir
        ) as temp_file:
            temp_file.write(
                """
                BUCKET_MAP:
                  NODES:
                    ATM:
                      buckets:
                        staging:
                          name: test-staging
                        archive:
                          name: test-archive
                """
            )
            temp_file.flush()

            os.environ["BUCKET_MAP_LOCATION"] = self.test_dir
            os.environ["BUCKET_MAP_FILE"] = os.path.basename(temp_file.name)
            os.environ["BUCKET_MAP_SCHEMA_LOCATION"] = join(
                self.test_dir, os.pardir, "service", "config"
            )
            os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

            bucket_map = initialize_bucket_map(logging.getLogger())

            self.assertIn("NODES", bucket_map)
            atm = bucket_map["NODES"]["ATM"]
            self.assertEqual(atm["buckets"]["staging"]["name"], "test-staging")

    # ------------------------------------------------------------------
    # Bucket map downloaded from S3 via mock boto3 client
    # ------------------------------------------------------------------
    @patch.object(pds.ingress.util.config_util.boto3, "client", mock_boto3_client)
    def test_bucket_map_from_s3(self):
        os.environ["BUCKET_MAP_LOCATION"] = "s3://dummy/map/"
        os.environ["BUCKET_MAP_FILE"] = "bucket-map-from-s3.yaml"
        os.environ["LAMBDA_TASK_ROOT"] = join(self.test_dir, os.pardir, "service")

        bucket_map = initialize_bucket_map(logging.getLogger())
        expected_path = join(os.environ["LAMBDA_TASK_ROOT"], os.environ["BUCKET_MAP_FILE"])

        self.assertTrue(os.path.exists(expected_path))
        try:
            self.assertIn("NODES", bucket_map)
            nodes = bucket_map["NODES"]

            self.assertIn("ATM", nodes)
            self.assertEqual(nodes["ATM"]["buckets"]["staging"]["name"], "dummy-staging")

            self.assertIn("paths", nodes["SBN"])
            self.assertEqual(len(nodes["SBN"]["paths"]), 2)
        finally:
            if os.path.exists(expected_path):
                os.unlink(expected_path)

    # ------------------------------------------------------------------
    # bucket_for_path() routing
    # ------------------------------------------------------------------
    def test_bucket_for_path(self):
        mapping = {
            "buckets": {
                "staging": {"name": "default-staging"},
                "archive": {"name": "default-archive"},
            },
            "paths": [
                {"prefix": "full/path/to/file", "bucket": {"name": "full-match"}},
                {"prefix": "short/path", "bucket": {"name": "short-match"}},
                {"prefix": "wild/*", "bucket": {"name": "wild-match"}},
            ],
        }

        logger = logging.getLogger(__name__)

        b = bucket_for_path(mapping, "full/path/to/file", logger)
        self.assertEqual(b["name"], "full-match")

        b = bucket_for_path(mapping, "short/path/example", logger)
        self.assertEqual(b["name"], "short-match")

        b = bucket_for_path(mapping, "wild/anything/here", logger)
        self.assertEqual(b["name"], "wild-match")

        b = bucket_for_path(mapping, "no/match/here", logger)
        self.assertEqual(b["name"], "default-staging")

    # ------------------------------------------------------------------
    # strtobool tests
    # ------------------------------------------------------------------
    def test_strtobool(self):
        self.assertTrue(strtobool("true"))
        self.assertTrue(strtobool("Yes"))
        self.assertFalse(strtobool("false"))
        self.assertFalse(strtobool("NO"))
        with self.assertRaises(ValueError):
            strtobool("xxx")


if __name__ == "__main__":
    unittest.main()

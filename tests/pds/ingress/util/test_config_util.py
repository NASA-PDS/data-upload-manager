#!/usr/bin/env python3
import unittest
from os.path import join
from unittest.mock import patch

import pds.ingress.util.config_util
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.config_util import SanitizingConfigParser
from pkg_resources import resource_filename


class ConfigUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = resource_filename(__name__, "")

    def test_default_config(self):
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

    def mock_default_config_path(self):
        return join(self.test_dir, "data", "mock.localstack.config.ini")

    def test_is_localstack_context(self):
        """Tests for the ConfigUtil.is_localstack_context() function"""
        # Test with default config, which is not tailored for localstack
        self.assertFalse(ConfigUtil.is_localstack_context())

        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None

        # Retest using the mock localstack config in place of the default
        with patch.object(
            pds.ingress.util.config_util.ConfigUtil, "default_config_path", self.mock_default_config_path
        ):
            self.assertTrue(ConfigUtil.is_localstack_context())

        # Reset cached config
        pds.ingress.util.config_util.CONFIG = None


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
import unittest

from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.config_util import SanitizingConfigParser


class ConfigUtilTest(unittest.TestCase):
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
            parser["OTHER"]["log_format"], "%(levelname)s %(threadName)s %(name)s:%(funcName)s %(message)s"
        )
        self.assertEqual(parser["OTHER"]["log_group_name"], "/pds/nucleus/dum/client-log-group")

        # Ensure the sanitizing config parser removed any quotes surrounding
        # values within the config
        self.assertFalse(parser["OTHER"]["log_format"].startswith("'"))
        self.assertFalse(parser["OTHER"]["log_format"].endswith("'"))

        self.assertFalse(parser["OTHER"]["log_group_name"].startswith('"'))
        self.assertFalse(parser["OTHER"]["log_group_name"].endswith('"'))


if __name__ == "__main__":
    unittest.main()

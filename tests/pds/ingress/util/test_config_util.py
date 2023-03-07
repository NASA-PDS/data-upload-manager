#!/usr/bin/env python3

import unittest

from src.pds.ingress.util.config_util import ConfigUtil


class ConfigUtilTest(unittest.TestCase):

    def test_default_config(self):
        """Test with the default configuration file"""
        parser = ConfigUtil.get_config()

        self.assertEqual(parser["AWS"]["profile"], "AWS_Profile_1234")

        self.assertEqual(parser["API_GATEWAY"]["url_template"],
                         "https://{id}.execute-api.{region}.amazonaws.com/{stage}/{request}")
        self.assertEqual(parser["API_GATEWAY"]["id"], "abcdefghi")
        self.assertEqual(parser["API_GATEWAY"]["region"], "us-west-2")
        self.assertEqual(parser["API_GATEWAY"]["stage"], "test")
        self.assertEqual(parser["API_GATEWAY"]["resource"], "request")

        self.assertEqual(parser["OTHER"]["log_level"], "INFO")

if __name__ == "__main__":
    unittest.main()
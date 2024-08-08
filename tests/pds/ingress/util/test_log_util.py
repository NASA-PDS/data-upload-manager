#!/usr/bin/env python3
import json as json_module
import unittest
from unittest.mock import patch

import pds.ingress.util.log_util as log_util
import requests
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.node_util import NodeUtil


class LogUtilTest(unittest.TestCase):
    def setUp(self):
        if log_util.CLOUDWATCH_HANDLER:
            log_util.CLOUDWATCH_HANDLER.bearer_token = None
            log_util.CLOUDWATCH_HANDLER.node_id = None

    def test_setup_logging(self):
        """Tests for log_util.setup_logging()"""
        logger = log_util.get_logger("test_setup_logging")
        config = ConfigUtil.get_config()

        logger = log_util.setup_logging(logger, config)

        self.assertEqual(logger.level, log_util.get_log_level("debug"))
        self.assertEqual(len(logger.handlers), 2)

        self.assertIn(log_util.CONSOLE_HANDLER, logger.handlers)
        self.assertEqual(log_util.CONSOLE_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))
        self.assertIsNotNone(log_util.CONSOLE_HANDLER.formatter)
        self.assertEqual(log_util.CONSOLE_HANDLER.formatter._fmt, config["OTHER"]["log_format"])

        self.assertIn(log_util.CLOUDWATCH_HANDLER, logger.handlers)
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))
        self.assertIsNotNone(log_util.CLOUDWATCH_HANDLER.formatter)
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.formatter._fmt, config["OTHER"]["log_format"])
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.log_group_name, config["OTHER"]["log_group_name"])

        self.assertIsNone(log_util.CLOUDWATCH_HANDLER.bearer_token)
        self.assertIsNone(log_util.CLOUDWATCH_HANDLER.node_id)

        # Test with log level override
        log_util.CONSOLE_HANDLER = None
        log_util.CLOUDWATCH_HANDLER = None
        logger = log_util.get_logger("test2", log_util.get_log_level("warning"))

        self.assertEqual(len(logger.handlers), 2)
        self.assertIsNotNone(log_util.CONSOLE_HANDLER)
        self.assertIsNotNone(log_util.CLOUDWATCH_HANDLER)
        self.assertEqual(logger.level, log_util.get_log_level("debug"))
        self.assertEqual(log_util.CONSOLE_HANDLER.level, log_util.get_log_level("warning"))

        # Provided log level should only affect console, CloudWatch logger
        # always defaults to what is defined in the INI
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))

    def test_send_log_events_to_cloud_watch(self):
        """Tests for CloudWatchHandler.send_log_events_to_cloud_watch()"""
        logger = log_util.get_logger("test_send_log_events_to_cloud_watch")

        logger.handlers.remove(log_util.CONSOLE_HANDLER)

        logger.info("Test message")

        # Ensure we see the following message logged when attempting to flush
        # to CloudWatch before the Cognito authentication information is set
        with self.assertLogs(level="WARNING") as cm:
            log_util.CLOUDWATCH_HANDLER.flush()
            self.assertIn(
                "WARNING:pds.ingress.util.log_util:Unable to submit to CloudWatch Logs, reason: "
                "Bearer token and/or Node ID was never set on CloudWatchHandler, "
                "unable to communicate with API Gateway endpoint for CloudWatch Logs.",
                cm.output,
            )

        # Set dummy Cognito authentication values on handler
        log_util.CLOUDWATCH_HANDLER.bearer_token = "Bearer faketoken"
        log_util.CLOUDWATCH_HANDLER.node_id = "eng"

        def requests_post_patch(url, data=None, json=None, **kwargs):
            """Mock implementation for requests.post()"""
            config = ConfigUtil.get_config()

            # Test that the API gateway URL was formatted as expected
            self.assertIn(config["API_GATEWAY"]["id"], url)
            self.assertIn(config["API_GATEWAY"]["region"], url)
            self.assertIn(config["API_GATEWAY"]["stage"], url)

            # Check contents of the request payload
            payload = json_module.loads(data)
            self.assertIn("logGroupName", payload)
            self.assertIn("logStreamName", payload)
            self.assertEqual(payload["logGroupName"], log_util.CLOUDWATCH_HANDLER.log_group_name)

            # Ensure node ID assigned to the handler was assigned to the log stream name
            log_stream_name = payload["logStreamName"]
            self.assertIn("eng", log_stream_name)

            # If log events were included, ensure test log message was captured
            if "logEvents" in payload:
                self.assertEqual(len(payload["logEvents"]), 1)
                self.assertEqual(
                    payload["logEvents"][0]["message"],
                    "INFO MainThread test_send_log_events_to_cloud_watch:test_send_log_events_to_cloud_watch Test message",
                )

            # Ensure the authentication headers were set as expected
            headers = kwargs["headers"]
            self.assertIn("Authorization", headers)
            self.assertIn("UserGroup", headers)
            self.assertEqual(headers["Authorization"], "Bearer faketoken")
            self.assertEqual(headers["UserGroup"], NodeUtil.node_id_to_group_name("eng"))

            response = requests.Response()
            response.status_code = 200

            return response

        with patch.object(log_util.requests, "post", requests_post_patch):
            log_util.CLOUDWATCH_HANDLER.flush()

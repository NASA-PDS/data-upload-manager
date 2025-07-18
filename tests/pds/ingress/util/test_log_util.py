#!/usr/bin/env python3
import json as json_module
import os
import unittest
from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import patch

import pds.ingress.util.log_util as log_util
import requests
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.node_util import NodeUtil
from requests import Response
from requests.exceptions import ConnectionError


class LogUtilTest(unittest.TestCase):
    def setUp(self):
        if log_util.CLOUDWATCH_HANDLER:
            log_util.CLOUDWATCH_HANDLER.bearer_token = None
            log_util.CLOUDWATCH_HANDLER.node_id = None

    def tearDown(self):
        if log_util.FILE_HANDLER:
            if os.path.exists(log_util.FILE_HANDLER.baseFilename):
                os.unlink(log_util.FILE_HANDLER.baseFilename)

    def test_setup_logging(self):
        """Tests for log_util.setup_logging()"""
        config = ConfigUtil.get_config()

        logger = log_util.get_logger("test_setup_logging")

        self.assertEqual(logger.level, log_util.get_log_level("debug"))
        self.assertEqual(len(logger.handlers), 3)

        self.assertIn(log_util.FILE_HANDLER, logger.handlers)
        self.assertEqual(log_util.FILE_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))
        self.assertIsNotNone(log_util.FILE_HANDLER.formatter)
        self.assertEqual(log_util.FILE_HANDLER.formatter._fmt, config["OTHER"]["file_format"])
        self.assertIsNotNone(log_util.FILE_HANDLER.baseFilename)

        self.assertIn(log_util.CONSOLE_HANDLER, logger.handlers)
        self.assertEqual(log_util.CONSOLE_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))
        self.assertIsNotNone(log_util.CONSOLE_HANDLER.formatter)
        self.assertEqual(log_util.CONSOLE_HANDLER.formatter._fmt, config["OTHER"]["console_format"])

        self.assertIn(log_util.CLOUDWATCH_HANDLER, logger.handlers)
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.level, log_util.get_log_level(config["OTHER"]["log_level"]))
        self.assertIsNotNone(log_util.CLOUDWATCH_HANDLER.formatter)
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.formatter._fmt, config["OTHER"]["cloudwatch_format"])
        self.assertEqual(log_util.CLOUDWATCH_HANDLER.log_group_name, config["OTHER"]["log_group_name"])

        self.assertIsNone(log_util.CLOUDWATCH_HANDLER.bearer_token)
        self.assertIsNone(log_util.CLOUDWATCH_HANDLER.node_id)

        # Test with log level override
        log_util.CONSOLE_HANDLER = None
        log_util.CLOUDWATCH_HANDLER = None
        logger = log_util.get_logger("test2", log_util.get_log_level("warning"), file=False)

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
        logger = log_util.get_logger("test_send_log_events_to_cloud_watch", console=False, file=False)

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
            response.status_code = HTTPStatus.OK

            return response

        with patch.object(log_util.requests, "post", requests_post_patch):
            log_util.CLOUDWATCH_HANDLER.flush()

    def test_send_log_events_to_cloud_watch_w_backoff_retry(self):
        """Test use of the backoff/retry decorator on send_log_events_to_cloud_watch"""
        logger = log_util.get_logger("test_send_log_events_to_cloud_watch_w_backoff_retry", console=False, file=False)

        logger.info("Test message")

        # Set dummy Cognito authentication values on handler
        log_util.CLOUDWATCH_HANDLER.bearer_token = "Bearer faketoken"
        log_util.CLOUDWATCH_HANDLER.node_id = "eng"

        # Set up some canned HTTP responses for the transient error codes we retry for
        response_400 = Response()
        response_400.status_code = HTTPStatus.BAD_REQUEST
        response_408 = Response()
        response_408.status_code = HTTPStatus.REQUEST_TIMEOUT
        response_425 = Response()
        response_425.status_code = HTTPStatus.TOO_EARLY
        response_429 = Response()
        response_429.status_code = HTTPStatus.TOO_MANY_REQUESTS
        response_500 = Response()
        response_500.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        response_502 = Response()
        response_502.status_code = HTTPStatus.BAD_GATEWAY
        response_503 = Response()
        response_503.status_code = HTTPStatus.SERVICE_UNAVAILABLE
        response_504 = Response()
        response_504.status_code = HTTPStatus.GATEWAY_TIMEOUT
        response_509 = Response()
        response_509.status_code = 509  # Bandwidth Limit Exceeded (non-standard code used by AWS)

        responses = [
            response_400,
            response_408,
            response_425,
            response_429,
            response_500,
            response_502,
            response_503,
            response_504,
            response_509,
        ]

        # Set up a Mock function for session.get which will cycle through all
        # transient error codes before finally returning success (200)
        mock_requests_post = MagicMock(side_effect=responses)

        with patch.object(log_util.requests, "post", mock_requests_post):
            log_util.CLOUDWATCH_HANDLER.flush()

        # Ensure we retired at least once for each of the failed responses
        self.assertGreaterEqual(mock_requests_post.call_count, len(responses))

        # Now try with a simulated connection error, which is not caught by requests.raise_for_status()
        response_104 = Response()
        response_104.status_code = 104
        mock_requests_post = MagicMock(side_effect=ConnectionError("Connection reset by peer", response=response_104))

        with patch.object(log_util.requests, "post", mock_requests_post):
            log_util.CLOUDWATCH_HANDLER.flush()

        # Ensure we retried at least once for a connection error
        self.assertGreaterEqual(mock_requests_post.call_count, 1)

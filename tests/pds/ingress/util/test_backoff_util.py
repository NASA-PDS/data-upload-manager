#!/usr/bin/env python3
import unittest
from importlib.resources import files
from os.path import join

import pds.ingress.util.backoff_util
import pds.ingress.util.config_util
import requests
import requests_mock
from pds.ingress.util.backoff_util import simulate_batch_request_failure
from pds.ingress.util.backoff_util import simulate_ingress_failure


class BackoffUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_dir = str(files("tests.pds.ingress").joinpath("util"))

    def setUp(self) -> None:
        config_path = join(self.test_dir, "data", "mock.backoff.config.ini")
        pds.ingress.util.config_util.CONFIG = None
        pds.ingress.util.config_util.ConfigUtil.get_config(config_path)

    def test_simulate_batch_request_failure(self):
        # Unit tests for the simulate_batch_request_failure function context manager
        api_gateway_url = "https://example.com/api"

        with simulate_batch_request_failure(api_gateway_url) as mock_requests:
            self.assertTrue(isinstance(mock_requests, requests_mock.Mocker))
            self.assertTrue(mock_requests.real_http)

            # Ensure an attempt to submit a POST request to the configured URL
            # raises the error class specified in the INI config (builtins.TypeError)
            with self.assertRaises(TypeError):
                requests.post(api_gateway_url, data=b"")

            # Check if the URL was registered with the mock_requests
            registered_urls = [req.url for req in mock_requests.request_history]
            self.assertIn(api_gateway_url, registered_urls)

            # Ensure mock_requests was invoked for our request
            self.assertTrue(mock_requests.called)
            self.assertGreaterEqual(mock_requests.call_count, 1)
            self.assertEqual(str(mock_requests.last_request), "POST https://example.com/api")

        # Ensure that the mock_requests context manager cleans up after itself
        mock_requests = requests_mock.Mocker(real_http=True)
        self.assertFalse(mock_requests.called)
        self.assertEqual(mock_requests.call_count, 0)
        self.assertListEqual(mock_requests.request_history, [])

    def test_simulate_ingress_failure(self):
        # Unit tests for the simulate_ingress_failure function context manager
        s3_ingress_url = "https://example.com/ingress"

        with simulate_ingress_failure(s3_ingress_url) as mock_requests:
            self.assertTrue(isinstance(mock_requests, requests_mock.Mocker))
            self.assertTrue(mock_requests.real_http)

            # Ensure an attempt to submit a PUT request to the configured URL
            # returns a response with a 403 status code, simulating access denied error
            response = requests.put(s3_ingress_url, data=b"")

            self.assertEqual(response.status_code, 403)

            # Check if the URL was registered with the mock_requests
            registered_urls = [req.url for req in mock_requests.request_history]
            self.assertIn(s3_ingress_url, registered_urls)

            # Ensure mock_requests was invoked for our request
            self.assertTrue(mock_requests.called)
            self.assertGreaterEqual(mock_requests.call_count, 1)
            self.assertEqual(str(mock_requests.last_request), "PUT https://example.com/ingress")

        # Ensure that the mock_requests context manager cleans up after itself
        mock_requests = requests_mock.Mocker(real_http=True)
        self.assertFalse(mock_requests.called)
        self.assertEqual(mock_requests.call_count, 0)
        self.assertListEqual(mock_requests.request_history, [])


if __name__ == "__main__":
    unittest.main()

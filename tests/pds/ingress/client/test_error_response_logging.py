import logging
import unittest
from unittest.mock import MagicMock

from pds.ingress.client.pds_ingress_client import log_error_response_details


class ErrorResponseLoggingTest(unittest.TestCase):
    """Tests for the logging of failed ingress request responses"""

    def setUp(self) -> None:
        self.logger = logging.getLogger("test_error_response_logging")

    @staticmethod
    def _response(text, headers=None):
        response = MagicMock()
        response.text = text
        response.headers = headers or {}
        return response

    def test_logs_body_and_request_ids(self):
        """The service response body and API Gateway request IDs are logged"""
        response = self._response(
            '{"error": "Internal server error", "request_id": "abc-123"}',
            {"x-amzn-RequestId": "gateway-request-id", "x-amz-apigw-id": "apigw-id"},
        )

        with self.assertLogs(logger=self.logger, level="ERROR") as cm:
            log_error_response_details(self.logger, response)

        output = "\n".join(cm.output)

        self.assertIn('Response from service: {"error": "Internal server error", "request_id": "abc-123"}', output)
        self.assertIn("x-amzn-RequestId: gateway-request-id", output)
        self.assertIn("x-amz-apigw-id: apigw-id", output)

    def test_truncates_long_body(self):
        """A long response body is truncated"""
        response = self._response("x" * 5000)

        with self.assertLogs(logger=self.logger, level="ERROR") as cm:
            log_error_response_details(self.logger, response, max_body_length=100)

        self.assertEqual(len(cm.output), 1)
        self.assertIn("x" * 100 + "... (truncated)", cm.output[0])
        self.assertNotIn("x" * 101, cm.output[0])

    def test_empty_body_and_no_headers(self):
        """Nothing is logged when the response carries no body or request IDs"""
        response = self._response("")

        with self.assertNoLogs(logger=self.logger, level="ERROR"):
            log_error_response_details(self.logger, response)


if __name__ == "__main__":
    unittest.main()

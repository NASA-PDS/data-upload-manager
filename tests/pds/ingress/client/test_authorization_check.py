"""
Tests for early authorization check functionality in pds_ingress_client.

These tests verify that unauthorized users receive clear error messages
even when attempting to upload empty directories or nonexistent files.
"""
import json
from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from pds.ingress.client.pds_ingress_client import check_authorization


class TestAuthorizationCheck:
    """Test suite for the check_authorization function."""

    @pytest.fixture
    def api_gateway_config(self):
        """Fixture providing mock API Gateway configuration."""
        return {
            "url_template": "https://{id}.execute-api.{region}.amazonaws.com/{stage}/{resource}",
            "id": "test-api-id",
            "region": "us-west-2",
            "stage": "dev",
        }

    @patch("pds.ingress.client.pds_ingress_client.requests.post")
    @patch("pds.ingress.client.pds_ingress_client.BEARER_TOKEN", "mock-bearer-token")
    def test_check_authorization_unauthorized_returns_401(self, mock_post, api_gateway_config):
        """
        Test that check_authorization properly handles 401 Unauthorized response.

        When a user is not authorized, the API returns 401 and the function
        should exit with clear error messaging.
        """
        # Mock the API response for unauthorized user
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.UNAUTHORIZED
        mock_response.reason = "Unauthorized"
        mock_post.return_value = mock_response

        # Verify that sys.exit(1) is called for unauthorized users
        with pytest.raises(SystemExit) as exc_info:
            check_authorization("eng", api_gateway_config)

        assert exc_info.value.code == 1
        mock_post.assert_called_once()

    @patch("pds.ingress.client.pds_ingress_client.requests.post")
    @patch("pds.ingress.client.pds_ingress_client.BEARER_TOKEN", "mock-bearer-token")
    def test_check_authorization_forbidden_returns_403(self, mock_post, api_gateway_config):
        """
        Test that check_authorization properly handles 403 Forbidden response.

        When a user's network is not authorized, the API returns 403 and the
        function should exit with clear error messaging.
        """
        # Mock the API response for forbidden access
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.FORBIDDEN
        mock_response.reason = "Forbidden"
        mock_post.return_value = mock_response

        # Verify that sys.exit(1) is called for forbidden users
        with pytest.raises(SystemExit) as exc_info:
            check_authorization("eng", api_gateway_config)

        assert exc_info.value.code == 1
        mock_post.assert_called_once()

    @patch("pds.ingress.client.pds_ingress_client.requests.post")
    @patch("pds.ingress.client.pds_ingress_client.BEARER_TOKEN", "mock-bearer-token")
    def test_check_authorization_authorized_returns_200(self, mock_post, api_gateway_config):
        """
        Test that check_authorization succeeds for authorized users.

        When a user is properly authorized, the API returns 200 with an empty
        response batch, and the function should return normally without error.
        """
        # Mock the API response for authorized user
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.OK
        mock_response.json.return_value = []  # Empty batch response
        mock_post.return_value = mock_response

        # Should not raise any exception or exit
        check_authorization("eng", api_gateway_config)

        # Verify the request was made with an empty batch
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # Verify empty batch was sent
        request_body = json.loads(call_args[1]["data"])
        assert request_body == []

    @patch("pds.ingress.client.pds_ingress_client.requests.post")
    @patch("pds.ingress.client.pds_ingress_client.BEARER_TOKEN", "mock-bearer-token")
    def test_check_authorization_sends_proper_headers(self, mock_post, api_gateway_config):
        """
        Test that check_authorization sends proper authentication headers.

        Verify that the authorization check includes the bearer token and
        other required headers in the request.
        """
        # Mock the API response
        mock_response = MagicMock()
        mock_response.status_code = HTTPStatus.OK
        mock_response.json.return_value = []
        mock_post.return_value = mock_response

        check_authorization("eng", api_gateway_config)

        # Verify headers were sent correctly
        call_args = mock_post.call_args
        headers = call_args[1]["headers"]

        assert "Authorization" in headers
        assert headers["Authorization"] == "mock-bearer-token"
        assert headers["content-type"] == "application/json"
        assert call_args[1]["timeout"] == 15

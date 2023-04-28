#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import pds.ingress.util.auth_util
from pds.ingress.util.auth_util import AuthUtil


class MockCognitoClient:
    """Mock implementation for the boto3 Cognito client class"""

    def initiate_auth(self, AuthFlow, AuthParameters, ClientId):
        """Simulate an authentication attempt"""
        if AuthParameters["PASSWORD"] == "good_pass":
            return {"AuthenticationResult": AuthUtilTest.authentication_result}
        else:
            raise Exception("Incorrect username or password.")


def mock_boto3_client(*args, **kwargs):
    """Mock implementation for boto3.client to always return the Mock Cognito client class"""
    return MockCognitoClient()


class AuthUtilTest(unittest.TestCase):
    authentication_result = {}

    @classmethod
    def setUpClass(cls) -> None:
        # Create a dummy authentication result from Cognito
        cls.authentication_result = {
            "AccessToken": "123abc",
            "ChallengeParameters": {},
            "ExpiresIn": 3600,
            "IdToken": "456ijk",
            "RefreshToken": "789xyz",
            "TokenType": "Bearer",
        }

    @patch.object(
        pds.ingress.util.auth_util.boto3,
        "client",
        mock_boto3_client,
    )
    def test_perform_cognito_authentication(self):
        """Tests for AuthUtil.perform_cognito_authentication"""
        # Test with a dummy Cognito configuration containing a "valid" username and password
        cognito_config = {
            "username": "cognito_user",
            "password": "good_pass",
            "client_id": "cognito_client_id",
            "region": "cognito_region",
        }

        authentication_result = AuthUtil.perform_cognito_authentication(cognito_config)

        self.assertIsInstance(authentication_result, dict)
        self.assertDictEqual(authentication_result, self.authentication_result)

        # Retry with "invalid" credentials
        cognito_config["password"] = "bad_pass"

        with self.assertRaises(
            RuntimeError, msg="Failed to authenticate to Cognito, reason: Incorrect username or password."
        ):
            AuthUtil.perform_cognito_authentication(cognito_config)

    def test_create_bearer_token(self):
        """Tests for AuthUtil.create_bearer_token"""
        bearer_token = AuthUtil.create_bearer_token(self.authentication_result)

        self.assertIsInstance(bearer_token, str)
        self.assertTrue(bearer_token.startswith("Bearer"))

        access_token = bearer_token.split(" ")[-1]

        self.assertEqual(access_token, self.authentication_result["AccessToken"])

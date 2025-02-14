"""
============
auth_util.py
============

Module containing functions for performing user authentication to the
Ingress Service Lambda.

"""
import boto3  # type: ignore

from .config_util import ConfigUtil
from .log_util import get_logger


class AuthUtil:
    """
    Class used to roll up methods related to user authentication to the
    Ingress Service Lambda.
    """

    @staticmethod
    def perform_cognito_authentication(cognito_config):
        """
        Authenticates the current user of the Upload Service to AWS Cognito
        based on the settings of the Cognito portion of the INI config.

        Parameters
        ----------
        cognito_config : dict
            The COGNITO portion of the parsed INI config, containing configuration
            details such as the username and password to authenticate with.

        Returns
        -------
        authentication_result : dict
            Dictionary containing the results of a successful Cognito
            authentication, including the Access Token.

        Raises
        ------
        RuntimeError
            If authentication fails for any reason.

        """
        logger = get_logger("perform_cognito_authentication")

        if ConfigUtil.is_localstack_context():
            client = boto3.client("cognito-idp", endpoint_url="http://localhost.localstack.cloud:4566")
        else:
            client = boto3.client("cognito-idp", region_name=cognito_config["region"])

        auth_params = {"USERNAME": cognito_config["username"], "PASSWORD": cognito_config["password"]}

        logger.info("Performing Cognito authentication for user %s", cognito_config["username"])

        try:
            response = client.initiate_auth(
                AuthFlow="USER_PASSWORD_AUTH", AuthParameters=auth_params, ClientId=cognito_config["client_id"]
            )
        except Exception as err:
            raise RuntimeError(f"Failed to authenticate to Cognito, reason: {str(err)}") from err

        logger.info("Authentication successful")

        authentication_result = response["AuthenticationResult"]

        return authentication_result

    @staticmethod
    def create_bearer_token(authentication_result):
        """
        Formats a Bearer token from a successful AWS Cognito authentication
        result.

        Parameters
        ----------
        authentication_result : dict
            Dictionary containing the results of a successful Cognito
            authentication, including the Access Token.

        Returns
        -------
        bearer_token : str
            A Bearer token suitable for use with an Authentication header in
            an HTTP request.

        """
        access_token = authentication_result["AccessToken"]

        bearer_token = f"Bearer {access_token}"

        return bearer_token

    @staticmethod
    def refresh_auth_token(cognito_config, refresh_token):
        """
        Performs a Cognito authentication token refresh request, returning a
        new authentication token for use with the worker threads and CloudWatch
        logger.

        Parameters
        ----------
        cognito_config : dict
            The Cognito configuration parameters as read from the INI config.
        refresh_token : str
            The refresh token provided by Cognito.

        Returns
        -------
        authentication_result : dict
            Dictionary containing the results of the authentication refresh.
            This includes an updated authentication token and expiration time.

        """
        logger = get_logger("refresh_auth_token", console=False)

        client = boto3.client("cognito-idp", region_name=cognito_config["region"])

        auth_params = {"REFRESH_TOKEN": refresh_token}

        logger.info("Refreshing authentication token")

        try:
            response = client.initiate_auth(
                AuthFlow="REFRESH_TOKEN_AUTH", AuthParameters=auth_params, ClientId=cognito_config["client_id"]
            )
        except Exception as err:
            raise RuntimeError(f"Failed to refresh Cognito authentication token, reason: {str(err)}") from err

        logger.info("Token refresh successful")

        authentication_result = response["AuthenticationResult"]

        return authentication_result

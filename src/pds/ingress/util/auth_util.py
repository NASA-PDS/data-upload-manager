"""
============
auth_util.py
============

Module containing functions for performing user authentication to the
Ingress Service Lambda.

"""
import logging

import boto3  # type: ignore

logger = logging.getLogger(__name__)


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
        client = boto3.client("cognito-idp", region_name=cognito_config["region"])

        auth_params = {"USERNAME": cognito_config["username"], "PASSWORD": cognito_config["password"]}

        logger.info(f"Performing Cognito authentication for user {cognito_config['username']}")

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
        logger.info("Creating Bearer token")

        access_token = authentication_result["AccessToken"]

        bearer_token = f"Bearer {access_token}"

        return bearer_token

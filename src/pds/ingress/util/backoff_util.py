"""
===============
backoff_util.py
===============

Module containing functions related to utilization of the backoff module for
automatic backoff/retry of HTTP requests.

"""
import importlib
import multiprocessing
import random
from contextlib import contextmanager
from http import HTTPStatus

import requests_mock
from pds.ingress.util.config_util import ConfigUtil
from pds.ingress.util.config_util import strtobool

# When leveraging this module with the Lambda service functions, the requests
# module will not be available within the Python runtime.
# It should not be needed by those Lambda's, so use MagicMock to bypass any
# import errors
try:
    import requests
    from requests.exceptions import ConnectionError, SSLError
except ImportError:
    from unittest.mock import MagicMock

    requests = MagicMock()
    ConnectionError = MagicMock()
    SSLError = MagicMock()


MOCK_REQUESTS_SEMAPHORE = multiprocessing.Semaphore(1)


def fatal_code(err: requests.exceptions.RequestException) -> bool:
    """
    Determines if the HTTP return code associated with a requests exception
    corresponds to a fatal error or not. If the error is of a transient nature,
    this function will return False, indicating to the backoff decorator that
    the reqeust should be retried. Otherwise, a return value of True will
    cause any backoff/reties to be abandoned.
    """
    if err.response is not None:
        # HTTP codes indicating a transient error (including throttling) which
        # are worth retrying after a backoff
        transient_codes = [
            104,  # Connection reset, could be result of throttling by AWS
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.REQUEST_TIMEOUT,
            HTTPStatus.TOO_EARLY,
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
            509,  # Bandwidth Limit Exceeded (non-standard code used by AWS)
        ]

        return err.response.status_code not in transient_codes
    elif isinstance(err, ConnectionError):
        # Connection error could be transient due to throttling from AWS
        return False
    elif isinstance(err, SSLError):
        # Some errors returned from AWS manifest as SSLErrors when AWS terminates
        # the connection on their end. This makes it hard to tell if
        # the error is recoverable, so just default to retrying
        return False
    else:
        # No response to interrogate, so default to no retry
        return True


def check_failure_chance(percentage: int) -> bool:
    """
    Checks if a simulated failure event should occur based on a given percentage
    chance.

    Parameters
    ----------
    percentage : int
        The desired percentage chance (e.g., 70 for 70%).

    Returns
    -------
        bool: True if the failure should occur, False otherwise.

    Raises
    ------
    ValueError: If the percentage is not between 0 and 100.

    """
    if not (0 <= percentage <= 100):
        raise ValueError("Percentage must be between 0 and 100.")

    # Generate a random float between 0.0 and 1.0
    random_number = random.random()

    # Convert the percentage to a decimal for comparison
    chance_threshold = percentage / 100.0

    return random_number < chance_threshold


def _simulate_requests_failure(
    mock_requests, url, http_method, enable_key, failure_rate_key, failure_class_key, failure_status_code_key
):
    """
    Simulates a random failure for S3 ingress by registering the provided
    ingress URL with the requests mocker to raise an HTTPError exception.

    Whether the failure is simulated is determined by the `simulate_ingress_failures`
    configuration option and the `ingress_failure_rate` percentage chance within
    the optional DEBUG section of the INI config. If this section is not present,
    this function should always default to not simulating a failure.

    If the failure is not simulated, the mock_requests instance is reset to
    ensure no previous failures are registered.

    Parameters
    ----------
    mock_requests : requests_mock.Mocker
        The requests mocker instance to register the simulated failure with.
    url : str
        The URL to which the simulated failure will be applied.
    http_method : str
        HTTP method to register the failure for (e.g., 'POST', 'PUT').
    enable_key : str
        Name of the INI key to check if failure simulation is enabled.
    failure_rate_key : str
        Name of the INI key that specifies the percentage chance of failure.
    failure_class_key : str
        Name of the INI key that specifies the exception class to raise on failure.

    """
    config = ConfigUtil.get_config()

    # Check if simulated failures are enabled, and if so, if we should simulate
    # a failure via mock_requests based on the configured failure chance
    if strtobool(config.get("DEBUG", enable_key, fallback="false")):
        if check_failure_chance(int(config.get("DEBUG", failure_rate_key, fallback="0"))):
            # Check if we're simulating a failure by raising an exception
            failure_class_str = config.get("DEBUG", failure_class_key, fallback=None)

            if failure_class_str is not None:
                # Dynamically import the exception class to raise
                failure_class_module, failure_exception_name = failure_class_str.rsplit(".", 1)

                module = importlib.import_module(failure_class_module)
                exception_klass = getattr(module, failure_exception_name)

                kwargs = {"exc": exception_klass}
            # Otherwise, fall back to raising an HTTPError with a status code
            else:
                failure_status_code = int(config.get("DEBUG", failure_status_code_key, fallback="500"))

                kwargs = {"status_code": failure_status_code}

            # Register the URL with the mock_requests to raise the specified exception w/ status code
            mock_requests.register_uri(http_method, url, **kwargs)

    return mock_requests


@contextmanager
def simulate_batch_request_failure(api_gateway_url):
    """
    Simulates a random failure for an ingress batch request by registering the
    provided ingress URL with the requests mocker to raise an HTTPError exception.

    Parameters
    ----------
    api_gateway_url : str
        The API Gateway URL to which the simulated failure will be applied.

    """
    with MOCK_REQUESTS_SEMAPHORE:
        with requests_mock.Mocker(real_http=True) as mock_requests:
            try:
                yield _simulate_requests_failure(
                    mock_requests,
                    api_gateway_url,
                    "POST",
                    "simulate_batch_request_failures",
                    "batch_request_failure_rate",
                    "batch_request_failure_class",
                    "batch_request_failure_status_code",
                )
            finally:
                # Remove any previously registered URL(s)
                mock_requests.reset()


@contextmanager
def simulate_ingress_failure(s3_ingress_url):
    """
    Simulates a random failure for S3 ingress by registering the provided
    ingress URL with the requests mocker to raise an HTTPError exception.

    Parameters
    ----------
    s3_ingress_url : str
        The S3 ingress URL to which the simulated failure will be applied.

    """
    with MOCK_REQUESTS_SEMAPHORE:
        with requests_mock.Mocker(real_http=True) as mock_requests:
            try:
                yield _simulate_requests_failure(
                    mock_requests,
                    s3_ingress_url,
                    "PUT",
                    "simulate_ingress_failures",
                    "ingress_failure_rate",
                    "ingress_failure_class",
                    "ingress_failure_status_code",
                )
            finally:
                # Remove any previously registered URL(s)
                mock_requests.reset()

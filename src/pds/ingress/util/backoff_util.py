"""
===============
backoff_util.py
===============

Module containing functions related to utilization of the backoff module for
automatic backoff/retry of HTTP requests.

"""
from http import HTTPStatus

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

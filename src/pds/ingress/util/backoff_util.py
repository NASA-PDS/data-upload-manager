"""
===============
backoff_util.py
===============

Module containing functions related to utilization of the backoff module for
automatic backoff/retry of HTTP requests.

"""
import requests


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
        transient_codes = [408, 425, 429, 500, 502, 503, 504, 509]

        return err.response.status_code not in transient_codes
    else:
        # No response to interrogate, so default to no retry
        return True

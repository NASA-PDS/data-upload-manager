"""
===========
log_util.py
===========

Module containing functions related to logging and set up of the logger used
with the ingress client.

"""
import json
import logging
import sys
import tempfile
from datetime import datetime
from logging.handlers import BufferingHandler

# When leveraging this module with the Lambda service functions, the backoff
# and requests modules will not be available within the Python runtime.
# They should not be needed by those Lambda's, so use MagicMock to bypass any
# import errors
try:
    import backoff
    import requests
except ImportError:
    from unittest.mock import MagicMock

    backoff = MagicMock()
    requests = MagicMock()

from .config_util import ConfigUtil
from .node_util import NodeUtil

MILLI_PER_SEC = 1000

LOG_LEVELS = {
    "critical": logging.CRITICAL,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}
"""Constant to help evaluate what level to do logging at."""

FILE_HANDLER = None
"""Handle to the StreamHandler singleton used to log to a file on disk"""

CONSOLE_HANDLER = None
"""Handle to the StreamHandler singleton used to log to the console (stdout)"""

CLOUDWATCH_HANDLER = None
"""Handle to the CloudWatchHandler singleton to be allocated to all logger objects"""

DEFAULT_FORMAT = "%(levelname)s %(threadName)s %(name)s:%(funcName)s %(message)s"
"""Default log format to fall back to if not defined by the INI config."""


class SingleLogFilter(logging.Filter):
    """Simple log filter to ensure each unique log message is only logged once."""

    def __init__(self, name=""):
        super().__init__(name)
        self.logged_messages = set()

    def filter(self, record):
        """Filters out the provided log record if we've seen it before"""
        log_message = record.getMessage()

        if log_message not in self.logged_messages:
            self.logged_messages.add(log_message)
            return True

        return False


SINGLE_LOG_FILTER = SingleLogFilter()
"""Singleton instance for the filter used to ensure duplicate messages are only logged once"""


def get_log_level(log_level):
    """Translates name of a log level to the constant used by the logging module"""
    if log_level is not None:
        return LOG_LEVELS.get(log_level.lower())


def get_logger(name, log_level=None, cloudwatch=True, console=True, file=True):
    """
    Returns the logging object for the provided module name.

    Parameters
    ----------
    name : str
        Name of the module to get a logger for.
    log_level : int, optional
        The logging level to use. If not provided, the level will be determined
        from the INI config.
    cloudwatch : bool, optional
        If true, include the CloudWatch Handler in the returned logger.
        Defaults to true.
    console : bool, optional
        If true, include the Console Handler in the returned logger.
        Defaults to true.
    file : bool, optional
        If true, include the File Handler in the returned logger.
        Defaults to true.

    Returns
    -------
    logger : logging.logger
        The logger for the specified module name.

    """
    _logger = logging.getLogger(name)

    # Set default level for the parent logger to its "lowest" value (debug),
    # this is necessary so the handlers can take on separate "higher" levels
    # (info, warning, etc..)
    _logger.setLevel(logging.DEBUG)

    _logger.handlers.clear()

    config = ConfigUtil.get_config()

    # Assign appropriate handlers to this logger based on what was requested
    if cloudwatch:
        _logger = setup_cloudwatch_log(_logger, config)

    if console:
        _logger = setup_console_log(_logger, config, log_level)

    if file:
        _logger = setup_file_log(_logger, config, log_level)

    return _logger


def setup_file_log(logger, config, log_level):
    """
    Sets up the handler used to log to a file.

    Parameters
    ----------
    logger : logging.logger
        The logger object to set up.
    config : ConfigParser
        The parsed config used to initialize the file log handler.
    log_level : int
        The logging level to use.

    Returns
    -------
    logger : logging.logger
        The setup logger object.

    """
    global FILE_HANDLER

    # Prioritize the provided log level. If it is None, use the value from the INI
    log_level = log_level or get_log_level(config["OTHER"]["log_level"])

    # Set the format based on the setting in the INI config
    log_format = logging.Formatter(config["OTHER"].get("file_format", DEFAULT_FORMAT))

    if FILE_HANDLER is None:
        # Use the log file path specified in the config (which may have
        # originated from the command-line)
        if config["OTHER"].get("log_file_path"):
            log_file_path = config["OTHER"]["log_file_path"]
        # Otherwise, create a timestamped temporary file to capture logging to
        else:
            temp_file = tempfile.NamedTemporaryFile(
                prefix=f"dum_{datetime.now().isoformat()}_", suffix=".log", delete=False
            )
            log_file_path = temp_file.name
            temp_file.close()

        FILE_HANDLER = logging.FileHandler(log_file_path, mode="w")
        FILE_HANDLER.setLevel(log_level)
        FILE_HANDLER.setFormatter(log_format)

    if FILE_HANDLER not in logger.handlers:
        logger.addHandler(FILE_HANDLER)

    return logger


def setup_console_log(logger, config, log_level):
    """
    Sets up the handler used to log to the console.

    Parameters
    ----------
    logger : logging.logger
        The logger object to set up.
    config : ConfigParser
        The parsed config used to initialize the console log handler.
    log_level : int
        The logging level to use.

    Returns
    -------
    logger : logging.logger
        The setup logger object.

    """
    global CONSOLE_HANDLER
    global SINGLE_LOG_FILTER  # noqa F824

    # Prioritize the provided log level. If it is None, use the value from the INI
    log_level = log_level or get_log_level(config["OTHER"]["log_level"])

    # Set the format based on the setting in the INI config
    log_format = logging.Formatter(config["OTHER"].get("console_format", DEFAULT_FORMAT))

    if CONSOLE_HANDLER is None:
        CONSOLE_HANDLER = logging.StreamHandler(stream=sys.stdout)
        CONSOLE_HANDLER.setLevel(log_level)
        CONSOLE_HANDLER.setFormatter(log_format)
        CONSOLE_HANDLER.addFilter(SINGLE_LOG_FILTER)

    if CONSOLE_HANDLER not in logger.handlers:
        logger.addHandler(CONSOLE_HANDLER)

    return logger


def setup_cloudwatch_log(logger, config):
    """
    Sets up the handler used to log to AWS CloudWatch Logs.

    Notes
    -----
    After the initial call to this function, the created handler object is
    cached as the singleton to be returned by all subsequent calls to
    setup_cloudwatch_log(). This ensures that loggers for all modules submit
    their logged messages to the same buffer which is eventually submitted to
    CloudWatch.

    Parameters
    ----------
    logger : logging.logger
        The logger object to set up.
    config : ConfigParser
        The parsed config used to initialize the console log handler.

    Returns
    -------
    logger : logging.logger
        The setup logger object.

    """
    global CLOUDWATCH_HANDLER

    # Always use the level defined in the config, which can differ from the
    # level configured for the console logger
    log_level = get_log_level(config["OTHER"]["log_level"])

    log_format = logging.Formatter(config["OTHER"].get("cloudwatch_format", DEFAULT_FORMAT))

    log_group_name = config["OTHER"]["log_group_name"]

    if CLOUDWATCH_HANDLER is None:
        CLOUDWATCH_HANDLER = CloudWatchHandler(log_group_name, config["API_GATEWAY"])
        CLOUDWATCH_HANDLER.setLevel(log_level)
        CLOUDWATCH_HANDLER.setFormatter(log_format)

    if CLOUDWATCH_HANDLER not in logger.handlers:
        logger.addHandler(CLOUDWATCH_HANDLER)

    return logger


class CloudWatchHandler(BufferingHandler):
    """
    Specialization of the BufferingHandler class that submits all buffered log
    records to CloudWatch Logs via an API Gateway endpoint when flushed.

    Notes
    -----
    In order for this handler to communicate with API Gateway, the bearer_token
    and node_id properties must be set on an instance prior to the first
    invocation of the flush() method.

    """

    def __init__(self, log_group_name, api_gateway_config, capacity=512):
        super().__init__(capacity)

        self.log_group_name = log_group_name
        self.api_gateway_config = api_gateway_config
        self.creation_time = datetime.now().strftime("%s")
        self._bearer_token = None
        self._node_id = None
        self._stream_created = False

    @property
    def bearer_token(self):
        """Returns the authentication bearer token set on this handler"""
        return self._bearer_token

    @bearer_token.setter
    def bearer_token(self, token):
        """Sets the authentication bearer token on this handler"""
        self._bearer_token = token

    @property
    def node_id(self):
        """Returns the PDS node ID set on this handler"""
        return self._node_id

    @node_id.setter
    def node_id(self, _id):
        """Sets the PDS node ID on this handler"""
        self._node_id = _id

    def emit(self, record):
        """
        Emit a record.

        Append the record. If shouldFlush() tells us to, call flush() to process
        the buffer.
        """
        self.format(record)
        self.buffer.append(record)

        if self.shouldFlush(record):
            self.flush()

    def flush(self):
        """
        Flushes the buffered log messages by submitting all log records to
        AWS CloudWatch Logs via an API Gateway endpoint. After a successful
        invocation of this method, the buffer is cleared.
        """
        self.acquire()

        # Use a "console-only" logger since the console logger, since attempting
        # to log to CloudWatch from within this class could cause infinite recursion
        console_logger = get_logger(__name__, cloudwatch=False, file=False)

        try:
            log_events = [
                {
                    "timestamp": int(round(record.created)) * MILLI_PER_SEC,
                    "message": f"{record.levelname} {record.threadName} {record.name}:{record.funcName} {record.message}",
                }
                for record in self.buffer
            ]

            # CloudWatch Logs wants all records sorted by ascending timestamp
            log_events = list(sorted(log_events, key=lambda event: event["timestamp"]))

            try:
                if not ConfigUtil.is_localstack_context():
                    self.send_log_events_to_cloud_watch(log_events)
                else:
                    if CONSOLE_HANDLER and not CONSOLE_HANDLER.stream.closed:
                        console_logger.warning(
                            "Localstack context detected, skipping submission of logs to CloudWatch since it is not yet supported"
                        )
            except requests.exceptions.HTTPError as err:
                raise RuntimeError(f"{str(err)} : {err.response.text}") from err

            self.buffer.clear()
        except Exception as err:
            # Check if the underlying StreamHandler has been closed already,
            # since the logging module attempts to flush all handlers at exit
            # whether they've been closed or not
            if CONSOLE_HANDLER and not CONSOLE_HANDLER.stream.closed:
                console_logger.warning("Unable to submit to CloudWatch Logs, reason: %s", str(err))
        finally:
            self.release()

    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_time=120,
        logger=__name__,
    )
    def send_log_events_to_cloud_watch(self, log_events):
        """
        Bundles the provided log events into a JSON payload and submits it
        to the API Gateway endpoint configured for CloudWatch Logs.

        Parameters
        ----------
        log_events : list
            List of log events converted to dictionaries suitable for submission
            to CloudWatch Logs.

        Raises
        ------
        ValueError
            If no Bearer Token was set on this handler to use with authentication
            to the API Gateway endpoint.

        RuntimeError
            If the submission to API Gateway fails for any reason.

        """
        console_logger = get_logger(__name__, cloudwatch=False, file=False)

        if self.bearer_token is None or self.node_id is None:
            console_logger.debug(
                "Bearer token and/or Node ID was never set on CloudWatchHandler, "
                "unable to communicate with API Gateway endpoint for CloudWatch Logs."
            )
            return

        # Extract the API Gateway configuration params
        api_gateway_template = self.api_gateway_config["url_template"]
        api_gateway_id = self.api_gateway_config["id"]
        api_gateway_region = self.api_gateway_config["region"]
        api_gateway_stage = self.api_gateway_config["stage"]

        log_stream_name = f"pds-ingress-client-{self.node_id}-{self.creation_time}"
        payload = {"logGroupName": self.log_group_name, "logStreamName": log_stream_name}

        # Create the log stream for the current run, if it hasn't been already.
        if not self._stream_created:
            api_gateway_resource = "createstream"

            api_gateway_url = api_gateway_template.format(
                id=api_gateway_id, region=api_gateway_region, stage=api_gateway_stage, resource=api_gateway_resource
            )

            headers = {
                "Authorization": self.bearer_token,
                "UserGroup": NodeUtil.node_id_to_group_name(self.node_id),
                "content-type": "application/json",
                "x-amz-docs-region": api_gateway_region,
            }

            response = requests.post(api_gateway_url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()

            # Can now skip this step for subsequent calls to flush()
            self._stream_created = True

        # Now submit logged content to the newly created log stream
        api_gateway_resource = "log"
        api_gateway_url = api_gateway_template.format(
            id=api_gateway_id, region=api_gateway_region, stage=api_gateway_stage, resource=api_gateway_resource
        )

        # Add the log events to the existing payload containing the log group/stream names
        payload["logEvents"] = log_events
        headers = {
            "Authorization": self.bearer_token,
            "UserGroup": NodeUtil.node_id_to_group_name(self.node_id),
            "content-type": "application/json",
            "x-amz-docs-region": api_gateway_region,
        }

        response = requests.post(api_gateway_url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()

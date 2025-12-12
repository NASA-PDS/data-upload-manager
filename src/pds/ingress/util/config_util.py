"""
==============
config_util.py
==============

Module containing functions for parsing config files used by the
Ingress client and service.

"""
import configparser
import os
from fnmatch import fnmatchcase
from importlib.resources import files
from os.path import join
from urllib.parse import urlparse

import boto3
import yamale
import yaml

CONFIG = None


def strtobool(val: str) -> bool:
    """
    Convert a string representation of truth to a boolean.

    True values are 'y', 'yes', 't', 'true', 'on', and '1';
    false values are 'n', 'no', 'f', 'false', 'off', and '0'.

    Note this behavior differs slightly from distutils.strtobool,
    which returns 1 for true and 0 for false.

    Parameters
    ----------
    val : str
        The truth value to convert to boolean, case-insensitive.

    Returns
    -------
    bool
        Boolean representation of the input string.

    Raises
    ------
    ValueError
        If 'val' is anything else.
    """
    val = val.lower()

    if val in {"y", "yes", "t", "true", "on", "1"}:
        return True
    elif val in {"n", "no", "f", "false", "off", "0"}:
        return False
    else:
        raise ValueError(f"Invalid truth value: {val}")


class SanitizingConfigParser(configparser.RawConfigParser):
    """
    Customized implementation of a ConfigParser object which sanitizes undesireable
    characters (such as double-quotes) from strings read from the INI config
    before they are returned to the caller.

    """

    def get(self, section, option, *, raw=False, vars=None, fallback=None):
        """Invokes the superclass implementation of get, sanitizing the result before it is returned"""
        val = super().get(section, option, raw=raw, vars=vars, fallback=fallback)

        # Remove any single or double-quotes surrounding the value, as these could complicate
        # JSON-serillaziation of certain config values, such as log group name
        if val:
            val = val.strip('"')
            val = val.strip("'")

        return val


class ConfigUtil:
    """
    Class used to read and parse the INI config file used with the Ingress
    Client.
    """

    @staticmethod
    def default_config_path():
        """Returns path to the default configuration file."""
        resource = files("pds.ingress").joinpath("conf.default.ini")
        return str(resource)

    @staticmethod
    def get_config(config_path=None):
        """
        Returns a ConfigParser instance containing the parsed contents of the
        requested config path.

        Notes
        -----
        After the initial call to this method, the parsed config object is
        cached as the singleton to be returned by all subsequent calls to
        get_config(). This ensures that the initialized config can be obtained
        by any subsequent callers without needing to know the path to the
        originating INI file.

        Parameters
        ----------
        config_path : str, optional
            Path to the INI config to parse. If not provided, the default
            config path is used.

        Returns
        -------
        parser : ConfigParser
            The parser instance containing the contents of the read config.

        """
        global CONFIG

        if CONFIG is not None:
            return CONFIG

        if not config_path:
            config_path = ConfigUtil.default_config_path()

        config_path = os.path.abspath(config_path)

        if not os.path.exists(config_path):
            raise ValueError(f"Requested config {config_path} does not exist")

        parser = SanitizingConfigParser()

        with open(config_path, "r") as infile:
            parser.read_file(infile, source=os.path.basename(config_path))

        CONFIG = parser

        return CONFIG

    @staticmethod
    def is_localstack_context():
        """
        Examines the DUM client config to determine if the target endpoint is
        a localstack instance or not.

        Returns
        -------
        True if the config indicates that the DUM client will communicate with localstack,
        False otherwise.

        """
        config = ConfigUtil.get_config()

        # If either region is set to localhost for the API Gateway and Cognito
        # configurations, then assume we're targeting localstack
        return any(
            region == "localhost"
            for region in [config["API_GATEWAY"]["region"].lower(), config["COGNITO"]["region"].lower()]
        )

    @staticmethod
    def get_expected_bucket_owner():
        """
        Returns the Expected Bucket Owner ID from the environment variable
        or the configuration file.
        """
        expected_bucket_owner = os.getenv("EXPECTED_BUCKET_OWNER")

        if not expected_bucket_owner:
            try:
                config = ConfigUtil.get_config()
                if config.has_option("AWS", "expected_bucket_owner"):
                    expected_bucket_owner = config["AWS"]["expected_bucket_owner"]
            except Exception:
                # Config might not be available or readable, which is fine in some contexts
                pass

        return expected_bucket_owner


def validate_bucket_map(bucket_map_path, logger):
    """
    Validates the bucket map at the provided path against the Yamale schema defined
    by the environment.

    Parameters
    ----------
    bucket_map_path : str
        Path to the bucket map file to validate.
    logger : logging.logger
        Object to log results of bucket map validation to.

    """
    lambda_root = os.environ["LAMBDA_TASK_ROOT"]
    bucket_schema_location = os.getenv("BUCKET_MAP_SCHEMA_LOCATION", "config")
    bucket_schema_file = os.getenv("BUCKET_MAP_SCHEMA_FILE", "bucket-map.schema")

    bucket_map_schema_path = join(lambda_root, bucket_schema_location, bucket_schema_file)

    bucket_map_schema = yamale.make_schema(bucket_map_schema_path)
    bucket_map_data = yamale.make_data(bucket_map_path)

    logger.info(f"Validating bucket map {bucket_map_path} with Yamale schema {bucket_map_schema_path}...")
    yamale.validate(bucket_map_schema, bucket_map_data)
    logger.info("Bucket map is valid.")


def initialize_bucket_map(logger):
    """
    Parses the YAML bucket map file for use with the current service invocation.
    The bucket map location is derived from the OS environment.

    Parameters
    ----------
    logger : logging.logger
        Object to log results of bucket map initialization to.

    Returns
    -------
    bucket_map : dict
        Contents of the parsed bucket map YAML config file.

    Raises
    ------
    RuntimeError
        If the bucket map cannot be found at the configured location.

    """
    lambda_root = os.environ["LAMBDA_TASK_ROOT"]
    bucket_map_location = os.getenv("BUCKET_MAP_LOCATION", "config")
    bucket_map_file = os.getenv("BUCKET_MAP_FILE", "bucket-map.yaml")

    bucket_map_path = join(bucket_map_location, bucket_map_file)

    if bucket_map_path.startswith("s3://"):
        logger.info("Downloading bucket map from %s", bucket_map_path)

        parsed_s3_uri = urlparse(bucket_map_path)
        bucket = parsed_s3_uri.netloc
        key = parsed_s3_uri.path[1:]
        bucket_map_dest = os.path.join(lambda_root, os.path.basename(key))

        try:
            s3_client = boto3.client("s3")
            # Get expected bucket owner from environment variable for security
            expected_bucket_owner = ConfigUtil.get_expected_bucket_owner()

            # Verify bucket ownership first using head_object
            if expected_bucket_owner:
                s3_client.head_object(Bucket=bucket, Key=key, ExpectedBucketOwner=expected_bucket_owner)
            s3_client.download_file(bucket, key, bucket_map_dest)
        except Exception as err:
            raise RuntimeError(f"Failed to download bucket map from {bucket_map_path}, reason: {str(err)}")

        bucket_map_path = bucket_map_dest
    else:
        logger.info("Searching Lambda root for bucket map")

        bucket_map_path = join(lambda_root, bucket_map_path)

    if not os.path.exists(bucket_map_path):
        raise RuntimeError(f"No bucket map found at location {bucket_map_path}")

    validate_bucket_map(bucket_map_path, logger)

    with open(bucket_map_path, "r") as infile:
        bucket_map = yaml.safe_load(infile)

    bucket_map = bucket_map["BUCKET_MAP"]

    logger.info("Bucket map %s loaded", bucket_map_path)
    logger.debug(str(bucket_map))

    return bucket_map


def bucket_for_path(node_bucket_map, file_path, logger, bucket_type="staging"):
    """
    Derives the appropriate bucket location and settings for the specified
    file path using the provided node-specific portion of the bucket map.

    Parameters
    ----------
    node_bucket_map : dict
        Bucket mapping specific to the node requesting file ingress.
    file_path : str
        The file path to match to a bucket map entry.
    logger : logging.logger
        Object to log results of the path resolution to.
    bucket_type : str, optional
        Either 'staging' or 'archive'. Defaults to 'staging'.

    Returns
    -------
    bucket : dict
        Dictionary containing details on the S3 bucket that will act as destination
        for the incoming file. This includes the bucket name, as well as any
        other configuration options that can be specified in the bucket map.

    """

    def _match_path_to_prefix(file_path, prefix):
        """Determine if a file path matches a bucket map prefix via equality, substring, or Unix-style pattern matching"""
        return file_path == prefix or file_path.startswith(prefix) or fnmatchcase(file_path, prefix)

    # Pick bucket type (staging or archive)
    buckets = node_bucket_map.get("buckets", {})
    if bucket_type in buckets:
        bucket = buckets[bucket_type]
    else:
        bucket = node_bucket_map.get("default", {}).get("bucket")

    # If any path overrides are defined, apply them
    for path in node_bucket_map.get("paths", []):
        if _match_path_to_prefix(file_path, path["prefix"]):
            bucket = path["bucket"]
            logger.debug("Resolved %s bucket location %s for path %s", bucket_type, bucket, file_path)
            break
    else:
        logger.debug('No %s bucket location configured for path "%s", using default bucket %s',
                     bucket_type, file_path, bucket)

    # Always wrap result in dict form
    if isinstance(bucket, str):
        bucket = {"name": bucket}

    return bucket

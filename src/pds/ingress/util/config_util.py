"""
==============
config_util.py
==============

Module containing functions for parsing config files used by the
Ingress client and service.

"""
import configparser
import os
from os.path import join

import yamale
import yaml
from pkg_resources import resource_filename

CONFIG = None


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
        return resource_filename(__name__, "conf.default.ini")

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
    Parses the YAML bucket map file for use with the Lambda service invocation.
    The bucket map location is derived from the OS environment. Currently,
    only the bucket map bundled with this Lambda function is supported.

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
    bucket_map_location = os.getenv("BUCKET_MAP_LOCATION", "config")
    bucket_map_file = os.getenv("BUCKET_MAP_FILE", "bucket-map.yaml")

    bucket_map_path = join(bucket_map_location, bucket_map_file)

    # TODO: add support for bucket map locations that are s3 or http URI's
    if bucket_map_path.startswith("s3://"):
        bucket_map = {}
    elif bucket_map_path.startswith(("http://", "https://")):
        bucket_map = {}
    else:
        logger.info("Searching Lambda root for bucket map")

        lambda_root = os.environ["LAMBDA_TASK_ROOT"]

        bucket_map_path = join(lambda_root, bucket_map_path)

        if not os.path.exists(bucket_map_path):
            raise RuntimeError(f"No bucket map found at location {bucket_map_path}")

        validate_bucket_map(bucket_map_path, logger)

        with open(bucket_map_path, "r") as infile:
            bucket_map = yaml.safe_load(infile)

    logger.info("Bucket map %s loaded", bucket_map_path)
    logger.debug(str(bucket_map))

    return bucket_map

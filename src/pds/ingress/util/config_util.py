"""
==============
config_util.py
==============

Module containing functions for parsing the INI config file used by the
Ingress client script.

"""
import configparser
import os

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

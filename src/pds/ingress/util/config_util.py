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

        parser = configparser.RawConfigParser()

        with open(config_path, "r") as infile:
            parser.read_file(infile, source=os.path.basename(config_path))

        CONFIG = parser

        return CONFIG

"""
============
path_util.py
============

Module containing functions for working with local file system paths.

"""
import os

from .log_util import get_logger


class PathUtil:
    """Provides methods for working with local file system paths."""

    @staticmethod
    def resolve_ingress_paths(user_paths, resolved_paths=None):
        """
        Iterates over the list of user-provided paths to derive the final
        set of file paths to request ingress for.

        Parameters
        ----------
        user_paths : list of str
            The collection of user-requested paths to include with the ingress
            request. Can be any combination of file and directory paths.
        resolved_paths : list of str, optional
            The list of paths resolved so far. For top-level callers, this should
            be left as None.

        Returns
        -------
        resolved_paths : list of str
            The list of all paths resolved from walking the set of user-provided
            paths.

        """
        logger = get_logger(__name__)

        # Initialize the list of resolved paths if necessary
        resolved_paths = resolved_paths or list()

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)

            if not os.path.exists(abs_user_path):
                logger.warning(f"Encountered path ({abs_user_path}) that does not actually exist, skipping...")
                continue

            if os.path.isfile(abs_user_path):
                logger.debug(f"Resolved path {abs_user_path}")

                resolved_paths.append(abs_user_path)
            elif os.path.isdir(abs_user_path):
                logger.debug(f"Resolving directory {abs_user_path}")
                for grouping in os.walk(abs_user_path, topdown=True, followlinks=True):
                    dirpath, _, filenames = grouping

                    # TODO: add option to include hidden files
                    # TODO: add support for include/exclude path filters
                    product_paths = [
                        os.path.join(dirpath, filename)
                        for filename in filter(lambda name: not name.startswith("."), filenames)
                    ]

                    resolved_paths = PathUtil.resolve_ingress_paths(product_paths, resolved_paths)
            else:
                logger.warning(f"Encountered path ({abs_user_path}) that is neither a file nor directory, skipping...")

        return resolved_paths

    @staticmethod
    def trim_ingress_path(ingress_path, prefix=None):
        """
        Trims an optional prefix value from the provided ingress path to prepare
        it for use with the Ingress Service Lambda function.

        Parameters
        ----------
        ingress_path : str
            The ingress path to trim
        prefix : str, optional
            A string prefix to trim from the ingress path, if the path starts
            with it.

        Returns
        -------
        trimmed_ingress_path : str
            The version of the ingress path with the provided prefix trimmed
            from it. If the path does not start with the prefix or no prefix
            is provided, the untrimmed path is returned.

        """
        logger = get_logger(__name__)

        trimmed_ingress_path = ingress_path

        # Remove path prefix if one was configured
        if prefix and ingress_path.startswith(prefix):
            trimmed_ingress_path = ingress_path.replace(prefix, "")

            # Trim any leading slash if one was left after removing prefix
            if trimmed_ingress_path.startswith("/"):
                trimmed_ingress_path = trimmed_ingress_path[1:]

            logger.debug(f"Removed prefix {prefix}, new path: {trimmed_ingress_path}")

        return trimmed_ingress_path

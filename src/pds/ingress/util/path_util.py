"""
============
path_util.py
============

Module containing functions for working with local file system paths.

"""
import logging
import os

logger = logging.getLogger(__name__)


class PathUtil:
    """Provides methods for working with local file system paths."""

    @staticmethod
    def resolve_ingress_paths(user_paths, resolved_paths=None, prefix=None):
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
        prefix : str
            Path prefix to trim from each resolved path, if present.

        Returns
        -------
        resolved_paths : list of str
            The list of all paths resolved from walking the set of user-provided
            paths.

        """
        # Initialize the list of resolved paths if necessary
        resolved_paths = resolved_paths or list()

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)

            if not os.path.exists(abs_user_path):
                logger.warning(f"Encountered path ({abs_user_path}) that does not actually exist, skipping...")
                continue

            if os.path.isfile(abs_user_path):
                logger.debug(f"Resolved path {abs_user_path}")

                # Remove path prefix if one was configured
                if prefix and abs_user_path.startswith(prefix):
                    abs_user_path = abs_user_path.replace(prefix, "")

                    # Trim any leading slash if one was left after removing prefix
                    if abs_user_path.startswith("/"):
                        abs_user_path = abs_user_path[1:]

                    logger.debug(f"Removed prefix {prefix}, new path: {abs_user_path}")

                resolved_paths.append(abs_user_path)
            elif os.path.isdir(abs_user_path):
                logger.debug(f"Resolving directory {abs_user_path}")
                for grouping in os.walk(abs_user_path, topdown=True):
                    dirpath, _, filenames = grouping

                    # TODO: add option to include hidden files
                    # TODO: add support for include/exclude path filters
                    product_paths = [
                        os.path.join(dirpath, filename)
                        for filename in filter(lambda name: not name.startswith("."), filenames)
                    ]

                    resolved_paths = PathUtil.resolve_ingress_paths(product_paths, resolved_paths, prefix=prefix)
            else:
                logger.warning(f"Encountered path ({abs_user_path}) that is neither a file nor directory, skipping...")

        return resolved_paths

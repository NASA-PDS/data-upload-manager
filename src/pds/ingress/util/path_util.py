"""
============
path_util.py
============

Module containing functions for working with local file system paths.

"""
import logging
import os

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from .log_util import get_logger


class PathUtil:
    """Provides methods for working with local file system paths."""

    @staticmethod
    def init_path_progress_bar(user_paths):
        """Initializes and returns tqdm progress bar based on the number of files to be resolved for ingress"""
        total_files = 0

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)
            for _, _, files in os.walk(abs_user_path):
                total_files += len(files)

        pbar = tqdm(total=total_files, position=0, leave=True, desc="Resolving ingress paths")

        return pbar

    @staticmethod
    def resolve_ingress_paths(user_paths, pbar, resolved_paths=None):
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
        # Use a vanilla logger here for use with the tqdm redirection
        logger = logging.getLogger(__name__)

        # Initialize the list of resolved paths if necessary
        resolved_paths = resolved_paths or list()

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)

            if not os.path.exists(abs_user_path):
                pbar.update()
                with logging_redirect_tqdm():
                    logger.warning("Encountered path (%s) that does not actually exist, skipping...", abs_user_path)
                    continue

            if os.path.isfile(abs_user_path):
                resolved_paths.append(abs_user_path)
                pbar.update()
            elif os.path.isdir(abs_user_path):
                for grouping in os.walk(abs_user_path, topdown=True, followlinks=True):
                    dirpath, _, filenames = grouping

                    # TODO: add option to include hidden files
                    # TODO: add support for include/exclude path filters
                    product_paths = [
                        os.path.join(dirpath, filename)
                        for filename in filter(lambda name: not name.startswith("."), filenames)
                    ]

                    resolved_paths = PathUtil.resolve_ingress_paths(product_paths, pbar, resolved_paths)
            else:
                with logging_redirect_tqdm():
                    logger.warning(
                        "Encountered path (%s) that is neither a file nor directory, skipping...", abs_user_path
                    )
                pbar.update()

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

            logger.debug("Removed prefix %s, new path: %s", prefix, trimmed_ingress_path)

        return trimmed_ingress_path

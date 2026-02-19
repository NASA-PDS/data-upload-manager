"""
============
path_util.py
============

Module containing functions for working with local file system paths.

"""
import fnmatch
import os

from .log_util import get_logger


class PathUtil:
    """Provides methods for working with local file system paths."""

    @staticmethod
    def resolve_ingress_paths(user_paths, includes, excludes, pbar, resolved_paths=None, follow_symlinks=True):
        """
        Iterates over the list of user-provided paths to derive the final
        set of file paths to request ingress for.

        Parameters
        ----------
        user_paths : list of str
            The collection of user-requested paths to include with the ingress
            request. Can be any combination of file and directory paths.
        includes : list of str
            List of patterns defining which files to include for ingress.
        excludes : list of str
            List of patterns defining which files to exclude from ingress.
        pbar : tqdm.tqdm
            Progress bar instance used to track path resolution.
        resolved_paths : list of str, optional
            The list of paths resolved so far. For top-level callers, this should
            be left as None.
        follow_symlinks : bool, optional
            Whether to follow symbolic links when walking directories. Defaults
            to True for backward compatibility. Set to False to skip symlinks
            and avoid uploading duplicate data.

        Returns
        -------
        resolved_paths : list of str
            The list of all paths resolved from walking the set of user-provided
            paths.

        """
        # Use a logger with no console output to avoid interfering with tqdm output
        logger = get_logger("resove_ingress_paths", console=False)

        # Initialize the list of resolved paths if necessary
        resolved_paths = resolved_paths or list()

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)

            if not os.path.exists(abs_user_path):
                pbar.update()
                logger.warning("Encountered path (%s) that does not actually exist, skipping...", abs_user_path)
                continue

            if os.path.isfile(abs_user_path):
                pbar.update()

                # Skip symlinked files if follow_symlinks is False
                if not follow_symlinks and os.path.islink(abs_user_path):
                    logger.debug("Skipping symlinked file %s", abs_user_path)
                    continue

                if PathUtil.filter_file(abs_user_path, includes, excludes):
                    logger.debug("Filtering path %s based on include/exclude filters", abs_user_path)
                    continue

                resolved_paths.append(abs_user_path)
            elif os.path.isdir(abs_user_path):
                for grouping in os.walk(abs_user_path, topdown=True, followlinks=follow_symlinks):
                    dirpath, _, filenames = grouping

                    # TODO: add option to include hidden files
                    # TODO: add support for include/exclude path filters
                    product_paths = [
                        os.path.join(dirpath, filename)
                        for filename in filter(lambda name: not name.startswith("."), filenames)
                    ]

                    resolved_paths = PathUtil.resolve_ingress_paths(
                        product_paths, includes, excludes, pbar, resolved_paths, follow_symlinks=follow_symlinks
                    )
            else:
                logger.warning("Encountered path (%s) that is neither a file nor directory, skipping...", abs_user_path)
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
        prefix : dict, optional
            A prefix dictionary mapping the prefix to trim from the ingress path
            with the value to replace it.

        Returns
        -------
        trimmed_ingress_path : str
            The version of the ingress path with the provided prefix trimmed
            from it. If the path does not start with the prefix or no prefix
            is provided, the untrimmed path is returned.

        """
        # Only log any debug trace messages here to file
        logger = get_logger("trim_ingress_path", console=False, cloudwatch=False)

        trimmed_ingress_path = ingress_path

        # Remove path prefix if one was configured
        if prefix and prefix.get("old") and ingress_path.startswith(prefix["old"]):
            trimmed_ingress_path = ingress_path.replace(prefix["old"], prefix.get("new", ""), 1)

            # Trim any leading slash if one was left after trimming prefix
            if trimmed_ingress_path.startswith("/"):
                trimmed_ingress_path = trimmed_ingress_path[1:]

            logger.debug("Trimmed prefix %s, new path: %s", prefix, trimmed_ingress_path)

        return trimmed_ingress_path

    @staticmethod
    def filter_file(file_path, includes, excludes):
        """
        Determines if the provided file path should be filtered out based on
        the provided include and exclude patterns. Include patterns are always
        applied prior to exclude patterns.

        Parameters
        ----------
        file_path : str
            The file path to filter.
        includes : list of str
            List of include patterns to apply.
        excludes : list of str
            List of exclude patterns to apply.

        Returns
        -------
        bool
            True if the file path should be filtered out based on the
            configuration of the provided include and exclude patterns,
            False otherwise.

        """
        result = False

        if includes and not any(fnmatch.fnmatch(file_path, pattern) for pattern in includes):
            result = True

        if excludes and any(fnmatch.fnmatch(file_path, pattern) for pattern in excludes):
            result = True

        return result

    @staticmethod
    def validate_gzip_extension(file_path):
        """
        Validates that a file has a .gz extension.

        Parameters
        ----------
        file_path : str
            The file path to validate.

        Returns
        -------
        bool
            True if the file has a .gz extension, False otherwise.

        """
        return file_path.lower().endswith(".gz")

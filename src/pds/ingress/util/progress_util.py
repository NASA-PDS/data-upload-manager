"""
================
progress_util.py
================

Module containing functions for working with tqdm progress bars to track various
states of an upload request.

"""
import multiprocessing
import os

from tqdm import tqdm
from tqdm.asyncio import tqdm_asyncio

PATH_BAR = None
MANIFEST_BAR = None
TOTAL_INGRESS_BAR = None
BATCH_BARS = []

BATCH_SEMAPHORE = multiprocessing.Semaphore(1)
"""Semaphore used to control write access to Batch progress bars"""

LIGHT_GREEN = "#05E520"
"""Hex code for a light green color"""


def get_path_progress_bar(user_paths):
    """
    Initializes (if necessary) and returns the Path Resolution progress bar using
    the number of files to be resolved for ingress.

    Parameters
    ----------
    user_paths : list of str
        The list of paths to resolve provided by the user on the command-line.

    Returns
    -------
    PATH_BAR : tqdm.tqdm
        The initialized global instance of the Path Resolution progress bar.

    """
    global PATH_BAR

    if PATH_BAR is None:
        total_files = 0

        for user_path in user_paths:
            abs_user_path = os.path.abspath(user_path)
            for _, _, files in os.walk(abs_user_path):
                # Ignore hidden files
                total_files += len([file for file in files if not file.startswith(".")])

        PATH_BAR = tqdm(
            total=total_files,
            position=0,
            leave=True,
            desc="Resolving ingress paths",
            colour=LIGHT_GREEN,
            bar_format="{l_bar}{bar:60}| {n_fmt}/{total_fmt} Files",
        )

    return PATH_BAR


def get_manifest_progress_bar(total):
    """
    Initializes (if necessary) and returns the Manifest File progress bar using
    the total number of batched requests.

    Parameters
    ----------
    total : int
        The total number of batches used to set the limit of the returned progress bar.

    Returns
    -------
    MANIFEST_BAR : tqdm.tqdm_asyncio
        The initialized global instance of the Manifest File progress bar.

    """
    global MANIFEST_BAR

    if MANIFEST_BAR is None:
        MANIFEST_BAR = tqdm_asyncio(
            total=total,
            position=0,
            leave=True,
            desc="Generating checksum manifest",
            colour=LIGHT_GREEN,
            bar_format="{l_bar}{bar:60}| {n_fmt}/{total_fmt} Batches ({remaining} est. remaining)",
        )

    return MANIFEST_BAR


def get_ingress_total_progress_bar(total):
    """
    Initializes (if necessary) and returns the Total Ingress progress bar using
    the total number of batched requests.

    Parameters
    ----------
    total : int
        The total number of batches used to set the limit of the returned progress bar.

    Returns
    -------
    TOTAL_INGRESS_BAR : tqdm.tqdm_asyncio
        The initialized global instance of the Total Ingress progress bar.

    """
    global TOTAL_INGRESS_BAR

    if TOTAL_INGRESS_BAR is None:
        TOTAL_INGRESS_BAR = tqdm_asyncio(
            total=total,
            position=0,
            leave=True,
            desc="Uploading Batches",
            colour=LIGHT_GREEN,
            bar_format="{l_bar}{bar:60}| {n_fmt}/{total_fmt} Batches ({remaining} est. remaining)",
        )

    return TOTAL_INGRESS_BAR


def init_batch_progress_bars(num_threads):
    """
    Initializes (if necessary) the set of Batch progress bars, which includes a
    sub-bar to track an indvidual file's upload progress for a given batch.

    Notes
    -----
    This function will only create the Batch progress bars if they have not been
    already. To obtain a handle to a single Batch progress bar for use, see the
    `get_available_batch_progress_bar()` function within this module. To get a
    handle to an Upload progress sub-bar, see the `get_upload_progress_bar_for_batch()`
    function within this module.

    Parameters
    ----------
    num_threads : int
        The number of threads to be utilized during Batch upload. Determines
        the number of Batch/Upload bars to initialize.

    """
    if len(BATCH_BARS) == 0:
        for i in range(num_threads):
            batch_pbar_position = ((i % num_threads) * 2) + 1
            batch_pbar = tqdm_asyncio(
                position=batch_pbar_position,
                leave=True,
                colour="green",
                bar_format="  |_ {l_bar}{bar:40}| {n_fmt}/{total_fmt} Files Uploaded",
            )
            batch_pbar.in_use = False

            upload_pbar_position = ((i % num_threads) + 1) * 2
            upload_pbar = tqdm_asyncio(
                position=upload_pbar_position,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=True,
                colour="blue",
                bar_format="{l_bar}{bar:80}{r_bar}",
            )
            batch_pbar.upload_pbar = upload_pbar  # link upload status sub-bar to its "parent" upload bar

            BATCH_BARS.append(batch_pbar)


def get_available_batch_progress_bar(total, desc=None):
    """
    Returns a handle to an available Batch progress bar. For a Batch progress bar
    to be available, it must not be currently in use for another batch.

    Parameters
    ----------
    total : int
        The size to allocate to the returned progress bar. This should typically
        correspond to the true number of files within the batch (which can be
        smaller than the configured batch size for the final batch in a sequence).
    desc : str, optional
        The description text to assign to the returned progress bar.

    Returns
    -------
    batch_pbar : tqdm.tqdm_asyncio
        The next Batch progress bar that is freely available for use by the caller.

    """
    batch_pbar = None

    with BATCH_SEMAPHORE:
        while batch_pbar is None:
            try:
                batch_pbar = next(pbar for pbar in BATCH_BARS if not pbar.in_use)
            except StopIteration:
                # Keep looking until a bar is freed up
                continue

        batch_pbar.in_use = True
        batch_pbar.total = total
        batch_pbar.reset()

        if desc:
            batch_pbar.desc = desc

        batch_pbar.refresh()

    return batch_pbar


def release_batch_progress_bar(batch_pbar):
    """
    Mark the provided Batch progress bar as released, allowing it to be reused
    to track progress on a new Batch.

    Parameters
    ----------
    batch_pbar : tqdm.tqdm_asyncio
        The Batch progress bar to release.

    """
    batch_pbar.in_use = False


def get_upload_progress_bar_for_batch(batch_pbar, total, filename=None):
    """
    Reinitalizes and returns a handle to the Upload progress sub-bar associated
    with a given Batch progress bar.

    Parameters
    ----------
    batch_pbar : tqdm.tqdm_asyncio
        The Batch progress bar to obtain the Upload sub-bar for.
    total : int
        The new total value to assign to the returned Upload sub-bar.
    filename : str, optional
        The name of the file to use as the new description for the returned
        sub-bar.

    Returns
    -------
    upload_pbar : tqdm.tqdm_asyncio
        Handle to the reinitalized Upload progress sub-bar.

    """
    upload_pbar = batch_pbar.upload_pbar
    upload_pbar.reset()
    upload_pbar.total = total

    if filename:
        update_upload_pbar_filename(upload_pbar, filename)

    upload_pbar.refresh()

    return upload_pbar


def update_upload_pbar_filename(upload_pbar, filename):
    """
    Updates the filename of the provided Batch progress bar.

    Parameters
    ----------
    upload_pbar : tqdm.tqdm_asyncio
        The file upload progress bar to update.
    filename : str
        The new filename text to assign to the Batch progress bar.

    """
    upload_pbar.desc = f"    |_ {filename}"
    upload_pbar.refresh()


def close_ingress_total_progress_bar():
    """Closes the Total Ingress progress bar."""
    global TOTAL_INGRESS_BAR  # noqa F824

    if TOTAL_INGRESS_BAR:
        TOTAL_INGRESS_BAR.close()
        TOTAL_INGRESS_BAR = None


def close_batch_progress_bars():
    """Closes all Batch progress bars and associated Upload sub-bars."""
    global BATCH_BARS, TOTAL_INGRESS_BAR  # noqa F824

    if not BATCH_BARS:
        return

    with BATCH_SEMAPHORE:
        for batch_pbar in BATCH_BARS:
            batch_pbar.upload_pbar.close()
            batch_pbar.close()

        BATCH_BARS.clear()
        TOTAL_INGRESS_BAR = None

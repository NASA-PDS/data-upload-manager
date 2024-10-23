"""
============
hash_util.py
============

Module containing functions related to hashing and checksum generation.

"""
import hashlib


def md5_for_path(ingress_path, block_size=4096):
    """
    Returns a hashlib.md5 object initialized with the contents of the provided
    file path.

    Parameters
    ----------
    ingress_path : str
        Path of a file to be ingressed.
    block_size : int, optional
        Block size of bytes to pull from file on each read.

    Returns
    -------
    hashlib.md5
        The md5 object initialized with the contents of the provided file.

    """
    # Calculate the MD5 checksum of the file payload
    md5 = hashlib.md5()
    with open(ingress_path, "rb") as object_file:
        while chunk := object_file.read(block_size):
            md5.update(chunk)

    return md5

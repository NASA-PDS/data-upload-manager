import shutil
from importlib.resources import files
import filecmp

import pytest


@pytest.fixture(autouse=True, scope="session")
def version_txt_in_test_config():
    """Copy the canonical VERSION.txt into the test config directory.

    Replaces what was previously a symlink, which confused roundup-action's
    TextFileDetective when scanning for VERSION.txt files to commit.
    See: https://github.com/NASA-PDS/roundup-action/issues/166
    """
    src = str(files("pds.ingress").joinpath("VERSION.txt"))
    dst = str(files("tests.pds.ingress").joinpath("service/config/VERSION.txt"))
    try:
        # Only copy when the destination is missing or has different content,
        # to avoid unnecessarily updating the file's mtime in the working tree.
        if not filecmp.cmp(src, dst, shallow=False):
            shutil.copy(src, dst)
    except FileNotFoundError:
        shutil.copy(src, dst)

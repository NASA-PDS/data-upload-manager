import shutil
from importlib.resources import files

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
    shutil.copy(src, dst)

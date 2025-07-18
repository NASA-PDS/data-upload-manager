#!/usr/bin/env python3
import os
import tempfile
import unittest
from importlib.resources import files
from os.path import abspath
from os.path import join

from pds.ingress.util.path_util import PathUtil
from pds.ingress.util.progress_util import get_path_progress_bar


class PathUtilTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Set up directories and files for testing"""
        cls.starting_dir = abspath(os.curdir)
        cls.test_dir = str(files("tests.pds.ingress").joinpath("util"))

        os.chdir(cls.test_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        """At completion re-establish starting directory"""
        os.chdir(cls.starting_dir)

    def setUp(self) -> None:
        """Create a temporary directory that each test can populate as necessary"""
        self.working_dir = tempfile.TemporaryDirectory(prefix="test_path_util_", suffix="_temp", dir=os.curdir)

    def tearDown(self) -> None:
        """Return to starting directory and delete temp dir"""
        os.chdir(self.test_dir)
        self.working_dir.cleanup()

    def test_resolve_ingress_paths(self):
        """Test the resolve_ingress_paths() function"""
        # Create some dummy files and directories to test with
        os.system(f"touch {join(self.working_dir.name, 'top_level_file.txt')}")
        os.system(f"mkdir {join(self.working_dir.name, 'dir_one')}")
        os.system(f"touch {join(self.working_dir.name, 'dir_one', 'mid_level_file.txt')}")
        os.system(f"mkdir {join(self.working_dir.name, 'dir_one', 'dir_two')}")
        os.system(f"touch {join(self.working_dir.name, 'dir_one', 'dir_two', 'low_level_file.txt')}")

        # Test with fully resolved paths
        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], pbar)

        self.assertIsInstance(resolved_ingress_paths, list)
        self.assertGreater(len(resolved_ingress_paths), 0)
        self.assertEqual(len(resolved_ingress_paths), 3)

        self.assertIn(abspath(join(self.working_dir.name, "top_level_file.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "dir_one", "mid_level_file.txt")), resolved_ingress_paths)
        self.assertIn(
            abspath(join(self.working_dir.name, "dir_one", "dir_two", "low_level_file.txt")), resolved_ingress_paths
        )

        # Test with a non-existent path
        with get_path_progress_bar(["/fake/path"]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths(["/fake/path"], pbar)

        self.assertIsInstance(resolved_ingress_paths, list)
        self.assertEqual(len(resolved_ingress_paths), 0)

    def test_trim_ingress_path(self):
        """Test the trim_ingress_path() function"""
        ingress_paths = [
            join(abspath(self.working_dir.name), "top_level_file.txt"),
            join(abspath(self.working_dir.name), "dir_one", "mid_level_file.txt"),
            join(abspath(self.working_dir.name), "dir_one", "dir_two", "low_level_file.txt"),
        ]

        trimmed_paths = [
            PathUtil.trim_ingress_path(ingress_path, prefix=abspath(self.working_dir.name))
            for ingress_path in ingress_paths
        ]

        self.assertIn("top_level_file.txt", trimmed_paths)
        self.assertIn(join("dir_one", "mid_level_file.txt"), trimmed_paths)
        self.assertIn(join("dir_one", "dir_two", "low_level_file.txt"), trimmed_paths)

        untrimmed_paths = [PathUtil.trim_ingress_path(ingress_path) for ingress_path in ingress_paths]

        self.assertListEqual(ingress_paths, untrimmed_paths)


if __name__ == "__main__":
    unittest.main()

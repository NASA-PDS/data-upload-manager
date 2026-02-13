#!/usr/bin/env python3
import os
import tempfile
import unittest
from importlib.resources import files
from os.path import abspath
from os.path import join
from pathlib import Path

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
        Path(join(self.working_dir.name, 'top_level_file.txt')).touch()
        Path(join(self.working_dir.name, 'dir_one')).mkdir(parents=True)
        Path(join(self.working_dir.name, 'dir_one', 'mid_level_file.txt')).touch()
        Path(join(self.working_dir.name, 'dir_one', 'dir_two')).mkdir(parents=True)
        Path(join(self.working_dir.name, 'dir_one', 'dir_two', 'low_level_file.txt')).touch()

        # Test with fully resolved paths
        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], [], [], pbar)

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
            resolved_ingress_paths = PathUtil.resolve_ingress_paths(["/fake/path"], [], [], pbar)

        self.assertIsInstance(resolved_ingress_paths, list)
        self.assertEqual(len(resolved_ingress_paths), 0)

    def test_ingress_path_filtering(self):
        """Test the resolve_ingress_paths() function with include and exclude filters"""
        # Create some dummy files to test with
        Path(join(self.working_dir.name, 'file.txt')).touch()
        Path(join(self.working_dir.name, 'file.xml')).touch()
        Path(join(self.working_dir.name, 'file.dat')).touch()
        Path(join(self.working_dir.name, 'data.txt')).touch()
        Path(join(self.working_dir.name, 'data.xml')).touch()
        Path(join(self.working_dir.name, 'data.dat')).touch()

        # Test with no filters
        includes = []
        excludes = []

        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], includes, excludes, pbar)

        self.assertEqual(len(resolved_ingress_paths), 6)
        self.assertIn(abspath(join(self.working_dir.name, "file.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "file.xml")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "file.dat")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.xml")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.dat")), resolved_ingress_paths)

        # Test with include filters
        includes = ["*file.*"]
        excludes = []

        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], includes, excludes, pbar)

        self.assertEqual(len(resolved_ingress_paths), 3)
        self.assertIn(abspath(join(self.working_dir.name, "file.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "file.xml")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "file.dat")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "data.txt")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "data.xml")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "data.dat")), resolved_ingress_paths)

        # Test with exclude filters
        includes = []
        excludes = ["*file.*"]

        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], includes, excludes, pbar)

        self.assertEqual(len(resolved_ingress_paths), 3)
        self.assertNotIn(abspath(join(self.working_dir.name, "file.txt")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "file.xml")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "file.dat")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.xml")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "data.dat")), resolved_ingress_paths)

        # Test with both include and exclude filters
        includes = ["*file.*"]
        excludes = ["*"]

        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], includes, excludes, pbar)

        self.assertEqual(len(resolved_ingress_paths), 0)

        includes = ["*.txt", "*.xml"]
        excludes = ["*data.*"]

        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_ingress_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], includes, excludes, pbar)

        self.assertEqual(len(resolved_ingress_paths), 2)
        self.assertIn(abspath(join(self.working_dir.name, "file.txt")), resolved_ingress_paths)
        self.assertIn(abspath(join(self.working_dir.name, "file.xml")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "data.txt")), resolved_ingress_paths)
        self.assertNotIn(abspath(join(self.working_dir.name, "data.xml")), resolved_ingress_paths)

    def test_trim_ingress_path(self):
        """Test the trim_ingress_path() function"""
        ingress_paths = [
            join(abspath(self.working_dir.name), "top_level_file.txt"),
            join(abspath(self.working_dir.name), "dir_one", "mid_level_file.txt"),
            join(abspath(self.working_dir.name), "dir_one", "dir_two", "low_level_file.txt"),
        ]

        prefix = {"old": abspath(self.working_dir.name), "new": ""}

        trimmed_paths = [PathUtil.trim_ingress_path(ingress_path, prefix=prefix) for ingress_path in ingress_paths]

        self.assertIn("top_level_file.txt", trimmed_paths)
        self.assertIn(join("dir_one", "mid_level_file.txt"), trimmed_paths)
        self.assertIn(join("dir_one", "dir_two", "low_level_file.txt"), trimmed_paths)

        prefix = {"old": abspath(self.working_dir.name), "new": "replacement"}

        trimmed_paths = [PathUtil.trim_ingress_path(ingress_path, prefix=prefix) for ingress_path in ingress_paths]

        self.assertIn("replacement/top_level_file.txt", trimmed_paths)
        self.assertIn(join("replacement", "dir_one", "mid_level_file.txt"), trimmed_paths)
        self.assertIn(join("replacement", "dir_one", "dir_two", "low_level_file.txt"), trimmed_paths)

        ingress_paths = [
            join("dir_one", "dir_two", "dir_one_again", "dir_one_two", "file.txt"),
        ]

        # Make sure we perform at most one replacement at the beginning of the string
        prefix = {"old": "dir_one", "new": "replacement"}

        trimmed_paths = [PathUtil.trim_ingress_path(ingress_path, prefix=prefix) for ingress_path in ingress_paths]

        self.assertIn("replacement/dir_two/dir_one_again/dir_one_two/file.txt", trimmed_paths)

        # Make sure we do not perform replacement when "old" value is falsey
        prefix = {"old": None, "new": "replacement"}

        untrimmed_paths = [PathUtil.trim_ingress_path(ingress_path, prefix=prefix) for ingress_path in ingress_paths]

        self.assertListEqual(ingress_paths, untrimmed_paths)

        prefix = {"old": "", "new": "replacement"}

        untrimmed_paths = [PathUtil.trim_ingress_path(ingress_path, prefix=prefix) for ingress_path in ingress_paths]

        self.assertListEqual(ingress_paths, untrimmed_paths)

        # Trim paths with no prefix dictionary provided
        untrimmed_paths = [PathUtil.trim_ingress_path(ingress_path) for ingress_path in ingress_paths]

        self.assertListEqual(ingress_paths, untrimmed_paths)

    def test_validate_gzip_extension(self):
        """Test the validate_gzip_extension() function"""
        # Valid gzip extensions
        self.assertTrue(PathUtil.validate_gzip_extension("/path/to/file.log.gz"))
        self.assertTrue(PathUtil.validate_gzip_extension("/path/to/file.gz"))
        self.assertTrue(PathUtil.validate_gzip_extension("file.gz"))
        self.assertTrue(PathUtil.validate_gzip_extension("/path/to/file.GZ"))
        self.assertTrue(PathUtil.validate_gzip_extension("/path/to/file.Gz"))

        # Invalid extensions
        self.assertFalse(PathUtil.validate_gzip_extension("/path/to/file.log"))
        self.assertFalse(PathUtil.validate_gzip_extension("/path/to/file.txt"))
        self.assertFalse(PathUtil.validate_gzip_extension("/path/to/file.gz.bak"))
        self.assertFalse(PathUtil.validate_gzip_extension("/path/to/file"))
        self.assertFalse(PathUtil.validate_gzip_extension(""))

    def test_resolve_ingress_paths_skip_symlinks(self):
        """Test that resolve_ingress_paths() correctly handles symlinks when follow_symlinks=False"""
        # Create a directory structure with real files
        real_dir = join(self.working_dir.name, "real_data")
        os.makedirs(real_dir)
        Path(join(real_dir, 'real_file.txt')).touch()

        # Create a symlinked directory and file, skipping the test if symlinks are not supported
        symlink_dir = join(self.working_dir.name, "symlink_data")
        symlink_file = join(self.working_dir.name, "symlink_file.txt")
        try:
            os.symlink(real_dir, symlink_dir)
            os.symlink(join(real_dir, "real_file.txt"), symlink_file)
        except OSError:
            self.skipTest("Symbolic links are not supported or permissions do not allow creating them on this platform.")

        # Create a regular file for comparison
        Path(join(self.working_dir.name, 'regular_file.txt')).touch()

        # Test with follow_symlinks=True (default behavior)
        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_paths = PathUtil.resolve_ingress_paths([self.working_dir.name], [], [], pbar, follow_symlinks=True)

        # Should include files from both real and symlinked paths
        self.assertIn(abspath(join(real_dir, "real_file.txt")), resolved_paths)
        self.assertIn(abspath(join(symlink_dir, "real_file.txt")), resolved_paths)
        self.assertIn(abspath(symlink_file), resolved_paths)
        self.assertIn(abspath(join(self.working_dir.name, "regular_file.txt")), resolved_paths)

        # Test with follow_symlinks=False
        with get_path_progress_bar([self.working_dir.name]) as pbar:
            resolved_paths = PathUtil.resolve_ingress_paths(
                [self.working_dir.name], [], [], pbar, follow_symlinks=False
            )

        # Should include only the real file and regular file, not symlinked paths
        self.assertIn(abspath(join(real_dir, "real_file.txt")), resolved_paths)
        self.assertIn(abspath(join(self.working_dir.name, "regular_file.txt")), resolved_paths)
        # Symlinked directory contents should not be included
        self.assertNotIn(abspath(join(symlink_dir, "real_file.txt")), resolved_paths)
        # Symlinked file should not be included
        self.assertNotIn(abspath(symlink_file), resolved_paths)


if __name__ == "__main__":
    unittest.main()

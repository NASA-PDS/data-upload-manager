"""
Regression tests for argument parsing behavior in pds_ingress_client.

Covers the bug where optional flags (e.g. --dry-run) placed after positional
path arguments were silently ignored, causing actual uploads instead of dry runs.
"""
import pytest

from pds.ingress.client.pds_ingress_client import setup_argparser


@pytest.fixture
def parser():
    return setup_argparser()


def _parse(parser, args):
    return parser.parse_intermixed_args(args)


class TestDryRunPlacement:
    """--dry-run must be recognized regardless of where it appears on the command line."""

    BASE = ["-n", "sbn", "/some/path"]

    def test_dry_run_before_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "--dry-run", "/some/path"])
        assert args.dry_run is True
        assert args.ingress_paths == ["/some/path"]

    def test_dry_run_after_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "/some/path", "--dry-run"])
        assert args.dry_run is True
        assert args.ingress_paths == ["/some/path"]

    def test_dry_run_after_multiple_paths(self, parser):
        args = _parse(parser, ["-n", "sbn", "/path/a", "/path/b", "--dry-run"])
        assert args.dry_run is True
        assert args.ingress_paths == ["/path/a", "/path/b"]

    def test_no_dry_run_flag(self, parser):
        args = _parse(parser, self.BASE)
        assert args.dry_run is False

    def test_dry_run_is_not_consumed_as_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "/some/path", "--dry-run"])
        assert "--dry-run" not in args.ingress_paths


class TestOtherFlagsAfterPath:
    """Other boolean flags must also work when placed after positional paths."""

    def test_force_overwrite_after_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "/some/path", "--force-overwrite"])
        assert args.force_overwrite is True
        assert args.ingress_paths == ["/some/path"]

    def test_skip_symlinks_after_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "/some/path", "--skip-symlinks"])
        assert args.skip_symlinks is True
        assert args.ingress_paths == ["/some/path"]

    def test_multiple_flags_after_path(self, parser):
        args = _parse(parser, ["-n", "sbn", "/some/path", "--dry-run", "--skip-symlinks"])
        assert args.dry_run is True
        assert args.skip_symlinks is True
        assert args.ingress_paths == ["/some/path"]

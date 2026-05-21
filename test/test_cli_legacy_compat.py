"""Backward-compat tests for `lib/cli.py` legacy detection.

Regression for Codex review (P2): flag-first invocations like
`python attendance_analyzer.py --full sample.txt csv` previously broke
the subcommand split because the heuristic only checked argv[0]. The
fix scans every token for a subcommand keyword; absent any, the whole
line is rewritten as `analyze ...`.
"""
import unittest

from lib.cli import KNOWN_SUBCOMMANDS, _looks_like_legacy_invocation


class TestLooksLikeLegacy(unittest.TestCase):
    def test_pure_file_path(self):
        self.assertTrue(_looks_like_legacy_invocation(
            ["202508-王小明-出勤資料.txt"]))

    def test_file_then_format(self):
        self.assertTrue(_looks_like_legacy_invocation(
            ["202508-王小明-出勤資料.txt", "csv"]))

    def test_flag_first(self):
        # The bug: --full sample.txt csv used to NOT be treated as legacy
        self.assertTrue(_looks_like_legacy_invocation(
            ["--full", "sample.txt", "csv"]))

    def test_multiple_flags_first(self):
        self.assertTrue(_looks_like_legacy_invocation(
            ["--debug", "--reset-state", "sample.txt", "csv"]))

    def test_subcommand_first(self):
        self.assertFalse(_looks_like_legacy_invocation(
            ["analyze", "sample.txt"]))

    def test_subcommand_anywhere(self):
        # Defensive: even if a user types `--debug analyze ...` we should
        # NOT silently rewrite their line; argparse will handle it.
        self.assertFalse(_looks_like_legacy_invocation(
            ["--debug", "analyze", "sample.txt"]))

    def test_dash_h_falls_through(self):
        # Top-level --help should hit the subcommand parser, not get
        # wrapped as `analyze --help`.
        self.assertFalse(_looks_like_legacy_invocation(["--help"]))
        self.assertFalse(_looks_like_legacy_invocation(["-h"]))

    def test_portal_subcommands_recognized(self):
        for c in ("portal-fetch", "portal-sync",
                  "portal-balances", "portal-apply", "reasons", "export", "import"):
            self.assertIn(c, KNOWN_SUBCOMMANDS)


if __name__ == "__main__":
    unittest.main()

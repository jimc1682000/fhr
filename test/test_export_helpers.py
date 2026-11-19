"""Unit tests for `lib/commands/export.py` helpers (Tier 1)."""

import argparse
import unittest
from datetime import date

from lib.commands.export import _parse_date


class TestExportParseDate(unittest.TestCase):
    def test_slash(self):
        self.assertEqual(_parse_date("2026/04/01"), date(2026, 4, 1))

    def test_dash(self):
        self.assertEqual(_parse_date("2026-04-01"), date(2026, 4, 1))

    def test_invalid(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_date("foo")


class TestExportParserArgs(unittest.TestCase):
    """Parser-level smoke tests: build parser, parse args, verify defaults."""

    def _parse(self, *argv):
        from lib.cli import build_parser

        parser = build_parser()
        return parser.parse_args(argv)

    def test_export_defaults(self):
        ns = self._parse("export", "--to=analysis-v1", "sample.txt", "--out", "tmp/out.json")
        self.assertEqual(ns.cmd, "export")
        self.assertEqual(ns.to, "analysis-v1")
        self.assertEqual(ns.filepath, "sample.txt")
        self.assertEqual(ns.out, "tmp/out.json")
        self.assertIsNone(ns.cutoff)
        self.assertIsNone(ns.today)
        # Default: full analysis (incremental=False per the Codex fix)
        self.assertFalse(ns.incremental)

    def test_export_with_dates(self):
        ns = self._parse(
            "export",
            "--to=analysis-v1",
            "x.txt",
            "--out",
            "y.json",
            "--cutoff",
            "2033/06/17",
            "--today",
            "2033/07/19",
        )
        self.assertEqual(ns.cutoff, date(2033, 6, 17))
        self.assertEqual(ns.today, date(2033, 7, 19))

    def test_export_opt_in_incremental(self):
        ns = self._parse("export", "--to=analysis-v1", "x.txt", "--out", "y.json", "--incremental")
        self.assertTrue(ns.incremental)


if __name__ == "__main__":
    unittest.main()

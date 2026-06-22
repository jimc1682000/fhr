"""Unit tests for `lib/commands/import_.py` parser surface (Tier 1)."""

import unittest


class TestImportParserArgs(unittest.TestCase):
    def _parse(self, *argv):
        from lib.cli import build_parser

        parser = build_parser()
        return parser.parse_args(argv)

    def test_minimal(self):
        ns = self._parse("import", "snap.json", "--from=portal-json", "--out", "out.txt")
        self.assertEqual(ns.cmd, "import")
        self.assertEqual(ns.snapshot, "snap.json")
        self.assertEqual(ns.source, "portal-json")
        self.assertEqual(ns.out, "out.txt")
        self.assertFalse(ns.legacy)

    def test_legacy_flag(self):
        ns = self._parse(
            "import", "snap.json", "--from=portal-json", "--out", "out.txt", "--legacy"
        )
        self.assertTrue(ns.legacy)


if __name__ == "__main__":
    unittest.main()

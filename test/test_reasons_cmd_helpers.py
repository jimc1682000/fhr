"""Unit tests for `lib/commands/reasons.py` parser surface (Tier 1).

The data-layer helpers (`lib/reasons.py`) are already covered in
`test/test_reasons.py`. Here we focus on the CLI handler glue:
default roots, required --author, --schedule-end passthrough.
"""

import unittest


class TestReasonsParserArgs(unittest.TestCase):
    def _parse(self, *argv):
        from lib.cli import build_parser

        parser = build_parser()
        return parser.parse_args(argv)

    def test_minimal(self):
        ns = self._parse(
            "reasons",
            "--input",
            "tmp/analysis.json",
            "--out",
            "tmp/evidence.json",
            "--author",
            "Jimmy Chen",
        )
        self.assertEqual(ns.cmd, "reasons")
        self.assertEqual(ns.input, "tmp/analysis.json")
        self.assertEqual(ns.out, "tmp/evidence.json")
        self.assertEqual(ns.author, ["Jimmy Chen"])
        # Default schedule_end matches AttendanceConfig
        self.assertEqual(ns.schedule_end, "18:30")
        # Roots default → None (handler will fall back to DEFAULT_GIT_REPO_ROOTS)
        self.assertIsNone(ns.roots)

    def test_multiple_authors(self):
        ns = self._parse(
            "reasons",
            "--input",
            "x",
            "--out",
            "y",
            "--author",
            "a",
            "--author",
            "b",
        )
        self.assertEqual(ns.author, ["a", "b"])

    def test_custom_roots(self):
        ns = self._parse(
            "reasons",
            "--input",
            "x",
            "--out",
            "y",
            "--author",
            "a",
            "--root",
            "/foo",
            "--root",
            "/bar",
        )
        self.assertEqual(ns.roots, ["/foo", "/bar"])

    def test_custom_schedule_end(self):
        ns = self._parse(
            "reasons",
            "--input",
            "x",
            "--out",
            "y",
            "--author",
            "a",
            "--schedule-end",
            "19:00",
        )
        self.assertEqual(ns.schedule_end, "19:00")


if __name__ == "__main__":
    unittest.main()

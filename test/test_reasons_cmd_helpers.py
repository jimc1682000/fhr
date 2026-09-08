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


class TestWeekendCandidateSpan(unittest.TestCase):
    """`_add_weekend_candidates` must scan to the end of the analysed period,
    not just to the last flagged entry — the analyzer emits nothing for a
    weekend, so a Sunday after the final weekday entry falls outside it."""

    def _run(self, analysis):
        from unittest import mock

        from lib.commands.reasons import _add_weekend_candidates

        seen = {}

        def fake_detect(start, end, authors, *, repos=None, **kw):
            seen["span"] = (start, end)
            return []

        with (
            mock.patch("lib.reasons.discover_repos", return_value=[]),
            mock.patch("lib.weekend_ot.detect_candidates", side_effect=fake_detect),
        ):
            _add_weekend_candidates(
                {},
                analysis,
                ["a"],
                roots=(),
                exclude_repos=(),
                work_hosts=(),
            )
        return seen["span"]

    def test_span_extends_to_analysis_end(self):
        from datetime import date

        span = self._run(
            {
                "analysis_end": "2026/09/08",
                "overtime": [{"date": "2026/08/26"}],
                "leave": [{"date": "2026/09/04"}],
            }
        )
        self.assertEqual(span, (date(2026, 8, 26), date(2026, 9, 8)))

    def test_span_falls_back_to_entry_dates_without_analysis_end(self):
        from datetime import date

        span = self._run(
            {
                "overtime": [{"date": "2026/08/26"}],
                "leave": [{"date": "2026/09/04"}],
            }
        )
        self.assertEqual(span, (date(2026, 8, 26), date(2026, 9, 4)))

    def test_analysis_end_never_shrinks_the_span(self):
        from datetime import date

        span = self._run(
            {
                "analysis_end": "2026/08/01",
                "overtime": [],
                "leave": [{"date": "2026/09/04"}],
            }
        )
        self.assertEqual(span, (date(2026, 9, 4), date(2026, 9, 4)))

    def test_no_entries_returns_zero(self):
        from lib.commands.reasons import _add_weekend_candidates

        self.assertEqual(
            _add_weekend_candidates(
                {},
                {"analysis_end": "2026/09/08", "overtime": [], "leave": []},
                ["a"],
                roots=(),
                exclude_repos=(),
                work_hosts=(),
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()

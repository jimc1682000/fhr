"""Tests for `lib/weekend_ot.py`."""

import unittest
from datetime import date
from unittest import mock

from lib.weekend_ot import (
    detect_candidates,
    list_weekend_holiday_dates,
    merge_into_analysis,
)


class TestListWeekendHolidayDates(unittest.TestCase):
    def test_saturdays_and_sundays(self):
        # 2026/04/01 (Wed) - 2026/04/12 (Sun)
        out = list_weekend_holiday_dates(date(2026, 4, 1), date(2026, 4, 12))
        out_strs = [d.strftime("%m/%d") for d in out]
        # Saturdays / Sundays only
        self.assertEqual(out_strs, ["04/04", "04/05", "04/11", "04/12"])

    def test_includes_explicit_holiday(self):
        out = list_weekend_holiday_dates(
            date(2026, 5, 1),
            date(2026, 5, 3),
            holidays={date(2026, 5, 1)},  # Friday Labor Day
        )
        out_strs = sorted(d.strftime("%m/%d") for d in out)
        self.assertEqual(out_strs, ["05/01", "05/02", "05/03"])


class TestDetectCandidates(unittest.TestCase):
    def test_returns_candidate_when_commits_exist(self):
        # 2026/04/25 was a Saturday with two commits in the session
        fake_commits_by_date = {
            (date(2026, 4, 25)): [
                {
                    "repo": "kb-devops-raw",
                    "sha": "abc",
                    "subject": "note(aws-nuke)",
                    "time": "2026-04-25T14:12:00",
                },
                {
                    "repo": "kb-devops-raw",
                    "sha": "def",
                    "subject": "follow up",
                    "time": "2026-04-25T14:35:00",
                },
            ],
            (date(2026, 4, 18)): [],  # quiet Saturday
        }

        def fake_commits_on(repo, target, authors, **kw):
            return fake_commits_by_date.get(target, [])

        with (
            mock.patch("lib.weekend_ot.commits_on", side_effect=fake_commits_on),
            mock.patch("lib.weekend_ot.discover_repos", return_value=["fake-repo"]),
        ):
            out = detect_candidates(
                date(2026, 4, 1),
                date(2026, 4, 30),
                authors=["Tester"],
            )
        self.assertEqual(len(out), 1)
        cand = out[0]
        self.assertEqual(cand["date"], "2026/04/25")
        self.assertEqual(cand["weekday"], "六")
        self.assertEqual(cand["location"], "在外地")
        self.assertGreaterEqual(cand["hours"], 1)
        self.assertIn("evidence", cand)
        self.assertEqual(len(cand["evidence"]["git"]), 2)

    def test_skips_days_with_no_commits(self):
        with (
            mock.patch("lib.weekend_ot.commits_on", return_value=[]),
            mock.patch("lib.weekend_ot.discover_repos", return_value=["fake"]),
        ):
            out = detect_candidates(
                date(2026, 4, 1),
                date(2026, 4, 30),
                authors=["Tester"],
            )
        self.assertEqual(out, [])

    def test_holidays_picked_up(self):
        def fake_commits_on(repo, target, authors, **kw):
            if target == date(2026, 5, 1):
                return [
                    {
                        "repo": "x",
                        "sha": "1",
                        "subject": "incident",
                        "time": "2026-05-01T10:00:00",
                    }
                ]
            return []

        with (
            mock.patch("lib.weekend_ot.commits_on", side_effect=fake_commits_on),
            mock.patch("lib.weekend_ot.discover_repos", return_value=["x"]),
        ):
            out = detect_candidates(
                date(2026, 5, 1),
                date(2026, 5, 1),
                authors=["Tester"],
                holidays={date(2026, 5, 1)},
            )
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["is_holiday"])


class TestMergeIntoAnalysis(unittest.TestCase):
    def test_appends_new_candidate(self):
        analysis = {
            "schema_version": "attendance-analysis/v1",
            "overtime": [],
            "leave": [],
            "summary": {
                "overtime_count": 0,
                "overtime_hours": 0,
                "leave_count": 0,
                "leave_hours": 0,
            },
        }
        candidates = [
            {
                "date": "2026/04/25",
                "start_time": "1400",
                "end_time": "1500",
                "hours": 1,
                "location": "在外地",
            }
        ]
        added = merge_into_analysis(analysis, candidates)
        self.assertEqual(added, 1)
        self.assertEqual(len(analysis["overtime"]), 1)
        self.assertEqual(analysis["summary"]["overtime_count"], 1)
        self.assertEqual(analysis["summary"]["overtime_hours"], 1)

    def test_skips_duplicate(self):
        analysis = {
            "schema_version": "attendance-analysis/v1",
            "overtime": [
                {
                    "date": "2026/04/25",
                    "start_time": "1400",
                    "end_time": "1500",
                    "hours": 1,
                    "location": "在外地",
                    "reason": "x",
                }
            ],
            "leave": [],
            "summary": {
                "overtime_count": 1,
                "overtime_hours": 1,
                "leave_count": 0,
                "leave_hours": 0,
            },
        }
        added = merge_into_analysis(
            analysis,
            [
                {
                    "date": "2026/04/25",
                    "start_time": "1400",
                    "end_time": "1500",
                    "hours": 1,
                    "location": "在外地",
                }
            ],
        )
        self.assertEqual(added, 0)
        self.assertEqual(len(analysis["overtime"]), 1)


if __name__ == "__main__":
    unittest.main()

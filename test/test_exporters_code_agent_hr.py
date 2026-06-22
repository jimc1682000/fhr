"""Tests for `lib/exporters/code_agent_hr.py`.

Cover end-time math (`start + hours`), filters (cutoff / future),
WFH synthesis, and the schema_version stamp.
"""

import json
import os
import tempfile
import unittest
from datetime import date, datetime

from attendance_analyzer import Issue, IssueType
from lib.exporters.code_agent_hr import (
    SCHEMA_VERSION,
    ExportOptions,
    issues_to_analysis,
    write,
)


def _ot(date_str: str, time_range: str, minutes: int) -> Issue:
    return Issue(
        date=datetime.strptime(date_str, "%Y/%m/%d"),
        type=IssueType.OVERTIME,
        duration_minutes=minutes,
        description=f"加班 {minutes // 60}小時",
        time_range=time_range,
        calculation="",
    )


def _late(date_str: str, time_range: str, minutes: int) -> Issue:
    return Issue(
        date=datetime.strptime(date_str, "%Y/%m/%d"),
        type=IssueType.LATE,
        duration_minutes=minutes,
        description=f"遲到 {minutes} 分鐘",
        time_range=time_range,
        calculation="",
    )


def _wfh(date_str: str) -> Issue:
    return Issue(
        date=datetime.strptime(date_str, "%Y/%m/%d"),
        type=IssueType.WFH,
        duration_minutes=540,
        description="WFH",
        time_range="",
        calculation="",
    )


def _full_day(date_str: str) -> Issue:
    return Issue(
        date=datetime.strptime(date_str, "%Y/%m/%d"),
        type=IssueType.WEEKDAY_LEAVE,
        duration_minutes=480,
        description="整天沒進公司，建議請假",
        time_range="",
        calculation="",
    )


class TestOvertimeMath(unittest.TestCase):
    def test_end_time_is_start_plus_hours_not_actual_punch(self):
        # 04/20 18:30-21:05 actual punch → 2h applicable, end = 18:30+2h = 20:30
        out = issues_to_analysis([_ot("2026/04/20", "18:30~21:05", 155)])
        self.assertEqual(out["overtime"][0]["start_time"], "1830")
        self.assertEqual(out["overtime"][0]["end_time"], "2030")
        self.assertEqual(out["overtime"][0]["hours"], 2)

    def test_early_arrival_baseline_preserved(self):
        # 04/22 actual checkin 09:05 → expected_checkout 18:05, OT 18:05-21:03 → 2h end 20:05
        out = issues_to_analysis([_ot("2026/04/22", "18:05~21:03", 178)])
        self.assertEqual(out["overtime"][0]["start_time"], "1805")
        self.assertEqual(out["overtime"][0]["end_time"], "2005")
        self.assertEqual(out["overtime"][0]["hours"], 2)

    def test_under_60min_dropped(self):
        out = issues_to_analysis([_ot("2026/04/01", "18:30~19:20", 50)])
        self.assertEqual(out["overtime"], [])
        self.assertEqual(out["skipped"][0]["reason"], "<1h")

    def test_floor_to_whole_hours(self):
        # 178min → 2h (not 3); 200min → 3h
        out = issues_to_analysis(
            [
                _ot("2026/04/22", "18:30~21:28", 178),
                _ot("2026/04/27", "18:30~21:50", 200),
            ]
        )
        self.assertEqual(out["overtime"][0]["hours"], 2)
        self.assertEqual(out["overtime"][1]["hours"], 3)


class TestLateMath(unittest.TestCase):
    def test_ceil_hours_from_09_30(self):
        # 04/20 actual 11:26 = late 116min → ceil 2h, end = 09:30+2h = 11:30
        out = issues_to_analysis([_late("2026/04/20", "09:30~11:26", 116)])
        e = out["leave"][0]
        self.assertEqual(e["start_time"], "0930")
        self.assertEqual(e["end_time"], "1130")
        self.assertEqual(e["hours"], 2)
        self.assertEqual(e["type_hint"], "late")

    def test_minimum_one_hour(self):
        # 5 min late still requires 1h leave
        out = issues_to_analysis([_late("2026/04/23", "09:30~09:35", 5)])
        self.assertEqual(out["leave"][0]["hours"], 1)
        self.assertEqual(out["leave"][0]["end_time"], "1030")


class TestWFH(unittest.TestCase):
    def test_full_day_default(self):
        out = issues_to_analysis([_wfh("2026/04/24")])
        e = out["leave"][0]
        self.assertEqual(e["start_time"], "0930")
        self.assertEqual(e["end_time"], "1830")
        self.assertEqual(e["hours"], 9)
        self.assertEqual(e["type_hint"], "WFH")
        self.assertEqual(e["reason"], "WFH")

    def test_respects_schedule_overrides(self):
        out = issues_to_analysis(
            [_wfh("2026/04/24")],
            ExportOptions(schedule_start_hhmm="0900", schedule_end_hhmm="1800"),
        )
        e = out["leave"][0]
        self.assertEqual(e["start_time"], "0900")
        self.assertEqual(e["end_time"], "1800")
        self.assertEqual(e["hours"], 9)


class TestFullDayLeave(unittest.TestCase):
    def test_weekday_full_day_emitted_as_leave(self):
        # 平日整日缺勤須輸出成可申請的整天請假（修復先前 silently ignored）
        out = issues_to_analysis([_full_day("2026/06/10")])
        self.assertEqual(len(out["leave"]), 1)
        e = out["leave"][0]
        self.assertEqual(e["date"], "2026/06/10")
        self.assertEqual(e["start_time"], "0930")
        self.assertEqual(e["end_time"], "1830")
        self.assertEqual(e["hours"], 8)  # 午休不計
        self.assertEqual(e["type_hint"], "full_day")

    def test_full_day_counts_in_summary(self):
        out = issues_to_analysis([_full_day("2026/06/10"), _full_day("2026/06/15")])
        self.assertEqual(out["summary"]["leave_count"], 2)
        self.assertEqual(out["summary"]["leave_hours"], 16)


class TestFilters(unittest.TestCase):
    def test_cutoff_drops_on_or_before(self):
        out = issues_to_analysis(
            [
                _ot("2026/04/17", "18:30~20:30", 120),
                _ot("2026/04/18", "18:30~20:30", 120),
            ],
            ExportOptions(cutoff_date=date(2026, 4, 17)),
        )
        self.assertEqual(len(out["overtime"]), 1)
        self.assertEqual(out["overtime"][0]["date"], "2026/04/18")
        self.assertEqual(out["skipped"][0]["reason"], "<= cutoff")

    def test_future_drops_after_today(self):
        out = issues_to_analysis(
            [
                _ot("2026/05/19", "18:30~20:30", 120),
                _ot("2026/05/22", "18:30~20:30", 120),
            ],
            ExportOptions(today=date(2026, 5, 20)),
        )
        self.assertEqual(len(out["overtime"]), 1)
        self.assertEqual(out["overtime"][0]["date"], "2026/05/19")
        self.assertEqual(out["skipped"][0]["reason"], "future")


class TestPayloadShape(unittest.TestCase):
    def test_schema_version_first(self):
        out = issues_to_analysis([_ot("2026/04/20", "18:30~20:30", 120)])
        self.assertEqual(next(iter(out)), "schema_version")
        self.assertEqual(out["schema_version"], SCHEMA_VERSION)

    def test_summary_matches_arrays(self):
        out = issues_to_analysis(
            [
                _ot("2026/04/20", "18:30~20:30", 120),
                _ot("2026/04/22", "18:30~20:30", 120),
                _late("2026/04/20", "09:30~10:30", 60),
            ]
        )
        self.assertEqual(out["summary"]["overtime_count"], 2)
        self.assertEqual(out["summary"]["overtime_hours"], 4)
        self.assertEqual(out["summary"]["leave_count"], 1)
        self.assertEqual(out["summary"]["leave_hours"], 1)

    def test_cutoff_date_in_payload(self):
        out = issues_to_analysis(
            [_ot("2026/04/20", "18:30~20:30", 120)],
            ExportOptions(cutoff_date=date(2026, 4, 17)),
        )
        self.assertEqual(out["cutoff_date"], "2026/04/17")


class TestWrite(unittest.TestCase):
    def test_persists_pretty_json(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            payload = write(path, [_ot("2026/04/20", "18:30~20:30", 120)])
            loaded = json.loads(open(path, encoding="utf-8").read())
            self.assertEqual(loaded["schema_version"], SCHEMA_VERSION)
            self.assertEqual(loaded["overtime"][0]["hours"], 2)
            self.assertEqual(loaded, payload)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()

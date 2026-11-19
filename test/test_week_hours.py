import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from fractions import Fraction
from unittest import mock

from lib.portal.statuses import (
    ACTIVE_FORM_STATUSES,
    FINAL_FORM_STATUSES,
    INACTIVE_FORM_STATUSES,
)
from lib.week_hours import (
    DEAD,
    FINAL,
    PENDING,
    UNKNOWN,
    classify_status,
    compute_week,
    default_week_start,
    display_hours,
    format_week,
    week_start,
)

MON = date(2033, 6, 20)
NEXT_MON = date(2033, 6, 27)
HOLIDAYS = {date(2033, 6, 24)}
DONE = "流程結束(完成)"


def leave(d, hours, leave_type="特休假", status=DONE, end_date=None, start="0930", end="1830"):
    return {
        "date": d,
        "start_time": start,
        "end_date": end_date or d,
        "end_time": end,
        "hours": hours,
        "leave_type": leave_type,
        "status": status,
    }


def overtime(d, hours, status=DONE, start="1830", end=None, end_date=None):
    if end is None:
        total = int(start[:2]) * 60 + int(start[2:]) + int(hours * 60)
        end = f"{total // 60:02d}{total % 60:02d}"
    return {
        "date": d,
        "start_time": start,
        "end_date": end_date or d,
        "end_time": end,
        "hours": hours,
        "status": status,
    }


class TestStatus(unittest.TestCase):
    def test_final_statuses_are_portal_active_statuses(self):
        self.assertLessEqual(FINAL_FORM_STATUSES, ACTIVE_FORM_STATUSES)

    def test_classification(self):
        for status in INACTIVE_FORM_STATUSES:
            self.assertEqual(classify_status(status), DEAD, status)
        self.assertEqual(classify_status("已核准"), FINAL)
        self.assertEqual(classify_status(DONE), FINAL)
        self.assertEqual(classify_status("簽核中"), PENDING)
        self.assertEqual(classify_status("已送出 (本機新增)"), PENDING)
        self.assertEqual(classify_status("奇怪的狀態"), UNKNOWN)
        self.assertEqual(classify_status(""), UNKNOWN)

    def test_any_status_mentioning_withdraw_or_reject_is_dead(self):
        for status in ("流程停止（抽單）", "主管駁回", " 流程結束（駁回） "):
            self.assertEqual(classify_status(status), DEAD, status)
        self.assertEqual(classify_status("流程結束（完成）"), FINAL)

    def test_full_width_dead_statuses_not_counted(self):
        forms = [
            leave("2033/06/20", 8, status="流程停止（抽單）"),
            leave("2033/06/21", 8, status="主管駁回"),
        ]
        week = compute_week(MON, forms, [overtime("2033/06/22", 2, "主管駁回")], set())
        self.assertEqual(week.ttl, 40)
        self.assertTrue(week.complete)


class TestDefaultWeek(unittest.TestCase):
    def test_friday_not_over_picks_previous_week(self):
        self.assertEqual(default_week_start(date(2033, 6, 24)), date(2033, 6, 13))

    def test_saturday_sunday_monday_pick_the_week_just_ended(self):
        for today in (date(2033, 6, 25), date(2033, 6, 26), date(2033, 6, 27)):
            self.assertEqual(default_week_start(today), MON, today)


class TestComputeWeek(unittest.TestCase):
    def test_plain_week_counts_8h_per_weekday_and_0_on_holiday(self):
        week = compute_week(MON, [], [], HOLIDAYS)
        self.assertEqual([d.total for d in week.days], [8, 8, 8, 8, 0])
        self.assertEqual(week.ttl, 32)
        self.assertIn("國定假日", week.days[4].notes)
        self.assertTrue(week.complete)

    def test_leave_deducts_and_overtime_adds(self):
        week = compute_week(
            MON,
            [leave("2033/06/20", 8, "半薪病假")],
            [overtime("2033/06/21", 1)],
            HOLIDAYS,
        )
        self.assertEqual(week.ttl, 25)
        self.assertEqual(week.leave, 8)
        self.assertEqual(week.overtime, 1)
        self.assertEqual(week.days[1].total, 9)

    def test_partial_leave(self):
        week = compute_week(MON, [leave("2033/06/20", 3, "半薪病假", end="1230")], [], set())
        self.assertEqual(week.days[0].total, 5)
        self.assertEqual(week.ttl, 37)

    def test_single_day_form_keeps_stated_hours(self):
        # 09:30–13:30 is 3h of work time once lunch is excluded, but a
        # single-day form always counts its stated hours, with no note.
        week = compute_week(MON, [leave("2033/06/20", 4, end="1330")], [], set())
        self.assertEqual(week.days[0].leave, 4)
        self.assertEqual(week.days[0].notes, ["特休假 4h"])

    def test_decimal_hours(self):
        week = compute_week(MON, [leave("2033/06/20", 1.5, end="1100")], [], set())
        self.assertEqual(week.days[0].total, 6.5)
        self.assertEqual(week.leave, 1.5)

    def test_work_type_leave_counts_as_work(self):
        forms = [
            leave("2033/06/20", 8, "異地辦公(8hr一週)"),
            leave("2033/06/21", 1, "忘刷忘帶卡", end="1030"),
        ]
        week = compute_week(MON, forms, [], set())
        self.assertEqual(week.ttl, 40)
        self.assertEqual(week.leave, 0)

    def test_official_leave_counts_as_leave(self):
        week = compute_week(MON, [leave("2033/06/23", 6, "公假-訓練", end="1630")], [], set())
        self.assertEqual(week.days[3].total, 2)
        self.assertEqual(week.leave, 6)
        self.assertEqual(week.ttl, 34)

    def test_dead_forms_ignored(self):
        forms = [
            leave("2033/06/20", 8, status="流程停止(抽單)"),
            leave("2033/06/21", 8, status="流程結束(駁回)"),
            leave("2033/06/22", 8, status="已撤回"),
            leave("2033/06/23", 8, status="退件"),
        ]
        ot = [overtime("2033/06/22", 2, "已駁回"), overtime("2033/06/23", 2, "已撤回")]
        week = compute_week(MON, forms, ot, set())
        self.assertEqual(week.ttl, 40)
        self.assertTrue(all(not d.notes for d in week.days))

    def test_pending_forms_counted_and_flagged(self):
        week = compute_week(
            MON,
            [leave("2033/06/20", 8, status="簽核中")],
            [overtime("2033/06/21", 2, status="主管簽核 - 一階主管")],
            set(),
        )
        self.assertEqual(week.leave, 8)
        self.assertEqual(week.overtime, 2)
        self.assertIn("（簽核中）", week.days[0].notes[0])
        self.assertIn("（簽核中）", week.days[1].notes[0])
        self.assertTrue(week.complete)

    def test_locally_recorded_form_counted_but_not_trusted(self):
        # portal-apply may record its 2h draft while the Portal already has a
        # different (e.g. approved 1.5h) form; only portal-sync can tell.
        local = overtime("2033/06/21", 2, status="已送出 (本機新增)")
        week = compute_week(MON, [], [local], set())
        self.assertEqual(week.overtime, 2)
        self.assertIn("本機記錄", week.days[1].notes[0])
        self.assertFalse(week.complete)
        self.assertIn("portal-sync", week.warnings[0])

    def test_approved_forms_not_flagged(self):
        week = compute_week(
            MON,
            [leave("2033/06/20", 8, status="已核准")],
            [overtime("2033/06/21", 2, status="已核准")],
            set(),
        )
        self.assertEqual(week.days[0].notes, ["特休假 8h"])
        self.assertEqual(week.days[1].notes, ["加班 2h"])

    def test_unknown_status_counted_but_marks_week_incomplete(self):
        week = compute_week(MON, [leave("2033/06/20", 8, status="神秘狀態")], [], set())
        self.assertEqual(week.leave, 8)
        self.assertIn("狀態不明", week.days[0].notes[0])
        self.assertFalse(week.complete)

    def test_missing_hours_marks_week_incomplete(self):
        week = compute_week(
            MON, [leave("2033/06/21", None)], [overtime("2033/06/22", None, end="2030")], set()
        )
        self.assertEqual(week.ttl, 40)
        self.assertFalse(week.complete)
        self.assertEqual(len(week.warnings), 2)
        self.assertIn("時數不明", week.days[1].notes[0])
        self.assertIn("時數不明", week.days[2].notes[0])
        self.assertIn("⚠️ 總計不完整", format_week(week))

    def test_missing_hours_outside_week_not_reported(self):
        week = compute_week(MON, [leave("2033/06/28", None)], [], set())
        self.assertTrue(week.complete)

    def test_leave_across_weekend_split_by_time(self):
        # Fri 14:30 → Mon 12:30 = 4h on Friday + 3h on Monday.
        form = leave("2033/06/24", 7, start="1430", end_date="2033/06/27", end="1230")
        this_week = compute_week(MON, [form], [], set())
        self.assertEqual(this_week.days[4].leave, 4)
        self.assertEqual(this_week.leave, 4)
        next_week = compute_week(NEXT_MON, [form], [], set())
        self.assertEqual(next_week.days[0].leave, 3)
        self.assertEqual(next_week.leave, 3)

    def test_leave_skips_holiday(self):
        # Thu → Mon 16h with a holiday Friday: Thu 8h, Mon 8h, Friday stays 0.
        form = leave("2033/06/23", 16, end_date="2033/06/27")
        week = compute_week(MON, [form], [], HOLIDAYS)
        self.assertEqual(week.days[3].leave, 8)
        self.assertEqual(week.days[4].leave, 0)
        self.assertEqual(week.days[4].notes, ["國定假日"])
        self.assertEqual(week.leave, 8)
        self.assertEqual(compute_week(NEXT_MON, [form], [], HOLIDAYS).leave, 8)

    def assert_not_allocated(self, form, holidays=frozenset(), note_index=3):
        week = compute_week(MON, [form], [], set(holidays))
        self.assertEqual(week.leave, 0)
        self.assertEqual(week.ttl, 40 - 8 * len(holidays))
        self.assertFalse(week.complete)
        self.assertIn("跨日單時數與時段不符，無法分配", week.days[note_index].notes[-1])
        return week

    def test_multi_day_mismatch_not_counted(self):
        # Thu–Fri full days are 16h of work time; the form says 12h.
        self.assert_not_allocated(leave("2033/06/23", 12, end_date="2033/06/24"))

    def test_multi_day_stated_more_than_span_not_counted(self):
        # Thu 14:30 → Fri 18:30 is 12h of work time; the form says 16h.
        form = leave("2033/06/23", 16, start="1430", end_date="2033/06/24")
        self.assert_not_allocated(form)

    def test_multi_day_without_any_workday_not_counted(self):
        # Fri (holiday) → Sun: no eligible workday at all.
        form = leave("2033/06/24", 8, end_date="2033/06/26")
        self.assert_not_allocated(form, HOLIDAYS, note_index=4)

    def test_multi_day_into_holiday_only_one_workday_not_counted(self):
        # Thu → holiday Fri, 16h: only Thu's 8h fit.
        form = leave("2033/06/23", 16, end_date="2033/06/24")
        self.assert_not_allocated(form, HOLIDAYS)

    def test_multi_day_tiny_tail_mismatch_not_counted(self):
        # 06/20 09:30 → 06/23 09:31 is 24h+1m of work time; the form says 2h.
        form = leave("2033/06/20", 2, end_date="2033/06/23", end="0931")
        self.assert_not_allocated(form, note_index=0)

    def test_overtime_ending_at_midnight_is_multi_day(self):
        # 23:00 → 00:00 next day is 1h by time; the form says 8h.
        form = overtime("2033/06/24", 8, start="2300", end_date="2033/06/25", end="0000")
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.overtime, 0)
        self.assertEqual(week.ttl, 40)
        self.assertFalse(week.complete)
        self.assertIn("無法分配", week.days[4].notes[-1])

    def test_overtime_ending_at_midnight_matching_hours(self):
        form = overtime("2033/06/24", 1, start="2300", end_date="2033/06/25", end="0000")
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.days[4].overtime, 1)
        self.assertTrue(week.complete)

    def test_leave_ending_at_midnight_is_multi_day(self):
        form = leave("2033/06/23", 8, start="1430", end_date="2033/06/24", end="0000")
        week = compute_week(MON, [form], [], set())
        self.assertEqual(week.leave, 0)
        self.assertFalse(week.complete)

    def test_difference_of_exactly_0_01h_accepted(self):
        # Thu–Fri full days are exactly 16h of work time.
        for stated in (16.01, 15.99):
            with self.subTest(stated):
                form = leave("2033/06/23", stated, end_date="2033/06/24")
                week = compute_week(MON, [form], [], set())
                self.assertEqual(week.leave, 16)
                self.assertTrue(week.complete)

    def test_difference_just_over_0_01h_rejected(self):
        for stated in (16.0100004, 15.9899996):
            with self.subTest(stated):
                form = leave("2033/06/23", stated, end_date="2033/06/24")
                week = compute_week(MON, [form], [], set())
                self.assertEqual(week.leave, 0)
                self.assertFalse(week.complete)

    def test_overtime_totals_not_built_from_rounded_days(self):
        # 22:59 → 01:01 is 61 + 61 minutes; each day alone would round to 1.02h.
        form = overtime("2033/06/23", 2.03, start="2259", end_date="2033/06/24", end="0101")
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.overtime, Fraction(122, 60))
        self.assertTrue(week.complete)
        text = format_week(week)
        self.assertIn("TTL: 42.03", text)
        self.assertIn("加班 (hr): 2.03", text)
        self.assertIn("| 06/23（四） | 9.02 | 0 | 1.02 |", text)

    def test_leave_totals_not_built_from_rounded_days(self):
        # Mon 18:29 → Tue 09:31 is 1 + 1 workday minutes; per-day rounding gives 0.04h.
        form = leave("2033/06/20", 0.03, start="1829", end_date="2033/06/21", end="0931")
        week = compute_week(MON, [form], [], set())
        self.assertEqual(week.leave, Fraction(2, 60))
        self.assertEqual(display_hours(week.leave), 0.03)
        self.assertEqual(display_hours(week.ttl), 39.97)
        self.assertTrue(week.complete)

    def test_display_hours(self):
        self.assertEqual(display_hours(8), 8)
        self.assertIsInstance(display_hours(Fraction(16)), int)
        self.assertEqual(display_hours(Fraction(1, 200)), 0.01)  # half up
        self.assertEqual(display_hours(Fraction(13, 2)), 6.5)
        cases = {"0.005": 0.01, "-0.005": -0.01, "-0.004": 0, "7.665": 7.67}
        for exact, shown in cases.items():
            with self.subTest(exact):
                self.assertEqual(display_hours(Fraction(exact)), shown)
        self.assertIsInstance(display_hours(Fraction("-0.004")), int)

    def test_value_just_below_midpoint_is_not_rounded_up(self):
        # TTL is 40 − 1e-28 + 1.005 = 41.005 − 1e-28, which must show 41.00.
        week = compute_week(
            MON, [leave("2033/06/20", 1e-28, end="1000")], [overtime("2033/06/21", 1.005)], set()
        )
        self.assertEqual(week.ttl, Fraction("41.005") - Fraction(1, 10**28))
        self.assertEqual(display_hours(week.ttl), 41)
        self.assertIn("TTL: 41\n", format_week(week))

    def test_unparsable_hours_raise_value_error(self):
        with self.assertRaisesRegex(ValueError, "時數 'N/A' 無法解析"):
            compute_week(MON, [leave("2033/06/20", "N/A")], [], set())

    def test_out_of_range_hours_raise_value_error(self):
        cases = [
            ("negative leave", [leave("2033/06/20", -1)], []),
            ("negative overtime", [], [overtime("2033/06/20", -1, end="1930")]),
            (
                "huge overtime",
                [],
                [overtime("2033/06/20", "100000000000000000000000001.01", end="1930")],
            ),
            ("overflowing string", [], [overtime("2033/06/20", "1e400", end="1930")]),
            ("overflowing int", [leave("2033/06/20", 10**400)], []),
        ]
        for label, leaves, ots in cases:
            with self.subTest(label), self.assertRaisesRegex(ValueError, "超出合理範圍"):
                compute_week(MON, leaves, ots, set())

    def test_multi_day_tiny_tail_within_tolerance(self):
        # Thu's 8h plus 1 minute of Fri (0.017h) is within 0.01h of the stated 8.02h.
        form = leave("2033/06/23", 8.02, end_date="2033/06/24", end="0931")
        week = compute_week(MON, [form], [], set())
        self.assertEqual(week.days[3].leave, 8)
        self.assertEqual(week.days[4].leave, Fraction(1, 60))
        self.assertEqual(display_hours(week.days[4].leave), 0.02)
        self.assertTrue(week.complete)

    def test_multi_day_overtime_mismatch_not_counted(self):
        form = overtime("2033/06/24", 3, start="2200", end_date="2033/06/25", end="0200")
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.overtime, 0)
        self.assertFalse(week.complete)
        self.assertIn("無法分配", week.days[4].notes[-1])

    def test_single_day_leave_over_8h_capped_and_incomplete(self):
        week = compute_week(MON, [leave("2033/06/20", 9)], [], set())
        self.assertEqual(week.days[0].work, 0)
        self.assertEqual(week.days[0].leave, 8)
        self.assertEqual(week.ttl, 32)
        self.assertEqual(week.ttl, 40 - week.leave + week.overtime)
        self.assertFalse(week.complete)

    def test_overlapping_leaves_never_take_work_below_zero(self):
        forms = [leave("2033/06/20", 6, end="1630"), leave("2033/06/20", 4, start="1430")]
        week = compute_week(MON, forms, [], set())
        self.assertEqual(week.days[0].work, 0)
        self.assertEqual(week.leave, 8)
        self.assertFalse(week.complete)

    def test_work_type_leave_over_8h_not_capped(self):
        week = compute_week(MON, [leave("2033/06/20", 9, "異地辦公(8hr一週)")], [], set())
        self.assertEqual(week.days[0].total, 8)
        self.assertTrue(week.complete)

    def test_overtime_across_midnight_split_by_time(self):
        form = overtime("2033/06/24", 4, start="2200", end_date="2033/06/25", end="0200")
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.days[4].overtime, 2)
        self.assertEqual(week.days[5].day, date(2033, 6, 25))
        self.assertEqual(week.days[5].overtime, 2)
        self.assertEqual(week.overtime, 4)

    def test_overtime_without_end_date_crossing_midnight(self):
        form = {"date": "2033/06/21", "start_time": "2300", "end_time": "0100", "hours": 2}
        form["status"] = DONE
        week = compute_week(MON, [], [form], set())
        self.assertEqual(week.days[1].overtime, 1)
        self.assertEqual(week.days[2].overtime, 1)

    def test_overtime_into_next_week_only_counts_this_weeks_part(self):
        form = overtime("2033/06/26", 5, start="2000", end_date="2033/06/27", end="0100")
        self.assertEqual(compute_week(MON, [], [form], set()).overtime, 4)
        self.assertEqual(compute_week(NEXT_MON, [], [form], set()).overtime, 1)

    def test_holiday_overtime_counted_on_that_day(self):
        week = compute_week(MON, [], [overtime("2033/06/24", 3, start="1000")], HOLIDAYS)
        self.assertEqual(week.days[4].total, 3)
        self.assertEqual(week.ttl, 35)

    def test_forms_outside_week_ignored(self):
        week = compute_week(MON, [leave("2033/06/27", 8)], [overtime("2033/06/18", 3)], set())
        self.assertEqual(week.ttl, 40)

    def test_weekend_day_with_only_a_note_keeps_its_row(self):
        week = compute_week(MON, [], [overtime("2033/06/25", None, end="1800")], set())
        self.assertEqual(week.days[5].day, date(2033, 6, 25))
        self.assertIn("時數不明", week.days[5].notes[0])
        self.assertIn("06/25（六）", format_week(week))

    def test_weekend_overtime_adds_row(self):
        week = compute_week(MON, [], [overtime("2033/06/25", 4, start="1000")], set())
        self.assertEqual(len(week.days), 6)
        self.assertEqual(week.days[5].day, date(2033, 6, 25))
        self.assertEqual(week.ttl, 44)

    def test_duplicate_row_id_rejected(self):
        a = {**leave("2033/06/20", 8), "row_id": "r1"}
        b = {**leave("2033/06/21", 8), "row_id": "r1"}
        with self.assertRaisesRegex(ValueError, "重複的 row_id"):
            compute_week(MON, [a, b], [], set())

    def test_missing_row_ids_allowed(self):
        week = compute_week(MON, [leave("2033/06/20", 8), leave("2033/06/21", 8)], [], set())
        self.assertEqual(week.leave, 16)

    def test_punch_notes_do_not_change_numbers(self):
        punches = {date(2033, 6, 20), date(2033, 6, 21)}
        week = compute_week(
            MON,
            [leave("2033/06/24", 8)],
            [],
            set(),
            punch_days=punches,
            punch_range=(date(2033, 6, 20), date(2033, 6, 22)),
        )
        self.assertEqual(week.ttl, 32)
        self.assertIn("無打卡也無假單", week.days[2].notes[0])
        self.assertIn("未涵蓋", week.days[3].notes[0])
        self.assertEqual(week.days[4].notes, ["特休假 8h"])

    def test_partial_leave_or_overtime_day_without_punch_not_flagged(self):
        week = compute_week(
            MON,
            [leave("2033/06/21", 4, end="1430")],
            [overtime("2033/06/22", 2)],
            set(),
            punch_days={date(2033, 6, 20), date(2033, 6, 23), date(2033, 6, 24)},
            punch_range=(MON, date(2033, 6, 24)),
        )
        self.assertEqual(week.days[1].notes, ["特休假 4h"])
        self.assertEqual(week.days[2].notes, ["加班 2h"])

    def test_punch_file_starting_mid_week(self):
        week = compute_week(
            MON,
            [],
            [],
            set(),
            punch_days={date(2033, 6, 22), date(2033, 6, 23), date(2033, 6, 24)},
            punch_range=(date(2033, 6, 22), date(2033, 6, 24)),
        )
        self.assertIn("未涵蓋", week.days[0].notes[0])
        self.assertIn("未涵蓋", week.days[1].notes[0])
        self.assertEqual(week.days[2].notes, [])

    def test_empty_punch_file_means_nothing_covered(self):
        week = compute_week(MON, [], [], set(), punch_days=set(), punch_range=None)
        self.assertTrue(all("未涵蓋" in d.notes[0] for d in week.days))

    def test_week_start(self):
        self.assertEqual(week_start(date(2033, 6, 23)), MON)
        self.assertEqual(week_start(MON), MON)

    def test_format_week(self):
        text = format_week(compute_week(MON, [], [overtime("2033/06/21", 1)], HOLIDAYS))
        self.assertIn("# 週工時 2033/06/20 ~ 2033/06/24", text)
        self.assertIn("| 06/21（二） | 9 | 0 | 1 | 加班 1h |", text)
        self.assertIn("TTL: 33", text)
        self.assertNotIn("不完整", text)

    def test_format_week_header_covers_weekend_overtime(self):
        week = compute_week(MON, [], [overtime("2033/06/26", 2, start="1000")], set())
        self.assertIn("# 週工時 2033/06/20 ~ 2033/06/26", format_week(week))


class TestWeekHoursCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "state.json")
        self._write_state(
            {
                "last_full_sync": "2033-06-23T10:00:00",
                "synced_at_by_kind": {
                    "leave": "2033-06-23T10:00:00",
                    "overtime": "2033-06-23T10:00:00",
                },
                "leave": [leave("2033/06/20", 8, "半薪病假")],
                "overtime": [overtime("2033/06/21", 1)],
            }
        )
        self.att = os.path.join(self.tmp.name, "att.txt")
        with open(self.att, "w", encoding="utf-8") as f:
            f.write("2033/06/21 09:30\t2033/06/21 09:40\t上班\t\t\t\t\t\t\n")
            f.write("2033/06/21 18:30\t2033/06/21 20:10\t下班\t\t\t\t\t\t\n")
            f.write("2033/06/22 09:30\t\t上班\t\t\t曠職\t\t\t\n")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_state(self, applied):
        with open(self.state, "w", encoding="utf-8") as f:
            json.dump({"users": {"u": {"applied_forms": applied}}}, f)

    def _run(self, *argv):
        from lib.cli import run

        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"FHR_STATE_FILE": self.state}),
            mock.patch("lib.env.load"),
            mock.patch("lib.holidays.HolidayService.load_years", return_value=HOLIDAYS),
            redirect_stdout(buf),
        ):
            run(["fhr", "week-hours", *argv])
        return buf.getvalue()

    def test_dead_form_years_do_not_load_holidays(self):
        from lib.cli import run

        rejected = leave("2033/06/24", 8, status="主管駁回", end_date="2034/01/02")
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [rejected],
                "overtime": [],
            }
        )

        def gov(year):
            return {date(2033, 1, 1)} if year == 2033 else set()

        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"FHR_STATE_FILE": self.state}),
            mock.patch("lib.env.load"),
            mock.patch("lib.holidays.TaiwanGovOpenDataProvider.load", side_effect=gov) as load,
            redirect_stdout(buf),
        ):
            run(["fhr", "week-hours", "--user", "u", "--week", "2033/06/20", "--json"])
        out = json.loads(buf.getvalue())
        self.assertTrue(out["complete"])
        self.assertEqual([c.args[0] for c in load.call_args_list], [2033])

    def test_basic_holiday_fallback_marks_incomplete(self):
        from lib.cli import run

        buf = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"FHR_STATE_FILE": self.state}),
            mock.patch("lib.env.load"),
            mock.patch("lib.holidays.TaiwanGovOpenDataProvider.load", return_value=set()),
            redirect_stdout(buf),
            self.assertLogs("attendance_analyzer", "WARNING") as logs,
        ):
            run(["fhr", "week-hours", "--user", "u", "--week", "2033/06/20", "--json"])
        out = json.loads(buf.getvalue())
        self.assertFalse(out["complete"])
        self.assertIn("2033 年國定假日只載入基本固定假日", out["warnings"][0])
        self.assertIn("基本固定假日", "\n".join(logs.output))

    def test_table_output(self):
        out = self._run("--user", "u", "--week", "2033/06/22", "--attendance", self.att)
        self.assertIn("TTL: 25", out)
        self.assertIn("| 06/22（三） | 8 | 0 | 0 | 無打卡也無假單", out)
        # The file starts on 06/21, so 06/20 is "not covered" — but it has a form anyway.
        self.assertIn("| 06/20（一） | 0 | 8 | 0 | 半薪病假 8h |", out)
        self.assertIn("| 06/23（四） | 8 | 0 | 0 | 打卡資料未涵蓋", out)

    def test_json_output(self):
        out = json.loads(self._run("--user", "u", "--week", "2033-06-20", "--json"))
        self.assertEqual(out["ttl"], 25)
        self.assertEqual(out["leave"], 8)
        self.assertEqual(out["overtime"], 1)
        self.assertEqual(out["days"][1]["hours"], 9)
        self.assertTrue(out["complete"])
        self.assertEqual(out["warnings"], [])

    def test_json_rounds_only_the_exact_totals(self):
        form = overtime("2033/06/23", 2.03, start="2259", end_date="2033/06/24", end="0101")
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [],
                "overtime": [form],
            }
        )
        out = json.loads(self._run("--user", "u", "--week", "2033-06-20", "--json"))
        self.assertEqual(out["overtime"], 2.03)
        self.assertEqual(out["ttl"], 34.03)  # 06/24 is a holiday in this fixture
        self.assertEqual(out["days"][3]["overtime"], 1.02)
        self.assertEqual(out["days"][0]["hours"], 8)

    def test_json_output_reports_incomplete(self):
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [leave("2033/06/20", None)],
                "overtime": [],
            }
        )
        with self.assertLogs("attendance_analyzer", "WARNING"):
            out = json.loads(self._run("--user", "u", "--week", "2033-06-20", "--json"))
        self.assertFalse(out["complete"])
        self.assertEqual(len(out["warnings"]), 1)

    def test_default_week_on_saturday_is_the_week_just_ended(self):
        with mock.patch("lib.commands.week_hours.date") as d:
            d.today.return_value = date(2033, 6, 25)
            out = self._run("--user", "u")
        self.assertIn("2033/06/20 ~ 2033/06/24", out)

    def test_missing_user_exits(self):
        with self.assertRaises(SystemExit):
            self._run("--user", "nobody")

    def test_bad_week_date_rejected(self):
        with self.assertRaises(SystemExit):
            self._run("--user", "u", "--week", "not-a-date")

    def test_leave_only_sync_refused(self):
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t"},
                "leave": [leave("2033/06/20", 8)],
            }
        )
        with self.assertLogs("attendance_analyzer", "ERROR") as logs:
            with self.assertRaises(SystemExit):
                self._run("--user", "u", "--week", "2033/06/20")
        self.assertIn("overtime", "\n".join(logs.output))

    def test_synced_kind_with_zero_rows_accepted(self):
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [],
                "overtime": [],
            }
        )
        self.assertIn("TTL: 32", self._run("--user", "u", "--week", "2033/06/20"))

    def test_kinds_synced_at_different_times_warn(self):
        self._write_state(
            {
                "last_full_sync": "t2",
                "synced_at_by_kind": {"leave": "t2", "overtime": "t1"},
                "leave": [],
                "overtime": [],
            }
        )
        with self.assertLogs("attendance_analyzer", "WARNING") as logs:
            self._run("--user", "u", "--week", "2033/06/20")
        self.assertIn("不是同一次同步", "\n".join(logs.output))

    def test_cache_without_both_sync_times_and_lists_refused(self):
        local_ot = {**overtime("2033/06/21", 1), "status": "已送出 (本機新增)"}
        cases = {
            "legacy full sync": {"last_full_sync": "t", "leave": [], "overtime": []},
            "legacy leave sync + local overtime": {
                "last_full_sync": "t",
                "leave": [],
                "overtime": [local_ot],
            },
            "new format, overtime list missing": {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [],
            },
            "never synced": {"leave": [], "overtime": [local_ot]},
        }
        for name, applied in cases.items():
            with self.subTest(name):
                self._write_state(applied)
                with self.assertLogs("attendance_analyzer", "ERROR") as logs:
                    with self.assertRaises(SystemExit):
                        self._run("--user", "u", "--week", "2033/06/20")
                self.assertIn("portal-sync", "\n".join(logs.output))

    def test_unparsable_hours_exit_with_logged_error(self):
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [leave("2033/06/20", "N/A")],
                "overtime": [],
            }
        )
        with self.assertLogs("attendance_analyzer", "ERROR") as logs:
            with self.assertRaises(SystemExit) as exit_:
                self._run("--user", "u", "--week", "2033/06/20")
        self.assertEqual(exit_.exception.code, 1)
        self.assertIn("無法解析", "\n".join(logs.output))

    def test_duplicate_row_id_exits(self):
        dup = {**leave("2033/06/20", 8), "row_id": "r1"}
        self._write_state(
            {
                "last_full_sync": "t",
                "synced_at_by_kind": {"leave": "t", "overtime": "t"},
                "leave": [dup, dup],
                "overtime": [],
            }
        )
        with self.assertRaises(SystemExit):
            self._run("--user", "u", "--week", "2033/06/20")


if __name__ == "__main__":
    unittest.main()

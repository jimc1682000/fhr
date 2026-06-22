import unittest
from datetime import datetime

from lib.policy import (
    Rules,
    calculate_late_minutes,
    calculate_leave_suggestion,
    calculate_overtime_minutes,
)


class W:
    def __init__(self, ci=None, co=None, date=datetime(2025, 7, 1)):
        class Rec:
            def __init__(self, t):
                self.actual_time = t

        self.checkin_record = Rec(ci) if ci else None
        self.checkout_record = Rec(co) if co else None
        self.date = date


class TestPolicyMore(unittest.TestCase):
    def test_late_from_schedule_start_no_lunch_deduction(self):
        # 11:30 arrival, latest_checkin 09:00, schedule_start 09:30
        # -> 120 min late, no lunch deduction
        rules = Rules(latest_checkin="09:00", schedule_start="09:30")
        wd = W(ci=datetime(2025, 7, 1, 11, 30), co=datetime(2025, 7, 1, 20, 0))
        mins, tr, calc = calculate_late_minutes(wd, rules)
        self.assertEqual(mins, 120)  # 11:30 - 09:30 = 120 min
        self.assertIn("需請假:", calc)
        self.assertNotIn("午休", calc)

    def test_leave_suggestion_deducts_lunch_overlap(self):
        # 13:19 到班：遲到 229 分，但 12:30~13:19 屬午休須扣 49 分
        # -> 缺工 180 分 -> 進位 3h，請假塊 09:30~12:30（非 4h）
        rules = Rules(
            latest_checkin="10:00",
            schedule_start="09:30",
            lunch_start="12:30",
            lunch_end="13:30",
        )
        wd = W(
            ci=datetime(2026, 6, 11, 13, 19),
            co=datetime(2026, 6, 11, 19, 24),
            date=datetime(2026, 6, 11),
        )
        late, _tr, _calc = calculate_late_minutes(wd, rules)
        self.assertEqual(late, 229)
        start, end, hours, effective = calculate_leave_suggestion(wd, rules, late)
        self.assertEqual((start, end), ("09:30", "12:30"))
        self.assertEqual(hours, 3)
        self.assertEqual(effective, 180)

    def test_leave_suggestion_block_crossing_lunch_advances_end(self):
        # 14:00 到班：遲到 270 分，扣午休 60 → 缺工 210 → 進位 4h。
        # 4 工時塊跨午休，終點須加回午休 → 09:30~14:30（否則 Portal 只算 3h）
        rules = Rules(
            latest_checkin="10:00",
            schedule_start="09:30",
            lunch_start="12:30",
            lunch_end="13:30",
        )
        wd = W(
            ci=datetime(2026, 6, 18, 14, 0),
            co=datetime(2026, 6, 18, 19, 0),
            date=datetime(2026, 6, 18),
        )
        late, _tr, _calc = calculate_late_minutes(wd, rules)
        self.assertEqual(late, 270)
        start, end, hours, effective = calculate_leave_suggestion(wd, rules, late)
        self.assertEqual((start, end, hours, effective), ("09:30", "14:30", 4, 210))

    def test_leave_suggestion_no_lunch_overlap_unchanged(self):
        # 11:26 到班：遲到 116 分，未碰午休 -> 維持 ceil 2h，缺工=遲到
        rules = Rules(
            latest_checkin="10:00",
            schedule_start="09:30",
            lunch_start="12:30",
            lunch_end="13:30",
        )
        wd = W(
            ci=datetime(2026, 6, 9, 11, 26),
            co=datetime(2026, 6, 9, 19, 42),
            date=datetime(2026, 6, 9),
        )
        late, _tr, _calc = calculate_late_minutes(wd, rules)
        start, end, hours, effective = calculate_leave_suggestion(wd, rules, late)
        self.assertEqual((start, end, hours, effective), ("09:30", "11:30", 2, 116))

    def test_late_early_return_when_missing_checkin(self):
        rules = Rules()
        wd = W(ci=None, co=datetime(2025, 7, 1, 18, 0))
        mins, tr, calc = calculate_late_minutes(wd, rules)
        self.assertEqual((mins, tr, calc), (0, "", ""))

    def test_overtime_early_return_when_incomplete(self):
        rules = Rules()
        wd = W(ci=datetime(2025, 7, 1, 9, 0), co=None)
        # expected_checkout can be any value since co=None triggers early return
        expected_checkout = datetime(2025, 7, 1, 18, 0)
        actual, applicable, tr, calc = calculate_overtime_minutes(wd, rules, expected_checkout)
        self.assertEqual((actual, applicable, tr, calc), (0, 0, "", ""))


if __name__ == "__main__":
    unittest.main()
"""Category: Policy
Purpose: Additional late/overtime guard branches and no-deduction scenario."""

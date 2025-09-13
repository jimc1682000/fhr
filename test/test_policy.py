import unittest
from datetime import datetime

from attendance_analyzer import AttendanceRecord, WorkDay, AttendanceType
from lib.policy import (
    Rules,
    is_full_day_absent,
    calculate_late_minutes,
    calculate_overtime_minutes,
)


def mk_record(dt_str_sched: str, dt_str_actual: str, typ: AttendanceType):
    sched = datetime.strptime(dt_str_sched, "%Y/%m/%d %H:%M") if dt_str_sched else None
    actual = (
        datetime.strptime(dt_str_actual, "%Y/%m/%d %H:%M") if dt_str_actual else None
    )
    return AttendanceRecord(
        date=sched.date() if sched else None,
        scheduled_time=sched,
        actual_time=actual,
        type=typ,
        card_number="1",
        source="src",
        status="",
        processed="",
        operation="",
        note="",
    )


class TestPolicy(unittest.TestCase):
    def setUp(self):
        self.rules = Rules()

    def test_is_full_day_absent(self):
        date = datetime.strptime("2025/07/04", "%Y/%m/%d")
        # missing actual times on both records
        wd = WorkDay(
            date=date,
            checkin_record=mk_record("2025/07/04 08:00", None, AttendanceType.CHECKIN),
            checkout_record=mk_record(
                "2025/07/04 17:00", None, AttendanceType.CHECKOUT
            ),
            is_friday=True,
        )
        self.assertTrue(is_full_day_absent(wd))

        # missing checkin record
        wd_missing_in = WorkDay(
            date=date,
            checkin_record=None,
            checkout_record=mk_record(
                "2025/07/04 17:00", "2025/07/04 17:00", AttendanceType.CHECKOUT
            ),
            is_friday=True,
        )
        self.assertTrue(is_full_day_absent(wd_missing_in))

        # missing checkout record
        wd_missing_out = WorkDay(
            date=date,
            checkin_record=mk_record(
                "2025/07/04 08:00", "2025/07/04 08:00", AttendanceType.CHECKIN
            ),
            checkout_record=None,
            is_friday=True,
        )
        self.assertTrue(is_full_day_absent(wd_missing_out))

        # both records present with actual times
        wd_present = WorkDay(
            date=date,
            checkin_record=mk_record(
                "2025/07/04 08:00", "2025/07/04 08:00", AttendanceType.CHECKIN
            ),
            checkout_record=mk_record(
                "2025/07/04 17:00", "2025/07/04 17:00", AttendanceType.CHECKOUT
            ),
            is_friday=True,
        )
        self.assertFalse(is_full_day_absent(wd_present))

    def test_late_across_lunch_deduct(self):
        # checkin at 13:30 vs latest 10:30 -> 180m; cross lunch deduct 60 => 120m
        date = datetime.strptime("2025/07/01", "%Y/%m/%d")
        wd = WorkDay(
            date=date,
            checkin_record=mk_record(
                "2025/07/01 08:00", "2025/07/01 13:30", AttendanceType.CHECKIN
            ),
            checkout_record=mk_record(
                "2025/07/01 17:00", "2025/07/01 22:45", AttendanceType.CHECKOUT
            ),
            is_friday=False,
        )
        minutes, _range, _calc = calculate_late_minutes(wd, self.rules)
        self.assertEqual(minutes, 120)

    def test_overtime_rounding(self):
        # checkin 09:00 => expected out 18:00; actual 20:01 => 121m actual, applicable 120m
        date = datetime.strptime("2025/07/01", "%Y/%m/%d")
        wd = WorkDay(
            date=date,
            checkin_record=mk_record(
                "2025/07/01 09:00", "2025/07/01 09:00", AttendanceType.CHECKIN
            ),
            checkout_record=mk_record(
                "2025/07/01 17:00", "2025/07/01 20:01", AttendanceType.CHECKOUT
            ),
            is_friday=False,
        )
        actual, applicable, _range, _calc = calculate_overtime_minutes(wd, self.rules)
        self.assertEqual(applicable, 120)


if __name__ == "__main__":
    unittest.main()
"""Category: Policy
Purpose: Late calculation branches and overtime applicability thresholds."""

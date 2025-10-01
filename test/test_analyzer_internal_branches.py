import unittest
from datetime import datetime

from attendance_analyzer import (
    AttendanceAnalyzer,
    AttendanceRecord,
    AttendanceType,
    IssueType,
    WorkDay,
)
from lib.policy import Rules


class TestAnalyzerInternalBranches(unittest.TestCase):
    def test__load_previous_forget_punch_usage_early_return(self):
        an = AttendanceAnalyzer()
        # Default: state_manager is None, incremental_mode True -> early return path
        an._load_previous_forget_punch_usage('誰')
        self.assertEqual(dict(an.forget_punch_usage), {})

    def test__parse_attendance_line_none(self):
        an = AttendanceAnalyzer()
        self.assertIsNone(an._parse_attendance_line('invalid'))

    def test__analyze_single_workday_friday_returns_early(self):
        an = AttendanceAnalyzer()
        # Construct a Friday workday (2025-07-04 is Friday)
        date = datetime(2025, 7, 4)
        rec_in = AttendanceRecord(
            date=date, scheduled_time=date.replace(hour=9, minute=0),
            actual_time=date.replace(hour=9, minute=5),
            type=AttendanceType.CHECKIN,
            card_number='1', source='門禁', status='',
            processed='', operation='', note=''
        )
        rec_out = AttendanceRecord(
            date=date, scheduled_time=date.replace(hour=18, minute=0),
            actual_time=date.replace(hour=19, minute=0),
            type=AttendanceType.CHECKOUT,
            card_number='1', source='門禁', status='',
            processed='', operation='', note=''
        )
        wd = WorkDay(date=date, checkin_record=rec_in, checkout_record=rec_out,
                     is_friday=True, is_holiday=False)
        an._analyze_single_workday(wd, Rules())
        # Friday: analyzer suggests WFH (even with attendance records)
        self.assertEqual(len(an.issues), 1)
        self.assertEqual(an.issues[0].type, IssueType.WFH)
        self.assertEqual(an.issues[0].duration_minutes, 9 * 60)

    def test__update_processing_state_guards(self):
        an = AttendanceAnalyzer()
        # Guard 1: missing state/user
        an._update_processing_state()  # no exception, early return

        # Guard 2: has state/user but no complete days
        class DummyState:
            def __init__(self):
                self.state_data = {'users': {}}
            def update_user_state(self, *a, **k):
                raise AssertionError('should not be called')
            def save_state(self):
                raise AssertionError('should not be called')

        an.state_manager = DummyState()
        an.current_user = '測試'
        an._update_processing_state()  # still early return due to no complete days


if __name__ == '__main__':
    unittest.main()
"""Category: Analyzer
Purpose: Cover analyzer internal guards and branches (friday return, state guards)."""

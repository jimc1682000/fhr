import unittest
from datetime import datetime

from attendance_analyzer import AttendanceAnalyzer
from lib.dates import identify_complete_work_days


class TestUnprocessedEarlyReturn(unittest.TestCase):
    def test_get_unprocessed_dates_without_state_returns_all(self):
        an = AttendanceAnalyzer()
        an.incremental_mode = True
        # Two complete days
        days = [
            datetime(2025, 7, 1),
            datetime(2025, 7, 2),
        ]
        out = an._get_unprocessed_dates('任意', days)
        self.assertEqual(out, days)

    def test_get_unprocessed_dates_full_mode_returns_all(self):
        an = AttendanceAnalyzer()
        an.incremental_mode = False
        days = [datetime(2025, 7, 1)]
        out = an._get_unprocessed_dates('任意', days)
        self.assertEqual(out, days)


class TestDatesHelperSkipsInvalid(unittest.TestCase):
    class Obj:
        def __init__(self, date=None, type=None):
            self.date = date
            self.type = type

    def test_identify_complete_skips_none_date(self):
        # One valid complete day + one record with no date should be ignored
        recs = [
            self.Obj(datetime(2025, 7, 1).date(), 'CHECKIN'),
            self.Obj(datetime(2025, 7, 1).date(), 'CHECKOUT'),
            self.Obj(None, 'CHECKIN'),
        ]
        out = identify_complete_work_days(recs)
        self.assertEqual([d.date() for d in out], [datetime(2025, 7, 1).date()])


if __name__ == '__main__':
    unittest.main()
"""Category: State/Dates
Purpose: Analyzer exposure of unprocessed dates and complete-day id."""

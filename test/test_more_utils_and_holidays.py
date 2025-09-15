import json
import os
import unittest
from datetime import datetime
from unittest import mock

from lib import parser
from lib.filename import parse_range_and_user
from lib.grouping import group_daily
from lib.holidays import HolidayService, TaiwanGovOpenDataProvider
from lib.state import AttendanceStateManager


class DummyRec:
    def __init__(self, date=None, type_name='CHECKOUT'):
        self.date = date
        class T:
            name = type_name
        self.type = T()


class DummyResp:
    def __init__(self, payload: dict):
        self._payload = payload
    def read(self):
        return json.dumps(self._payload).encode('utf-8')
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class TestMiscGaps(unittest.TestCase):
    def test_parser_invalid_datetime_and_type(self):
        # parse_datetime_str invalid
        self.assertIsNone(parser.parse_datetime_str('not-a-dt'))
        # parse_line invalid type returns None
        self.assertIsNone(parser.parse_line('2025/07/01 09:00\t2025/07/01 09:00\t打卡\t'))
        # parse_line missing scheduled returns None
        self.assertIsNone(parser.parse_line('\t2025/07/01 09:00\t上班\t'))

    def test_filename_value_error_paths(self):
        # Invalid month causes ValueError path
        self.assertEqual(parse_range_and_user('20251x-姓名-出勤資料.txt'), (None, None, None))
        # Force second segment to parse and then fail month math (13th month)
        self.assertEqual(
            parse_range_and_user('202501-202513-姓名-出勤資料.txt'), (None, None, None)
        )

    def test_grouping_skips_none_date(self):
        out = group_daily([DummyRec(date=None), DummyRec(date=datetime(2025,7,1))])
        self.assertIn(datetime(2025,7,1), out)

    def test_state_getters_for_missing_user(self):
        s = AttendanceStateManager(state_file=':memory:')
        self.assertEqual(s.get_forget_punch_usage('nobody', '2025-07'), 0)
        self.assertEqual(s.get_last_analysis_time('nobody'), '')

    def test_holiday_env_parsing_invalid(self):
        old = dict(os.environ)
        try:
            os.environ['HOLIDAY_API_MAX_RETRIES'] = 'not-int'
            os.environ['HOLIDAY_API_BACKOFF_BASE'] = 'not-float'
            os.environ['HOLIDAY_API_MAX_BACKOFF'] = 'not-float'
            p = TaiwanGovOpenDataProvider()
            # Defaults applied
            self.assertEqual(p.max_retries, 3)
            self.assertEqual(p.base_backoff, 0.5)
            self.assertEqual(p.max_backoff, 8.0)
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_holiday_service_load_years(self):
        # Mock URL open to return empty valid result for non-2025 to force fallback basic
        payload = {'result': {'records': []}}
        with mock.patch('urllib.request.urlopen', return_value=DummyResp(payload)):
            old = dict(os.environ)
            try:
                os.environ['HOLIDAY_API_MAX_RETRIES'] = '0'
                os.environ['HOLIDAY_API_BACKOFF_BASE'] = '0'
                os.environ['HOLIDAY_API_MAX_BACKOFF'] = '0'
                svc = HolidayService()
                out = svc.load_years({2025, 2026})
            finally:
                os.environ.clear()
            os.environ.update(old)
        # Contains at least one known date from 2025 hardcoded provider or 2026 basic
        self.assertTrue(any(d.year in (2025, 2026) for d in out))


if __name__ == '__main__':
    unittest.main()
"""Category: Utils/Holidays
Purpose: Parser/filename edges, grouping, state getters, env parsing and load_years."""

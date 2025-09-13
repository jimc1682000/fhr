import os
import json
import unittest
from datetime import datetime
from unittest import mock
from urllib.error import HTTPError

from lib.holidays import (
    Hardcoded2025Provider,
    BasicFixedProvider,
    TaiwanGovOpenDataProvider,
    HolidayService,
)


class TestHolidaysProviders(unittest.TestCase):
    def setUp(self):
        # Speed up backoff during tests
        self._env = dict(os.environ)
        os.environ['HOLIDAY_API_MAX_RETRIES'] = '2'
        os.environ['HOLIDAY_API_BACKOFF_BASE'] = '0'
        os.environ['HOLIDAY_API_MAX_BACKOFF'] = '0'

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_hardcoded_2025_contains_known_date(self):
        p = Hardcoded2025Provider()
        s = p.load(2025)
        self.assertIn(datetime.strptime('2025/10/10', '%Y/%m/%d').date(), s)
        self.assertEqual(len(p.load(2024)), 0)

    def test_basic_fixed_provider_jan1_and_national_day(self):
        p = BasicFixedProvider()
        s = p.load(2026)
        self.assertIn(datetime.strptime('2026/01/01', '%Y/%m/%d').date(), s)
        self.assertIn(datetime.strptime('2026/10/10', '%Y/%m/%d').date(), s)

    def test_gov_provider_timeout_then_success(self):
        seq = []
        import socket as _socket
        seq.append(_socket.timeout('timed out'))
        payload = {'result': {'records': [{'isHoliday': 1, 'date': '2027-10-10'}]}}

        class DummyResp:
            def read(self):
                return json.dumps(payload).encode('utf-8')
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        seq.append(DummyResp())

        def urlopen_side(url, timeout=10, context=None):
            v = seq.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        p = TaiwanGovOpenDataProvider()
        with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
            out = p.load(2027)
        self.assertIn(datetime.strptime('2027/10/10', '%Y/%m/%d').date(), out)

    def test_gov_provider_non_retryable_403(self):
        class _HTTPError(HTTPError):
            def __init__(self, code):
                super().__init__('http://x', code, 'err', hdrs=None, fp=None)

        def urlopen_side(url, timeout=10, context=None):
            raise _HTTPError(403)

        p = TaiwanGovOpenDataProvider()
        with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
            out = p.load(2028)
        self.assertEqual(len(out), 0)

    def test_service_uses_hardcoded_for_2025(self):
        s = HolidayService()
        out = s.load_year(2025)
        self.assertIn(datetime.strptime('2025/01/01', '%Y/%m/%d').date(), out)

    def test_service_fallbacks_to_basic_when_gov_empty(self):
        s = HolidayService()
        with mock.patch('lib.holidays.TaiwanGovOpenDataProvider.load', return_value=set()):
            out = s.load_year(2029)
        self.assertIn(datetime.strptime('2029/01/01', '%Y/%m/%d').date(), out)


if __name__ == '__main__':
    unittest.main()
"""Category: Holidays/Providers
Purpose: Validate hardcoded/basic providers and service fallbacks."""

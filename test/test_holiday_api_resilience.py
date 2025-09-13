import unittest
from unittest import mock
from datetime import datetime

from attendance_analyzer import AttendanceAnalyzer
from test.test_helpers import DummyResp, temp_env, urlopen_sequence


class TestHolidayApiResilience(unittest.TestCase):
    def test_timeout_then_success(self):
        import socket as _socket
        with temp_env(dict(HOLIDAY_API_MAX_RETRIES='2', HOLIDAY_API_BACKOFF_BASE='0', HOLIDAY_API_MAX_BACKOFF='0')):
            an = AttendanceAnalyzer()
            seq = [
                _socket.timeout('timed out'),
                {'result': {'records': [{'isHoliday': 1, 'date': '2027-10-10'}]}}
            ]
            with mock.patch('urllib.request.urlopen', side_effect=urlopen_sequence(seq)):
                ok = an._try_load_from_gov_api(2027)
        self.assertTrue(ok)
        self.assertIn(datetime.strptime('2027/10/10','%Y/%m/%d').date(), an.holidays)

    def test_http_5xx_then_success(self):
        from urllib.error import HTTPError
        class _HTTPError(HTTPError):
            def __init__(self, code):
                super().__init__('http://x', code, 'err', hdrs=None, fp=None)
        with temp_env(dict(HOLIDAY_API_MAX_RETRIES='2', HOLIDAY_API_BACKOFF_BASE='0', HOLIDAY_API_MAX_BACKOFF='0')):
            an = AttendanceAnalyzer()
            seq = [
                _HTTPError(503),
                {'result': {'records': [{'isHoliday': 1, 'date': '2026-01-01'}]}}
            ]
            with mock.patch('urllib.request.urlopen', side_effect=urlopen_sequence(seq)):
                ok = an._try_load_from_gov_api(2026)
        self.assertTrue(ok)
        self.assertIn(datetime.strptime('2026/01/01','%Y/%m/%d').date(), an.holidays)

    def test_non_retryable_4xx_fails(self):
        from urllib.error import HTTPError
        class _HTTPError(HTTPError):
            def __init__(self, code):
                super().__init__('http://x', code, 'err', hdrs=None, fp=None)
        def urlopen_side(url, timeout=10, context=None):
            raise _HTTPError(403)
        with temp_env(dict(HOLIDAY_API_MAX_RETRIES='1', HOLIDAY_API_BACKOFF_BASE='0', HOLIDAY_API_MAX_BACKOFF='0')):
            an = AttendanceAnalyzer()
            with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
                ok = an._try_load_from_gov_api(2028)
        self.assertFalse(ok)
"""Category: Holidays/API
Purpose: Retry and resilience handling for gov open data provider."""

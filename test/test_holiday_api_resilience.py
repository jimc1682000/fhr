import os
import json
import unittest
from unittest import mock
from datetime import datetime

from attendance_analyzer import AttendanceAnalyzer


class DummyHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload
    def read(self):
        return json.dumps(self._payload).encode('utf-8')
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class TestHolidayApiResilience(unittest.TestCase):
    def setUp(self):
        self._env = dict(os.environ)
        os.environ['HOLIDAY_API_MAX_RETRIES'] = '2'
        os.environ['HOLIDAY_API_BACKOFF_BASE'] = '0'
        os.environ['HOLIDAY_API_MAX_BACKOFF'] = '0'
    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_timeout_then_success(self):
        import socket as _socket
        seq = [
            _socket.timeout('timed out'),
            DummyHTTPResponse({'result': {'records': [
                {'isHoliday': 1, 'date': '2027-10-10'}
            ]}})
        ]
        def urlopen_side(url, timeout=10, context=None):
            v = seq.pop(0)
            if isinstance(v, Exception):
                raise v
            return v
        an = AttendanceAnalyzer()
        with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
            ok = an._try_load_from_gov_api(2027)
        self.assertTrue(ok)
        self.assertIn(datetime.strptime('2027/10/10','%Y/%m/%d').date(), an.holidays)

    def test_http_5xx_then_success(self):
        from urllib.error import HTTPError
        class _HTTPError(HTTPError):
            def __init__(self, code):
                super().__init__('http://x', code, 'err', hdrs=None, fp=None)
        seq = [
            _HTTPError(503),
            DummyHTTPResponse({'result': {'records': [
                {'isHoliday': 1, 'date': '2026-01-01'}
            ]}})
        ]
        def urlopen_side(url, timeout=10, context=None):
            v = seq.pop(0)
            if isinstance(v, Exception):
                raise v
            return v
        an = AttendanceAnalyzer()
        with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
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
        an = AttendanceAnalyzer()
        with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
            ok = an._try_load_from_gov_api(2028)
        self.assertFalse(ok)

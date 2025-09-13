import unittest
from datetime import datetime
from unittest import mock

from attendance_analyzer import AttendanceAnalyzer
from test.test_helpers import DummyResp, temp_env, urlopen_sequence


class TestHolidayApiRetry(unittest.TestCase):
    def test_success_after_retries(self):
        with temp_env(HOLIDAY_API_MAX_RETRIES="3", HOLIDAY_API_BACKOFF_BASE="0", HOLIDAY_API_MAX_BACKOFF="0"):
            analyzer = AttendanceAnalyzer()
            seq = [
                Exception("temporary failure"),
                Exception("temporary failure"),
                {
                    "result": {
                        "records": [
                            {"isHoliday": 1, "date": "2026-01-01"},
                            {"isHoliday": 0, "date": "2026-01-02"},
                        ]
                    }
                }
            ]
            with mock.patch("urllib.request.urlopen", side_effect=urlopen_sequence(seq)):
                ok = analyzer._try_load_from_gov_api(2026)

        self.assertTrue(ok)
        self.assertIn(datetime.strptime("2026/01/01", "%Y/%m/%d").date(), analyzer.holidays)

    def test_retry_exhaustion_then_fallback(self):
        with temp_env(HOLIDAY_API_MAX_RETRIES="2", HOLIDAY_API_BACKOFF_BASE="0", HOLIDAY_API_MAX_BACKOFF="0"):
            analyzer = AttendanceAnalyzer()
            with mock.patch("urllib.request.urlopen", side_effect=Exception("network down")):
                ok = analyzer._try_load_from_gov_api(2027)

        self.assertFalse(ok)

    def test_timeout_then_success(self):
        import socket as _socket
        with temp_env(HOLIDAY_API_MAX_RETRIES="2", HOLIDAY_API_BACKOFF_BASE="0", HOLIDAY_API_MAX_BACKOFF="0"):
            analyzer = AttendanceAnalyzer()
            seq = [
                _socket.timeout("timed out"),
                {"result": {"records": [{"isHoliday": 1, "date": "2027-10-10"}]}}
            ]
            with mock.patch("urllib.request.urlopen", side_effect=urlopen_sequence(seq)):
                ok = analyzer._try_load_from_gov_api(2027)
        self.assertTrue(ok)
"""Category: Holidays/API
Purpose: Analyzer facade retry path via _try_load_from_gov_api."""

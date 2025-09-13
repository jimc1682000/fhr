import os
import json
import unittest
from datetime import datetime
from unittest import mock

from attendance_analyzer import AttendanceAnalyzer


class DummyHTTPResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status = status

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestHolidayApiRetry(unittest.TestCase):
    def setUp(self):
        self._orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._orig_env)

    def test_success_after_retries(self):
        os.environ["HOLIDAY_API_MAX_RETRIES"] = "3"
        calls = {"count": 0}

        def flaky_urlopen(url, timeout=10, context=None):
            calls["count"] += 1
            if calls["count"] < 3:
                raise Exception("temporary failure")
            payload = {
                "result": {
                    "records": [
                        {"isHoliday": 1, "date": "2026-01-01"},
                        {"isHoliday": 0, "date": "2026-01-02"},
                    ]
                }
            }
            return DummyHTTPResponse(payload)

        analyzer = AttendanceAnalyzer()

        with mock.patch("urllib.request.urlopen", side_effect=flaky_urlopen):
            ok = analyzer._try_load_from_gov_api(2026)

        self.assertTrue(ok)
        self.assertGreaterEqual(calls["count"], 3)
        self.assertIn(datetime.strptime("2026/01/01", "%Y/%m/%d").date(), analyzer.holidays)

    def test_retry_exhaustion_then_fallback(self):
        os.environ["HOLIDAY_API_MAX_RETRIES"] = "2"

        calls = {"count": 0}

        def always_fail(url, timeout=10, context=None):
            calls["count"] += 1
            raise Exception("network down")

        analyzer = AttendanceAnalyzer()

        with mock.patch("urllib.request.urlopen", side_effect=always_fail):
            ok = analyzer._try_load_from_gov_api(2027)

        self.assertFalse(ok)
        self.assertGreaterEqual(calls["count"], 1)

    def test_timeout_then_success(self):
        os.environ["HOLIDAY_API_MAX_RETRIES"] = "2"
        import socket as _socket

        seq = [
            _socket.timeout("timed out"),
            DummyHTTPResponse({
                "result": {"records": [{"isHoliday": 1, "date": "2027-10-10"}]}
            })
        ]

        def seq_urlopen(url, timeout=10, context=None):
            v = seq.pop(0)
            if isinstance(v, Exception):
                raise v
            return v

        analyzer = AttendanceAnalyzer()
        with mock.patch("urllib.request.urlopen", side_effect=seq_urlopen):
            ok = analyzer._try_load_from_gov_api(2027)
        self.assertTrue(ok)


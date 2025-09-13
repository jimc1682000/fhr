import unittest
from datetime import datetime
from unittest import mock

from lib.holidays import TaiwanGovOpenDataProvider
from test.test_helpers import DummyResp, temp_env


"""Use shared DummyResp from test_helpers to speed up imports and reuse."""


class FakeParse:
    def __init__(self, scheme: str):
        self.scheme = scheme


class TestHolidaysMore(unittest.TestCase):

    def test_invalid_date_record_is_skipped(self):
        payload = {
            "result": {
                "records": [
                    {"isHoliday": 1, "date": "bad-date"},
                    {"isHoliday": 1, "date": "2026-10-10"},
                    {"isHoliday": 0, "date": "2026-01-02"},
                ]
            }
        }
        with temp_env(
            {
                "HOLIDAY_API_MAX_RETRIES": "1",
                "HOLIDAY_API_BACKOFF_BASE": "0",
                "HOLIDAY_API_MAX_BACKOFF": "0",
            }
        ):
            p = TaiwanGovOpenDataProvider()
            with mock.patch("urllib.request.urlopen", return_value=DummyResp(payload)):
                with self.assertLogs("lib.holidays", level="WARNING") as cm:
                    out = p.load(2026)
        self.assertIn(datetime.strptime("2026/10/10", "%Y/%m/%d").date(), out)
        logs = "\n".join(cm.output)
        self.assertIn("跳過無效的日期格式", logs)

    def test_unsupported_scheme_returns_empty(self):
        with temp_env(
            {
                "HOLIDAY_API_MAX_RETRIES": "1",
                "HOLIDAY_API_BACKOFF_BASE": "0",
                "HOLIDAY_API_MAX_BACKOFF": "0",
            }
        ):
            p = TaiwanGovOpenDataProvider()
            with mock.patch("lib.holidays.urlparse", return_value=FakeParse("file")):
                with self.assertLogs("lib.holidays", level="WARNING") as cm:
                    out = p.load(2026)
        self.assertEqual(out, set())
        self.assertIn("不支援的 URL scheme", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
"""Category: Holidays/API
Purpose: Invalid record filtering and scheme rejection paths."""

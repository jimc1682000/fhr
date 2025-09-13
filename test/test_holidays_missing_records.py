import unittest
from unittest import mock

from lib.holidays import TaiwanGovOpenDataProvider
from test.test_helpers import DummyResp, temp_env


"""Use shared DummyResp from test_helpers to avoid local duplication."""


class TestHolidaysMissingRecords(unittest.TestCase):
    def test_missing_result_or_records_returns_empty(self):
        # Speed up tests by removing backoff and limiting retries
        with temp_env({'HOLIDAY_API_MAX_RETRIES': '1', 'HOLIDAY_API_BACKOFF_BASE': '0', 'HOLIDAY_API_MAX_BACKOFF': '0'}):
            # First attempt: no 'result' key
            payload1 = {}
            # Second attempt: 'result' present but no 'records'
            payload2 = {'result': {}}
            seq = [DummyResp(payload1), DummyResp(payload2)]
            def urlopen_side(url, timeout=10, context=None):
                return seq.pop(0)

            p = TaiwanGovOpenDataProvider()
            with mock.patch('urllib.request.urlopen', side_effect=urlopen_side):
                with self.assertLogs('lib.holidays', level='INFO') as cm:
                    out = p.load(2026)
        # Should gracefully return empty set after retries exhausted
        self.assertEqual(out, set())
        logs = "\n".join(cm.output)
        self.assertIn('資訊: 嘗試載入 2026 年假日 (第 1/1 次)...', logs)
        self.assertIn('錯誤: 嘗試 1 次後仍無法載入 2026 年假日資料。回退到基本假日。', logs)


if __name__ == '__main__':
    unittest.main()
"""Category: Holidays/API
Purpose: Missing 'result' / 'records' handling with retry exhaustion."""

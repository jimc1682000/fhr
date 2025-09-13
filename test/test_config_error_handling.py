import os
import tempfile
import unittest
from unittest import mock

from attendance_analyzer import AttendanceAnalyzer


class TestConfigErrorHandling(unittest.TestCase):
    def test_missing_config_logs_info_and_uses_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Point analyzer to a non-existent config file
            cfg = os.path.join(tmp, "no-such-config.json")
            with self.assertLogs(level="INFO") as cm:
                an = AttendanceAnalyzer(config_path=cfg)
            logs = "\n".join(cm.output)
            self.assertIn("找不到設定檔", logs)
            # Verify a known default remains in effect
            self.assertEqual(an.config.latest_checkin, "10:30")

    def test_invalid_json_logs_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = os.path.join(tmp, "bad.json")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("{ invalid json ")  # malformed
            with self.assertLogs(level="WARNING") as cm:
                an = AttendanceAnalyzer(config_path=cfg)
            logs = "\n".join(cm.output)
            self.assertIn("無法讀取設定檔", logs)
            # Defaults still intact
            self.assertEqual(an.config.min_overtime_minutes, 60)


if __name__ == "__main__":
    unittest.main()
"""Category: Config
Purpose: Config file overrides and error handling (missing/invalid JSON)."""

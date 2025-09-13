import os
import json
import tempfile
import unittest
from unittest import mock

from lib.state import AttendanceStateManager


class TestStateEdgeCases(unittest.TestCase):
    def test_load_state_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attendance_state.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ this is not json")
            with self.assertLogs("lib.state", level="WARNING") as cm:
                m = AttendanceStateManager(path)
            self.assertEqual(m.state_data, {"users": {}})
            logs = "\n".join(cm.output)
            self.assertIn("無法讀取狀態檔案", logs)
            self.assertIn("將使用空白狀態", logs)

    def test_save_state_write_failure_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attendance_state.json")
            m = AttendanceStateManager(path)
            m.state_data = {"users": {}}
            with mock.patch("builtins.open", side_effect=OSError("disk full")):
                with self.assertLogs("lib.state", level="WARNING") as cm:
                    m.save_state()
            self.assertIn("無法儲存狀態檔案", "\n".join(cm.output))

    def test_update_user_state_replace_and_merge_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "attendance_state.json")
            m = AttendanceStateManager(path)
            r1 = {
                "start_date": "2025-07-01",
                "end_date": "2025-07-31",
                "source_file": "202507-小明-出勤資料.txt",
                "last_analysis_time": "2025-09-13T10:00:00",
            }
            r2 = dict(
                r1, end_date="2025-08-31", last_analysis_time="2025-09-13T11:00:00"
            )

            m.update_user_state("小明", r1, {"2025-07": 1})
            self.assertEqual(len(m.get_user_processed_ranges("小明")), 1)
            self.assertEqual(m.get_forget_punch_usage("小明", "2025-07"), 1)

            # same source_file should replace, not append
            m.update_user_state("小明", r2, {"2025-08": 2})
            ranges = m.get_user_processed_ranges("小明")
            self.assertEqual(len(ranges), 1)
            self.assertEqual(ranges[0]["end_date"], "2025-08-31")
            self.assertEqual(m.get_forget_punch_usage("小明", "2025-08"), 2)


if __name__ == "__main__":
    unittest.main()
"""Category: State
Purpose: Corrupt state file, save failure warnings, and merge logic."""

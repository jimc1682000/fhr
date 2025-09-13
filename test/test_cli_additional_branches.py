import os
import json
import tempfile
import unittest
from unittest import mock

import attendance_analyzer as mod


class TestCliAdditionalBranches(unittest.TestCase):
    def test_reset_state_user_not_present_logs_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # state file with a different user
            state_path = os.path.join(tmpdir, "attendance_state.json")
            state = {
                "users": {
                    "別人": {"processed_date_ranges": [], "forget_punch_usage": {}}
                }
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f)

            file_path = os.path.join(tmpdir, "202508-阿明-出勤資料.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(
                    "應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n"
                )

            cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                argv = ["attendance_analyzer.py", file_path, "--reset-state"]
                with self.assertLogs(level="INFO") as cm:
                    with mock.patch("sys.argv", argv):
                        mod.main()
                logs = "\n".join(cm.output)
                self.assertIn("沒有現有狀態需要清除", logs)
            finally:
                os.chdir(cwd)

    def test_runtime_exception_in_cli_exits(self):
        # Force an exception during CLI run to hit error handler
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "sample-attendance-data.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(
                    "應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n"
                )
            argv = ["attendance_analyzer.py", file_path, "csv"]
            # Patch the analyzer method that CLI calls to raise
            with mock.patch(
                "attendance_analyzer.AttendanceAnalyzer.parse_attendance_file",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertLogs(level="ERROR") as cm:
                    with self.assertRaises(SystemExit) as se:
                        with mock.patch("sys.argv", argv):
                            mod.main()
                self.assertEqual(se.exception.code, 1)
                self.assertIn("錯誤: boom", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
"""Category: CLI
Purpose: Exercise CLI side branches (reset-state no user, runtime exceptions)."""

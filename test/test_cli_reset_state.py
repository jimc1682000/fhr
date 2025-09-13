import os
import json
import tempfile
import unittest
from unittest import mock

import attendance_analyzer as mod


class TestCliResetState(unittest.TestCase):
    def test_reset_state_logs_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, 'attendance_state.json')
            user_name = '阿明'
            state = {"users": {user_name: {"processed_date_ranges": [], "forget_punch_usage": {}}}}
            with open(state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f)

            file_path = os.path.join(tmpdir, '202508-阿明-出勤資料.txt')
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n")

            cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                argv = ['attendance_analyzer.py', file_path, '--reset-state']
                with self.assertLogs(level='INFO') as cm:
                    with mock.patch('sys.argv', argv):
                        mod.main()
                logs = "\n".join(cm.output)
                self.assertIn("狀態檔 'attendance_state.json' 已清除使用者", logs)
                self.assertIn(user_name, logs)
                self.assertIn("@ ", logs)
            finally:
                os.chdir(cwd)


if __name__ == '__main__':
    unittest.main()

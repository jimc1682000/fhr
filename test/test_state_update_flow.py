import os
import tempfile
import unittest

from attendance_analyzer import AttendanceAnalyzer, AttendanceType


class DummyState:
    def __init__(self):
        self.saved = False
        self.updated = False
        self.state_data = {"users": {}}

    def get_user_processed_ranges(self, user):
        return []

    def get_last_analysis_time(self, user):
        return ""

    def update_user_state(self, user, range_info, forget_punch_usage):
        self.updated = True
        self.state_data.setdefault('users', {}).setdefault(user, {})['last'] = range_info

    def save_state(self):
        self.saved = True

    def detect_date_overlap(self, user, start, end):
        return []


class TestStateUpdateFlow(unittest.TestCase):
    def _write_minimal_file(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n')
            # 2025/07/01 checkin and checkout to form a complete day
            f.write('2025/07/01 09:10\t2025/07/01 09:10\t上班\t123\t門禁\t\t\t\t\n')
            f.write('2025/07/01 18:20\t2025/07/01 18:20\t下班\t123\t門禁\t\t\t\t\n')

    def test_update_processing_state_is_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '202507-阿明-出勤資料.txt')
            self._write_minimal_file(path)

            an = AttendanceAnalyzer()
            an.parse_attendance_file(path, incremental=True)
            an.group_records_by_day()

            # Replace real state manager with dummy to observe updates
            dummy = DummyState()
            an.state_manager = dummy

            an.analyze_attendance()

            self.assertTrue(dummy.updated)
            self.assertTrue(dummy.saved)


if __name__ == '__main__':
    unittest.main()
"""Category: State
Purpose: Ensure update/save is invoked after analysis in incremental mode."""

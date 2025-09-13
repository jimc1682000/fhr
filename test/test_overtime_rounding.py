import tempfile
import os
import unittest
from attendance_analyzer import AttendanceAnalyzer, IssueType


def run_case(checkin, checkout):
    text = (
        "應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n"
        f"2025/07/01 08:00\t{checkin}\t上班\t1\t刷卡匯入\t\t\t\t\n"
        f"2025/07/01 17:00\t{checkout}\t下班\t1\t刷卡匯入\t\t\t\t\n"
    )
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(text)
        path = f.name
    try:
        an = AttendanceAnalyzer()
        an.parse_attendance_file(path)
        an.group_records_by_day()
        an.analyze_attendance()
        over = [i for i in an.issues if i.type == IssueType.OVERTIME]
        return over[0].duration_minutes if over else 0
    finally:
        os.unlink(path)


class TestOvertimeRounding(unittest.TestCase):
    def test_just_under_90_minutes(self):
        # Actual overtime 89m => eligible 60m (hourly increments from 60)
        # Checkin 09:00, expected checkout 18:00, actual 19:29 => 89m
        self.assertEqual(run_case("2025/07/01 09:00", "2025/07/01 19:29"), 60)

    def test_just_under_120(self):
        # Actual 119m => eligible 60m
        self.assertEqual(run_case("2025/07/01 09:00", "2025/07/01 19:59"), 60)

    def test_over_120(self):
        # Actual 121m => eligible 120m
        self.assertEqual(run_case("2025/07/01 09:00", "2025/07/01 20:01"), 120)


if __name__ == '__main__':
    unittest.main()


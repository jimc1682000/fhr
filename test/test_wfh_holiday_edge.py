import unittest
import tempfile
import os
from attendance_analyzer import AttendanceAnalyzer, IssueType


class TestWfhHolidayEdge(unittest.TestCase):
    def _run_analyze(self, text: str):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(text)
            path = f.name
        try:
            an = AttendanceAnalyzer()
            an.parse_attendance_file(path)
            an.group_records_by_day()
            an.analyze_attendance()
            return an
        finally:
            os.unlink(path)

    def test_friday_national_day_no_wfh(self):
        # 2025/10/10 是國慶日且為週五，應不產生WFH建議
        data = """應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註
2025/10/10 08:00\t\t上班\t\t\t曠職\t已處理\t\t
2025/10/10 17:00\t\t下班\t\t\t曠職\t已處理\t\t"""
        an = self._run_analyze(data)
        types = {i.type for i in an.issues}
        self.assertNotIn(IssueType.WFH, types)
        self.assertEqual(len(an.issues), 0, "國定假日不應產生任何請假建議")

    def test_normal_friday_wfh(self):
        # 一般週五曠職 → 產生WFH建議
        data = """應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註
2025/07/04 08:00\t\t上班\t\t\t曠職\t已處理\t\t
2025/07/04 17:00\t\t下班\t\t\t曠職\t已處理\t\t"""
        an = self._run_analyze(data)
        types = [i.type for i in an.issues]
        self.assertIn(IssueType.WFH, types)


if __name__ == "__main__":
    unittest.main()
"""Category: Policy/Holidays
Purpose: WFH suggestion behavior on holidays vs normal Fridays."""

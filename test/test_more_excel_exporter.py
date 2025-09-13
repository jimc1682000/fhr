import os
import tempfile
import unittest
from datetime import datetime

from lib import excel_exporter as xls
from attendance_analyzer import Issue, IssueType


class TestExcelExporterMore(unittest.TestCase):
    def test_status_row_and_type_colors(self):
        wb, ws, header_font, header_fill, border, align = xls.init_workbook()
        headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式', '狀態']
        xls.write_headers(ws, headers, header_font, header_fill, border, align)

        # Write status row and assert returned next row index
        next_row = xls.write_status_row(ws, '2025/07/31', 22, '2025-09-13T12:00:00', border, align)
        self.assertEqual(next_row, 3)
        self.assertEqual(ws['A2'].value, '2025/07/31')
        self.assertEqual(ws['B2'].value, '狀態資訊')
        self.assertEqual(ws['G2'].value, '系統狀態')

        # Prepare issues to hit all color branches
        issues = [
            Issue(datetime(2025, 7, 1), IssueType.OVERTIME, 120, '加班', '18:00~20:00', 'calc', True),
            Issue(datetime(2025, 7, 2), IssueType.WFH, 540, 'WFH', '', '', False),
            Issue(datetime(2025, 7, 3), IssueType.FORGET_PUNCH, 30, '忘刷卡', '', '', True),
        ]
        xls.write_issue_rows(ws, issues, start_row=next_row, incremental_mode=True, border=border, alignment=align)

        # Sanity check values written
        self.assertEqual(ws['B3'].value, '加班')
        self.assertEqual(ws['B4'].value, 'WFH假')
        self.assertEqual(ws['B5'].value, '忘刷卡')
        self.assertEqual(ws['G3'].value, '[NEW] 本次新發現')
        self.assertEqual(ws['G4'].value, '已存在')

        # Save to ensure no errors in save_workbook path
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            xls.save_workbook(wb, tmp.name)
            saved = tmp.name
        self.assertTrue(os.path.exists(saved))
        os.remove(saved)


if __name__ == '__main__':
    unittest.main()
"""Category: Export/Excel
Purpose: Status row rendering, cell styles, and save routine."""

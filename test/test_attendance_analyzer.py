import os
import tempfile
import unittest
from datetime import datetime

from attendance_analyzer import Issue, IssueType
from lib import excel_exporter


class TestExcelExporter(unittest.TestCase):
    def test_write_and_save_workbook(self) -> None:
        wb, ws, header_font, header_fill, border, align = excel_exporter.init_workbook()
        headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式', '狀態']
        excel_exporter.write_headers(ws, headers, header_font, header_fill, border, align)
        issue = Issue(
            date=datetime(2025, 9, 1),
            type=IssueType.LATE,
            duration_minutes=10,
            description='遲到10分鐘',
            time_range='09:10-09:20',
            calculation='09:10-09:00',
            is_new=True,
        )
        excel_exporter.write_issue_rows(ws, [issue], 2, True, border, align)
        excel_exporter.set_column_widths(ws, True)
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            excel_exporter.save_workbook(wb, tmp.name)
            saved_path = tmp.name
        from openpyxl import load_workbook
        wb2 = load_workbook(saved_path)
        ws2 = wb2.active
        self.assertEqual(ws2['A1'].value, '日期')
        self.assertEqual(ws2['A2'].value, '2025/09/01')
        self.assertEqual(ws2['B2'].value, '遲到')
        self.assertEqual(ws2['G2'].value, '[NEW] 本次新發現')
        os.remove(saved_path)


if __name__ == '__main__':
    unittest.main()

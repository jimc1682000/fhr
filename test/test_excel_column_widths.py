import unittest
from lib import excel_exporter


class TestExcelColumnWidths(unittest.TestCase):
    def test_widths_incremental_true(self):
        wb, ws, *_ = excel_exporter.init_workbook()
        excel_exporter.set_column_widths(ws, True)
        self.assertEqual(ws.column_dimensions['D'].width, 30)
        self.assertEqual(ws.column_dimensions['F'].width, 40)
        self.assertEqual(ws.column_dimensions['G'].width, 24)

    def test_widths_incremental_false(self):
        wb, ws, *_ = excel_exporter.init_workbook()
        excel_exporter.set_column_widths(ws, False)
        self.assertEqual(ws.column_dimensions['D'].width, 30)
        self.assertEqual(ws.column_dimensions['F'].width, 35)
        self.assertFalse('G' in ws.column_dimensions and ws.column_dimensions['G'].width)


if __name__ == '__main__':
    unittest.main()
"""Category: Export/Excel
Purpose: Column width rules for incremental and full modes."""

import os
import tempfile
import unittest
from unittest import mock

from attendance_analyzer import AttendanceAnalyzer


class TestExportExcelFallback(unittest.TestCase):
    def test_import_error_falls_back_to_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(os.getcwd(), 'sample-attendance-data.txt')
            path = os.path.join(tmp, 'sample-attendance-data.txt')
            with open(src, 'r', encoding='utf-8') as fsrc, open(path, 'w', encoding='utf-8') as fdst:
                fdst.write(fsrc.read())

            an = AttendanceAnalyzer()
            an.parse_attendance_file(path, incremental=False)
            an.group_records_by_day()
            an.analyze_attendance()

            # Patch import to raise ImportError when importing lib.excel_exporter
            import builtins as _builtins
            real_import = _builtins.__import__

            def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'lib' and ('excel_exporter' in fromlist):
                    raise ImportError('no openpyxl')
                return real_import(name, globals, locals, fromlist, level)

            xlsx = path.replace('.txt', '_analysis.xlsx')
            csv = path.replace('.txt', '_analysis.csv')
            with mock.patch('builtins.__import__', side_effect=fake_import):
                with self.assertLogs(level='WARNING') as cm:
                    an.export_excel(xlsx)
            self.assertTrue(os.path.exists(csv))
            self.assertIn('未安裝 openpyxl，回退使用CSV格式', "\n".join(cm.output))


if __name__ == '__main__':
    unittest.main()
"""Category: Export/Excel
Purpose: Fallback to CSV when openpyxl is unavailable."""

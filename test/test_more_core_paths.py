import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from attendance_analyzer import AttendanceAnalyzer


class TestAnalyzerAdditionalPaths(unittest.TestCase):
    def test_config_overrides(self):
        # Write a temporary config that overrides one value
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = os.path.join(tmp, 'config.json')
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump({"min_overtime_minutes": 30}, f)
            an = AttendanceAnalyzer(config_path=cfg_path)
            self.assertEqual(an.config.min_overtime_minutes, 30)

    def test_parse_file_blank_and_exception_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, '202507-小王-出勤資料.txt')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('頭\t欄\t位\n')
                f.write('\n')  # blank triggers continue
                f.write('x\ty\t上班\n')  # will be fed to patched parser

            an = AttendanceAnalyzer()

            # Patch internal line parser to raise, to hit except branch
            with patch.object(
                AttendanceAnalyzer, '_parse_attendance_line', side_effect=ValueError('bad')
            ):
                with self.assertLogs(level='WARNING') as cm:
                    an.parse_attendance_file(path, incremental=False)
            self.assertIn('解析失敗', "\n".join(cm.output))

    def test_export_report_triggers_backup_and_excel_issue_rows(self):
        # Craft data that yields issues and ensure backup log is printed
        text = (
            '應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n'
            '2025/07/01 09:00\t2025/07/01 11:00\t上班\t1\t刷卡匯入\t\t\t\t\n'  # late
            '2025/07/01 18:00\t2025/07/01 20:15\t下班\t1\t刷卡匯入\t\t\t\t\n'  # overtime
        )
        with tempfile.TemporaryDirectory() as tmp:
            in_path = os.path.join(tmp, '202507-王小明-出勤資料.txt')
            with open(in_path, 'w', encoding='utf-8') as f:
                f.write(text)

            an = AttendanceAnalyzer()
            an.parse_attendance_file(in_path, incremental=False)
            an.group_records_by_day()
            an.analyze_attendance()

            out_xlsx = os.path.join(tmp, 'out.xlsx')
            # Pre-create to force backup
            open(out_xlsx, 'wb').close()
            with self.assertLogs(level='INFO') as cm:
                an.export_report(out_xlsx, 'excel')
            logs = "\n".join(cm.output)
            self.assertIn('備份現有檔案', logs)
            self.assertTrue(os.path.exists(out_xlsx))

    def test_openpyxl_import_error_branch(self):
        # Ensure the inner openpyxl import error fallback in export_excel is covered
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(os.getcwd(), 'sample-attendance-data.txt')
            path = os.path.join(tmp, 'sample-attendance-data.txt')
            with open(src, encoding='utf-8') as fsrc, open(path, 'w', encoding='utf-8') as fdst:
                fdst.write(fsrc.read())

            an = AttendanceAnalyzer()
            an.parse_attendance_file(path, incremental=False)
            an.group_records_by_day()
            an.analyze_attendance()

            # Patch import to raise ImportError when importing openpyxl
            import builtins as _builtins
            real_import = _builtins.__import__

            def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == 'openpyxl':
                    raise ImportError('no openpyxl installed')
                return real_import(name, globals, locals, fromlist, level)

            xlsx = path.replace('.txt', '_analysis.xlsx')
            csv = path.replace('.txt', '_analysis.csv')
            with patch('builtins.__import__', side_effect=fake_import):
                with self.assertLogs(level='WARNING') as cm:
                    an.export_excel(xlsx)
            self.assertTrue(os.path.exists(csv))
            self.assertIn('未安裝 openpyxl，回退使用CSV格式', "\n".join(cm.output))

    def test_compute_incremental_status_row_returns_none_when_unprocessed(self):
        # Create one complete day
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, '202507-王小明-出勤資料.txt')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('h\th\th\n')
                f.write('2025/07/01 09:00\t2025/07/01 09:00\t上班\t\n')
                f.write('2025/07/01 18:00\t2025/07/01 18:00\t下班\t\n')

            class DummyState:
                def __init__(self):
                    self.state_data = {"users": {}}
                def get_user_processed_ranges(self, user):
                    return []
                def get_last_analysis_time(self, user):
                    return ''

            an = AttendanceAnalyzer()
            an.parse_attendance_file(p, incremental=True)
            an.group_records_by_day()

            # Force unprocessed dates to be non-empty
            with patch.object(
                AttendanceAnalyzer, '_get_unprocessed_dates', return_value=[datetime(2025, 7, 1)]
            ):
                an.state_manager = DummyState()
                an.current_user = '王小明'
                self.assertIsNone(an._compute_incremental_status_row())

    def test_load_taiwan_holidays_default_year(self):
        an = AttendanceAnalyzer()
        # No records; direct call to use default years branch
        an._load_taiwan_holidays()
        self.assertTrue(any(d.strftime('%Y/%m/%d') == '2025/10/10' for d in an.holidays))


if __name__ == '__main__':
    unittest.main()
"""Category: Analyzer/Core
Purpose: Config overrides, parse errors, backup log, import fallback, and status-row logic."""

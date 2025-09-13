import unittest
from types import SimpleNamespace
from datetime import datetime

from lib import report


class TestReportBuilder(unittest.TestCase):
    def test_incremental_preview_overflow(self):
        dates = [f"2025/07/{i:02d}" for i in range(1, 8)]
        lines = report.build_incremental_lines('王小明', 20, 7, dates)
        text = "\n".join(lines)
        self.assertIn('等 7 天', text)

    def test_issue_section_empty(self):
        self.assertEqual(report.build_issue_section('## 節', 'x', []), [])

    def test_issue_section_hide_calc(self):
        issues = [
            SimpleNamespace(
                date=datetime(2025, 7, 1), description='遲到2分鐘', time_range='10:30~10:32', calculation='…'
            )
        ]
        lines = report.build_issue_section('## 測試', '😅', issues, show_calc=False)
        text = "\n".join(lines)
        self.assertIn('遲到2分鐘', text)
        self.assertIn('10:30~10:32', text)
        self.assertNotIn('🧮', text)


if __name__ == '__main__':
    unittest.main()
"""Category: Report
Purpose: Incremental section preview and issue sections rendering."""

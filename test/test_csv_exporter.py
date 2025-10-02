import csv
import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace

from lib import csv_exporter


def make_issue(
    date_str: str, typ_value: str, minutes: int, desc: str, rng: str, calc: str, is_new=True
):
    return SimpleNamespace(
        date=datetime.strptime(date_str, "%Y/%m/%d"),
        type=SimpleNamespace(value=typ_value),
        duration_minutes=minutes,
        description=desc,
        time_range=rng,
        calculation=calc,
        is_new=is_new,
    )


class TestCsvExporter(unittest.TestCase):
    def test_write_with_status_row(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
            path = tmp.name
        try:
            issues = []
            csv_exporter.save_csv(path, issues, True, ("2025/07/31", 22, "2025-09-13T10:00:00"))
            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual(rows[1][1], '狀態資訊')
            self.assertIn('上次分析時間', rows[1][3])
        finally:
            os.unlink(path)

    def test_write_issue_rows(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
            path = tmp.name
        try:
            issues = [
                make_issue('2025/09/01', '遲到', 10, '遲到10分鐘', '10:30-10:40', 'calc', True)
            ]
            csv_exporter.save_csv(path, issues, True, None)
            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertEqual(rows[1][0], '2025/09/01')
            self.assertEqual(rows[1][-1], '[NEW] 本次新發現')
        finally:
            os.unlink(path)

    def test_merge_replaces_existing_issue(self):
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
            path = tmp.name
        try:
            first_issue = [
                make_issue('2025/09/01', '遲到', 10, '遲到10分鐘', '10:30-10:40', 'calc', True)
            ]
            csv_exporter.save_csv(path, first_issue, True, None)

            updated_issue = [
                make_issue('2025/09/01', '遲到', 15, '遲到15分鐘', '10:30-10:45', 'calc', False)
            ]
            csv_exporter.save_csv(path, updated_issue, True, None, merge=True)

            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][2], '15')  # minutes updated
            self.assertEqual(rows[1][-1], '已存在')
        finally:
            os.unlink(path)

    def test_merge_preserves_existing_issues(self):
        """Test that merge keeps existing issues not in the new set"""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False) as tmp:
            path = tmp.name
        try:
            # First save with two issues
            first_issues = [
                make_issue('2025/09/01', '遲到', 10, '遲到10分鐘', '10:30-10:40', 'calc1', True),
                make_issue('2025/09/02', '加班', 60, '加班60分鐘', '18:00-19:00', 'calc2', True),
            ]
            csv_exporter.save_csv(path, first_issues, True, None)

            # Then merge with one new issue
            new_issues = [
                make_issue('2025/09/03', 'WFH', 540, 'WFH 9小時', '09:00-18:00', 'calc3', True)
            ]
            csv_exporter.save_csv(path, new_issues, True, None, merge=True)

            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))

            # Should have header + 3 issues
            self.assertEqual(len(rows), 4)
            dates = {row[0] for row in rows[1:]}
            self.assertEqual(dates, {'2025/09/01', '2025/09/02', '2025/09/03'})
        finally:
            os.unlink(path)

    def test_merge_handles_nonexistent_file(self):
        """Test that merge=True works when file doesn't exist yet"""
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=True) as tmp:
            path = tmp.name
        # File is now deleted
        try:
            issues = [
                make_issue('2025/09/01', '遲到', 10, '遲到10分鐘', '10:30-10:40', 'calc', True)
            ]
            csv_exporter.save_csv(path, issues, True, None, merge=True)

            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))

            self.assertEqual(len(rows), 2)  # header + 1 issue
            self.assertEqual(rows[1][0], '2025/09/01')
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == '__main__':
    unittest.main()
"""Category: Export/CSV
Purpose: CSV headers, status row, and issue rows with incremental flag."""

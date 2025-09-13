import csv
import os
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace

from lib import csv_exporter


def make_issue(date_str: str, typ_value: str, minutes: int, desc: str, rng: str, calc: str, is_new=True):
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
            issues = [make_issue('2025/09/01', '遲到', 10, '遲到10分鐘', '10:30-10:40', 'calc', True)]
            csv_exporter.save_csv(path, issues, True, None)
            with open(path, encoding='utf-8-sig') as f:
                rows = list(csv.reader(f, delimiter=';'))
            self.assertEqual(rows[1][0], '2025/09/01')
            self.assertEqual(rows[1][-1], '[NEW] 本次新發現')
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()


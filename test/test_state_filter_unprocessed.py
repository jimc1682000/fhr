import unittest
from datetime import datetime

from lib.state import filter_unprocessed_dates


class TestFilterUnprocessed(unittest.TestCase):
    def _d(self, y, m, d):
        return datetime(y, m, d)

    def test_empty_ranges_returns_all(self):
        days = [self._d(2025, 7, i) for i in (1, 2, 3)]
        out = filter_unprocessed_dates([], days)
        self.assertEqual(out, days)

    def test_inclusive_boundaries(self):
        days = [self._d(2025, 7, i) for i in range(1, 6)]
        ranges = [{"start_date": "2025-07-02", "end_date": "2025-07-04"}]
        out = filter_unprocessed_dates(ranges, days)
        # 2..4 are processed; keep 1 and 5
        self.assertEqual(out, [self._d(2025, 7, 1), self._d(2025, 7, 5)])

    def test_multiple_ranges_overlap(self):
        days = [self._d(2025, 7, i) for i in range(1, 8)]
        ranges = [
            {"start_date": "2025-07-01", "end_date": "2025-07-03"},
            {"start_date": "2025-07-03", "end_date": "2025-07-05"},
        ]
        out = filter_unprocessed_dates(ranges, days)
        # 1..5 are covered due to overlap; keep 6,7
        self.assertEqual(out, [self._d(2025, 7, 6), self._d(2025, 7, 7)])

    def test_malformed_ranges_are_ignored(self):
        days = [self._d(2025, 7, i) for i in (1, 2)]
        ranges = [{"start_date": "invalid", "end_date": "2025-07-02"}]
        out = filter_unprocessed_dates(ranges, days)
        # malformed -> ignored, so all days remain
        self.assertEqual(out, days)


if __name__ == '__main__':
    unittest.main()


import unittest
from lib.filename import parse_range_and_user


class TestFilenameParsing(unittest.TestCase):
    def test_single_month(self):
        user, start, end = parse_range_and_user("/x/202508-王小明-出勤資料.txt")
        self.assertEqual(user, "王小明")
        self.assertEqual(start, "2025-08-01")
        self.assertEqual(end, "2025-08-31")

    def test_cross_month(self):
        user, start, end = parse_range_and_user("/x/202508-202509-王小明-出勤資料.txt")
        self.assertEqual(user, "王小明")
        self.assertEqual(start, "2025-08-01")
        self.assertEqual(end, "2025-09-30")

    def test_invalid(self):
        user, start, end = parse_range_and_user("/x/invalid.txt")
        self.assertIsNone(user)
        self.assertIsNone(start)
        self.assertIsNone(end)


if __name__ == "__main__":
    unittest.main()
"""Category: Filename/Parsing
Purpose: Parse user and date ranges from filename patterns."""

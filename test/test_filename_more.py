import unittest

from lib.filename import parse_range_and_user


class TestFilenameMore(unittest.TestCase):
    def test_bad_patterns_return_none(self):
        for name in [
            'badname.txt',
            '2025AA-姓名-出勤資料.txt',
            '202513-202514-姓名-出勤資料.txt',
        ]:
            u, s, e = parse_range_and_user(name)
            self.assertIsNone(u)
            self.assertIsNone(s)
            self.assertIsNone(e)

    def test_second_segment_non_digits_becomes_part_of_name(self):
        # According to current parser regex, non-digit 2nd segment is treated as part of the name
        u, s, e = parse_range_and_user('202512-2025XX-姓名-出勤資料.txt')
        self.assertEqual(u, '2025XX-姓名')
        self.assertEqual(s, '2025-12-01')
        self.assertEqual(e, '2025-12-31')


if __name__ == '__main__':
    unittest.main()
"""Category: Filename/Parsing
Purpose: Edge patterns and invalid month handling for filename parsing."""

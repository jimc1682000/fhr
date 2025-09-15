import unittest
from unittest.mock import patch

import lib.filename as lf


class TestFilenameEdge(unittest.TestCase):
    def test_single_month_next_month_value_error(self):
        real_dt = lf.datetime

        calls = {'n': 0}

        def dt_fn(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 1:
                return real_dt(*args, **kwargs)
            raise ValueError('forced')

        with patch('lib.filename.datetime', dt_fn):
            self.assertEqual(
                lf.parse_range_and_user('202501-姓名-出勤資料.txt'), (None, None, None)
            )


if __name__ == '__main__':
    unittest.main()
"""Category: Filename/Parsing
Purpose: Force ValueError in single-month end-date calculation path."""

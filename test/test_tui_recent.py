import os
import json
import unittest
from unittest import mock


class TestRecentList(unittest.TestCase):
    def setUp(self):
        # ensure a clean recent file in CWD
        self.recent_path = os.path.join(os.getcwd(), ".fhr_recent.json")
        try:
            os.remove(self.recent_path)
        except FileNotFoundError:
            pass

    def tearDown(self):
        try:
            os.remove(self.recent_path)
        except FileNotFoundError:
            pass

    def test_add_and_load_recent(self):
        from tui.recent import add_recent_file, load_recent_files

        # create two temp files
        f1 = os.path.join(os.getcwd(), "sample-attendance-data.txt")
        f2 = os.path.join(os.getcwd(), "202507-202508-JimmyChen-出勤資料.txt")
        open(f1, "a").close()
        open(f2, "a").close()
        try:
            add_recent_file(f1)
            add_recent_file(f2)
            lst = load_recent_files()
            self.assertTrue(lst and lst[0].endswith("出勤資料.txt"))
            self.assertEqual(len(lst), 2)
        finally:
            os.remove(f2)


if __name__ == "__main__":
    unittest.main()

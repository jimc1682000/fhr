import os
import shutil
import tempfile
import unittest

from lib.cli import run as cli_run


class TestCliBasic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _copy_sample(self, name='sample-attendance-data.txt'):
        src = os.path.join(os.getcwd(), name)
        dst = os.path.join(self.tmp.name, name)
        shutil.copy(src, dst)
        return dst

    def test_full_csv_export_creates_file(self):
        f = self._copy_sample()
        argv = ['attendance_analyzer.py', f, 'csv', '--full']
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            with self.assertLogs(level='INFO'):
                cli_run(argv)
            self.assertTrue(os.path.exists(f.replace('.txt', '_analysis.csv')))
        finally:
            os.chdir(cwd)

    def test_incremental_default_csv(self):
        f = self._copy_sample()
        argv = ['attendance_analyzer.py', f, 'csv']
        cwd = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            with self.assertLogs(level='INFO'):
                cli_run(argv)
            self.assertTrue(os.path.exists(f.replace('.txt', '_analysis.csv')))
        finally:
            os.chdir(cwd)


if __name__ == '__main__':
    unittest.main()
"""Category: CLI
Purpose: Basic CLI flows for full and incremental CSV export."""

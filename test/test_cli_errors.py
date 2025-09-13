import os
import tempfile
import unittest
from unittest import mock

import attendance_analyzer as mod


class TestCliErrors(unittest.TestCase):
    def test_reset_state_with_unparsable_filename_exits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = os.path.join(tmpdir, 'sample-attendance-data.txt')
            with open(bad, 'w', encoding='utf-8') as f:
                f.write('header\n')
            cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                argv = ['attendance_analyzer.py', bad, '--reset-state']
                with self.assertLogs(level='WARNING') as cm:
                    with self.assertRaises(SystemExit) as se:
                        with mock.patch('sys.argv', argv):
                            mod.main()
                self.assertEqual(se.exception.code, 1)
                self.assertIn('無法從檔名識別使用者', "\n".join(cm.output))
            finally:
                os.chdir(cwd)


if __name__ == '__main__':
    unittest.main()
"""Category: CLI
Purpose: Error handling paths for CLI (unparsable filename, sys.exit)."""

import os
import tempfile
import unittest

from lib.backup import backup_with_timestamp


class TestBackup(unittest.TestCase):
    def test_backup_with_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'report.csv')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('data')

            backup = backup_with_timestamp(path)
            self.assertIsNotNone(backup)
            self.assertFalse(os.path.exists(path))
            self.assertTrue(os.path.exists(backup))
            self.assertTrue(backup.endswith('.csv'))
            # name contains timestamp suffix
            self.assertIn('_', os.path.basename(backup).replace('report', ''))

    def test_no_backup_when_absent(self):
        backup = backup_with_timestamp('/non/existent/file.csv')
        self.assertIsNone(backup)


if __name__ == '__main__':
    unittest.main()
"""Category: Backup
Purpose: Ensure timestamped backup behavior and no-op when missing."""

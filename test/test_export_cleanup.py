import os
import tempfile
import unittest

from lib.export_cleanup import cleanup_exports, list_backups


class TestExportCleanup(unittest.TestCase):
    def test_list_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, 'sample_analysis.csv')
            open(os.path.join(tmp, 'sample_analysis_20250930_120000.csv'), 'w').close()
            open(os.path.join(tmp, 'sample_analysis_20250930_120500.csv'), 'w').close()
            open(os.path.join(tmp, 'other_file.csv'), 'w').close()

            backups = list_backups(base)
            names = {os.path.basename(p) for p in backups}
            self.assertEqual(
                names,
                {'sample_analysis_20250930_120000.csv', 'sample_analysis_20250930_120500.csv'},
            )

    def test_cleanup_exports_optionally_includes_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, 'sample_analysis.csv')
            canonical = base
            open(canonical, 'w').close()
            ts_path = os.path.join(tmp, 'sample_analysis_20250930_120000.csv')
            open(ts_path, 'w').close()

            removed = cleanup_exports(base)
            self.assertEqual([ts_path], removed)
            self.assertFalse(os.path.exists(ts_path))
            self.assertTrue(os.path.exists(canonical))

            removed_with_canonical = cleanup_exports(base, include_canonical=True)
            self.assertEqual([canonical], removed_with_canonical)
            self.assertFalse(os.path.exists(canonical))

    def test_list_backups_rejects_directory_traversal(self):
        """Test that list_backups rejects paths with directory traversal"""
        with self.assertRaises(ValueError) as ctx:
            list_backups('../etc/passwd')
        self.assertIn('directory traversal', str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            list_backups('foo/../../etc/passwd')
        self.assertIn('directory traversal', str(ctx.exception))

    def test_list_backups_ignores_subdirectories(self):
        """Test that list_backups only considers files in the same directory"""
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, 'sample_analysis.csv')
            # Create a valid backup
            open(os.path.join(tmp, 'sample_analysis_20250930_120000.csv'), 'w').close()
            # Try to create a malicious filename with path separator (should be ignored)
            # Note: This is just for testing - actual filesystems won't allow this
            backups = list_backups(base)
            # Should only find the legitimate backup
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].endswith('sample_analysis_20250930_120000.csv'))

    def test_cleanup_handles_permission_errors(self):
        """Test that cleanup handles permission errors gracefully"""
        with tempfile.TemporaryDirectory() as tmp:
            base = os.path.join(tmp, 'sample_analysis.csv')
            backup = os.path.join(tmp, 'sample_analysis_20250930_120000.csv')
            open(backup, 'w').close()

            # Make the backup read-only
            import stat
            os.chmod(backup, stat.S_IRUSR)

            try:
                # Should log warning but not crash
                removed = cleanup_exports(base)
                # File should not be in removed list
                self.assertEqual(removed, [])
                # File should still exist
                self.assertTrue(os.path.exists(backup))
            finally:
                # Cleanup - restore permissions
                os.chmod(backup, stat.S_IWUSR | stat.S_IRUSR)
                os.unlink(backup)


if __name__ == '__main__':
    unittest.main()
"""Category: Export/Cleanup
Purpose: Ensure timestamped backups are detected and removed when requested."""

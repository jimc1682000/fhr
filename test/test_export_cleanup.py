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


if __name__ == '__main__':
    unittest.main()
"""Category: Export/Cleanup
Purpose: Ensure timestamped backups are detected and removed when requested."""

"""Test source_file_name exception handling in parse_attendance_file."""

import tempfile
import unittest
from unittest.mock import patch

from attendance_analyzer import AttendanceAnalyzer


class TestSourceFileNameException(unittest.TestCase):
    """Test the exception handling when getting source_file_name."""

    def test_source_file_name_exception_handling(self):
        """Test that source_file_name is set to None when os.path.basename raises."""
        # Create a normal test file
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            f.write('應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n')
            f.write('2025/07/01 09:00\t2025/07/01 09:00\t上班\t1\t刷卡匯入\t\t\t\t\n')
            temp_path = f.name

        # Patch os.path.basename to raise an exception
        with patch('os.path.basename', side_effect=Exception('Mocked error')):
            analyzer = AttendanceAnalyzer()
            # This should not raise, but set source_file_name to None
            analyzer.parse_attendance_file(temp_path, incremental=True)
            
            # Verify source_file_name was set to None due to exception
            self.assertIsNone(analyzer.source_file_name)

        # Clean up
        import os
        os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()
"""Category: Analyzer/Exception
Purpose: Test source_file_name exception handling for edge cases."""
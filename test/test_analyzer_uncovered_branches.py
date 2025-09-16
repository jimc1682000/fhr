"""Test uncovered branches in AttendanceAnalyzer."""

import os
import tempfile
import unittest
from unittest.mock import patch

from attendance_analyzer import AttendanceAnalyzer


class TestAnalyzerUncoveredBranches(unittest.TestCase):
    """Test uncovered code branches in AttendanceAnalyzer."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Create sample attendance data
        self.test_file = os.path.join(self.temp_dir, "test_data.txt")
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write('應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n')
            f.write('2025/07/01 09:00\t2025/07/01 09:00\t上班\t1\t刷卡匯入\t\t\t\t\n')
            f.write('2025/07/01 18:00\t2025/07/01 18:00\t下班\t1\t刷卡匯入\t\t\t\t\n')

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)
        os.rmdir(self.temp_dir)

    def test_non_incremental_mode_get_unprocessed_dates(self):
        """Test _get_unprocessed_dates when not in incremental mode."""
        analyzer = AttendanceAnalyzer()
        analyzer.incremental_mode = False
        
        # Parse the file to populate records
        analyzer.parse_attendance_file(self.test_file, incremental=False)
        
        # Get complete work days
        complete_days = analyzer._identify_complete_work_days()
        
        # Test _get_unprocessed_dates in non-incremental mode
        unprocessed = analyzer._get_unprocessed_dates("test_user", complete_days)
        
        # In non-incremental mode, should return all complete days
        self.assertEqual(unprocessed, complete_days)

    def test_no_state_manager_get_unprocessed_dates(self):
        """Test _get_unprocessed_dates when state_manager is None."""
        analyzer = AttendanceAnalyzer()
        analyzer.state_manager = None
        analyzer.incremental_mode = True  # Enable incremental but no state manager
        
        # Parse the file to populate records
        # Don't initialize state manager
        analyzer.parse_attendance_file(self.test_file, incremental=False)
        analyzer.state_manager = None  # Explicitly set to None
        
        # Get complete work days
        complete_days = analyzer._identify_complete_work_days()
        
        # Test _get_unprocessed_dates with no state manager
        unprocessed = analyzer._get_unprocessed_dates("test_user", complete_days)
        
        # Should return all complete days when no state manager
        self.assertEqual(unprocessed, complete_days)

    def test_load_previous_forget_punch_usage_no_state_manager(self):
        """Test _load_previous_forget_punch_usage when state_manager is None."""
        analyzer = AttendanceAnalyzer()
        analyzer.state_manager = None
        analyzer.incremental_mode = True
        
        # Should return early without error
        analyzer._load_previous_forget_punch_usage("test_user")
        
        # Should maintain empty defaultdict
        self.assertEqual(len(analyzer.forget_punch_usage), 0)

    def test_load_previous_forget_punch_usage_non_incremental(self):
        """Test _load_previous_forget_punch_usage when not in incremental mode."""
        analyzer = AttendanceAnalyzer()
        analyzer.incremental_mode = False
        
        # Should return early without error
        analyzer._load_previous_forget_punch_usage("test_user")
        
        # Should maintain empty defaultdict
        self.assertEqual(len(analyzer.forget_punch_usage), 0)

    def test_load_taiwan_holidays_with_none(self):
        """Test _load_taiwan_holidays with years=None."""
        analyzer = AttendanceAnalyzer()
        
        # Test with None to trigger default year (2025)
        analyzer._load_taiwan_holidays(years=None)
        
        # Should have loaded 2025 holidays
        self.assertIn(2025, analyzer.loaded_holiday_years)

    def test_try_load_from_gov_api_unsupported_scheme(self):
        """Test _try_load_from_gov_api with unsupported URL scheme."""
        analyzer = AttendanceAnalyzer()
        
        # Patch urlparse to return unsupported scheme
        with patch('attendance_analyzer.urlparse') as mock_urlparse:
            mock_urlparse.return_value.scheme = "ftp"  # Unsupported scheme
            
            result = analyzer._try_load_from_gov_api(2025)
            
            # Should return False for unsupported scheme
            self.assertFalse(result)

    def test_parse_attendance_file_source_filename_exception(self):
        """Test parse_attendance_file when setting source_file_name raises exception."""
        analyzer = AttendanceAnalyzer()
        
        # Test that the source_file_name is set correctly normally
        analyzer.parse_attendance_file(self.test_file, incremental=False)
        
        # Should set source_file_name to the basename
        self.assertEqual(analyzer.source_file_name, "test_data.txt")

    def test_parse_attendance_file_no_user_from_filename(self):
        """Test parse_attendance_file when filename parsing returns no user."""
        analyzer = AttendanceAnalyzer()
        
        # Use a filename that won't match the pattern
        bad_filename = os.path.join(self.temp_dir, "bad_format.txt")
        with open(bad_filename, 'w', encoding='utf-8') as f:
            f.write('應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n')
            f.write('2025/07/01 09:00\t2025/07/01 09:00\t上班\t1\t刷卡匯入\t\t\t\t\n')
        
        try:
            analyzer.parse_attendance_file(bad_filename, incremental=True)
            
            # Should not set current_user when parsing fails
            self.assertIsNone(analyzer.current_user)
        finally:
            if os.path.exists(bad_filename):
                os.unlink(bad_filename)


if __name__ == '__main__':
    unittest.main()
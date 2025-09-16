"""Test exception handling in AttendanceStateManager."""

import os
import tempfile
import unittest
from unittest.mock import patch

from lib.state import AttendanceStateManager


class TestStateExceptionHandling(unittest.TestCase):
    """Test exception handling scenarios in AttendanceStateManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.temp_dir, "test_state.json")

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.state_file):
            os.unlink(self.state_file)
        os.rmdir(self.temp_dir)

    def test_load_state_json_decode_error(self):
        """Test handling of JSON decode error during state loading."""
        # Create a corrupted JSON file
        with open(self.state_file, 'w', encoding='utf-8') as f:
            f.write('{"invalid": json}')  # Invalid JSON
        
        manager = AttendanceStateManager(self.state_file)
        
        # Should return default state due to JSON decode error
        self.assertEqual(manager.state_data, {"users": {}})

    def test_load_state_os_error(self):
        """Test handling of OS error during state loading."""
        # Create file and make it unreadable
        with open(self.state_file, 'w', encoding='utf-8') as f:
            f.write('{"users": {}}')
        
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            manager = AttendanceStateManager(self.state_file)
            
            # Should return default state due to OS error
            self.assertEqual(manager.state_data, {"users": {}})

    def test_save_state_os_error(self):
        """Test handling of OS error during state saving."""
        manager = AttendanceStateManager(self.state_file)
        
        # Mock open to raise OSError during save
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            # Should not raise exception, just log warning
            manager.save_state()

    def test_get_forget_punch_usage_user_not_exists(self):
        """Test get_forget_punch_usage when user doesn't exist."""
        manager = AttendanceStateManager(self.state_file)
        
        usage = manager.get_forget_punch_usage("nonexistent_user", "2025-08")
        self.assertEqual(usage, 0)

    def test_get_forget_punch_usage_missing_data(self):
        """Test get_forget_punch_usage when user exists but no forget_punch_usage data."""
        manager = AttendanceStateManager(self.state_file)
        manager.state_data = {
            "users": {
                "test_user": {
                    "processed_date_ranges": []
                    # Missing forget_punch_usage key
                }
            }
        }
        
        usage = manager.get_forget_punch_usage("test_user", "2025-08")
        self.assertEqual(usage, 0)

    def test_get_last_analysis_time_user_not_exists(self):
        """Test get_last_analysis_time when user doesn't exist."""
        manager = AttendanceStateManager(self.state_file)
        
        last_time = manager.get_last_analysis_time("nonexistent_user")
        self.assertEqual(last_time, "")

    def test_get_last_analysis_time_no_ranges(self):
        """Test get_last_analysis_time when user exists but no processed ranges."""
        manager = AttendanceStateManager(self.state_file)
        manager.state_data = {
            "users": {
                "test_user": {
                    "processed_date_ranges": [],
                    "forget_punch_usage": {}
                }
            }
        }
        
        last_time = manager.get_last_analysis_time("test_user")
        self.assertEqual(last_time, "")

    def test_get_last_analysis_time_missing_time_field(self):
        """Test get_last_analysis_time when ranges exist but missing time field."""
        manager = AttendanceStateManager(self.state_file)
        manager.state_data = {
            "users": {
                "test_user": {
                    "processed_date_ranges": [
                        {
                            "start_date": "2025-08-01",
                            "end_date": "2025-08-31",
                            "source_file": "test.txt"
                            # Missing last_analysis_time field
                        }
                    ],
                    "forget_punch_usage": {}
                }
            }
        }
        
        last_time = manager.get_last_analysis_time("test_user")
        self.assertEqual(last_time, "")

    def test_update_user_state_new_user(self):
        """Test update_user_state when user doesn't exist in state."""
        manager = AttendanceStateManager(self.state_file)
        
        new_range = {
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
            "source_file": "test.txt",
            "last_analysis_time": "2025-08-27T14:30:00"
        }
        forget_punch_usage = {"2025-08": 1}
        
        manager.update_user_state("new_user", new_range, forget_punch_usage)
        
        # Verify user was created with correct structure
        self.assertIn("new_user", manager.state_data["users"])
        user_data = manager.state_data["users"]["new_user"]
        self.assertEqual(user_data["processed_date_ranges"], [new_range])
        self.assertEqual(user_data["forget_punch_usage"], forget_punch_usage)

    def test_update_user_state_existing_file_update(self):
        """Test update_user_state when updating existing file range."""
        manager = AttendanceStateManager(self.state_file)
        manager.state_data = {
            "users": {
                "test_user": {
                    "processed_date_ranges": [
                        {
                            "start_date": "2025-08-01",
                            "end_date": "2025-08-15",
                            "source_file": "test.txt",
                            "last_analysis_time": "2025-08-15T10:00:00"
                        }
                    ],
                    "forget_punch_usage": {"2025-08": 0}
                }
            }
        }
        
        updated_range = {
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
            "source_file": "test.txt",
            "last_analysis_time": "2025-08-31T15:00:00"
        }
        
        manager.update_user_state("test_user", updated_range, {"2025-08": 1})
        
        # Verify existing range was updated, not appended
        user_data = manager.state_data["users"]["test_user"]
        self.assertEqual(len(user_data["processed_date_ranges"]), 1)
        self.assertEqual(user_data["processed_date_ranges"][0], updated_range)
        self.assertEqual(user_data["forget_punch_usage"]["2025-08"], 1)

    def test_update_user_state_new_file_append(self):
        """Test update_user_state when adding new file range."""
        manager = AttendanceStateManager(self.state_file)
        manager.state_data = {
            "users": {
                "test_user": {
                    "processed_date_ranges": [
                        {
                            "start_date": "2025-07-01",
                            "end_date": "2025-07-31",
                            "source_file": "july.txt",
                            "last_analysis_time": "2025-07-31T10:00:00"
                        }
                    ],
                    "forget_punch_usage": {"2025-07": 2}
                }
            }
        }
        
        new_range = {
            "start_date": "2025-08-01",
            "end_date": "2025-08-31",
            "source_file": "august.txt",
            "last_analysis_time": "2025-08-31T15:00:00"
        }
        
        manager.update_user_state("test_user", new_range, {"2025-08": 1})
        
        # Verify new range was appended
        user_data = manager.state_data["users"]["test_user"]
        self.assertEqual(len(user_data["processed_date_ranges"]), 2)
        self.assertEqual(user_data["processed_date_ranges"][1], new_range)
        self.assertEqual(user_data["forget_punch_usage"]["2025-07"], 2)
        self.assertEqual(user_data["forget_punch_usage"]["2025-08"], 1)


if __name__ == '__main__':
    unittest.main()
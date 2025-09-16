"""Test filter_unprocessed_dates function edge cases and uncovered paths."""

import unittest
from datetime import datetime

from lib.state import filter_unprocessed_dates


class TestFilterUnprocessedDates(unittest.TestCase):
    """Test filter_unprocessed_dates function comprehensive scenarios."""

    def test_empty_processed_ranges(self):
        """Test with empty processed_ranges (None and empty list)."""
        complete_days = [
            datetime(2025, 8, 1),
            datetime(2025, 8, 2),
            datetime(2025, 8, 3)
        ]
        
        # Test with None
        result = filter_unprocessed_dates(None, complete_days)
        self.assertEqual(result, complete_days)
        
        # Test with empty list
        result = filter_unprocessed_dates([], complete_days)
        self.assertEqual(result, complete_days)

    def test_malformed_date_ranges_skipped(self):
        """Test that malformed date ranges are skipped gracefully."""
        processed_ranges = [
            {
                "start_date": "invalid-date",
                "end_date": "2025-08-31"
            },
            {
                "start_date": "2025-08-01",
                "end_date": "invalid-date"
            },
            {
                "start_date": "2025-08-15",
                "end_date": "2025-08-20"
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 10),  # Should be unprocessed
            datetime(2025, 8, 16),  # Should be filtered out (in valid range)
            datetime(2025, 8, 25)   # Should be unprocessed
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        # Only the day within the valid range should be filtered out
        expected = [datetime(2025, 8, 10), datetime(2025, 8, 25)]
        self.assertEqual(result, expected)

    def test_range_merging_scenarios(self):
        """Test range merging logic for overlapping and adjacent ranges."""
        # Test overlapping ranges
        processed_ranges = [
            {
                "start_date": "2025-08-01",
                "end_date": "2025-08-10"
            },
            {
                "start_date": "2025-08-05",  # Overlaps with first range
                "end_date": "2025-08-15"
            },
            {
                "start_date": "2025-08-20",  # Separate range
                "end_date": "2025-08-25"
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 3),   # In merged range (1-15)
            datetime(2025, 8, 8),   # In merged range (1-15) 
            datetime(2025, 8, 12),  # In merged range (1-15)
            datetime(2025, 8, 18),  # Between ranges - unprocessed
            datetime(2025, 8, 22),  # In second range (20-25)
            datetime(2025, 8, 30)   # After ranges - unprocessed
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        # Only days 18 and 30 should be unprocessed
        expected = [datetime(2025, 8, 18), datetime(2025, 8, 30)]
        self.assertEqual(result, expected)

    def test_adjacent_ranges_merging(self):
        """Test that adjacent ranges are merged correctly."""
        processed_ranges = [
            {
                "start_date": "2025-08-01",
                "end_date": "2025-08-10"
            },
            {
                "start_date": "2025-08-11",  # Adjacent to first range
                "end_date": "2025-08-20"
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 5),   # In merged range
            datetime(2025, 8, 10),  # End of first range
            datetime(2025, 8, 11),  # Start of second range
            datetime(2025, 8, 15),  # In merged range
            datetime(2025, 8, 25)   # After merged range - unprocessed
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        # Only day 25 should be unprocessed
        expected = [datetime(2025, 8, 25)]
        self.assertEqual(result, expected)

    def test_binary_search_edge_cases(self):
        """Test binary search logic with edge cases."""
        processed_ranges = [
            {
                "start_date": "2025-08-05",
                "end_date": "2025-08-10"
            },
            {
                "start_date": "2025-08-15",
                "end_date": "2025-08-20"
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 1),   # Before all ranges
            datetime(2025, 8, 4),   # Just before first range
            datetime(2025, 8, 5),   # Start of first range
            datetime(2025, 8, 7),   # Middle of first range
            datetime(2025, 8, 10),  # End of first range
            datetime(2025, 8, 12),  # Between ranges
            datetime(2025, 8, 15),  # Start of second range
            datetime(2025, 8, 18),  # Middle of second range
            datetime(2025, 8, 20),  # End of second range
            datetime(2025, 8, 25)   # After all ranges
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        # Days outside ranges should be unprocessed
        expected = [
            datetime(2025, 8, 1),
            datetime(2025, 8, 4),
            datetime(2025, 8, 12),
            datetime(2025, 8, 25)
        ]
        self.assertEqual(result, expected)

    def test_single_day_ranges(self):
        """Test with single-day processed ranges."""
        processed_ranges = [
            {
                "start_date": "2025-08-05",
                "end_date": "2025-08-05"  # Single day
            },
            {
                "start_date": "2025-08-10",
                "end_date": "2025-08-10"  # Single day
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 4),   # Unprocessed
            datetime(2025, 8, 5),   # Processed
            datetime(2025, 8, 6),   # Unprocessed
            datetime(2025, 8, 10),  # Processed
            datetime(2025, 8, 11)   # Unprocessed
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        expected = [
            datetime(2025, 8, 4),
            datetime(2025, 8, 6),
            datetime(2025, 8, 11)
        ]
        self.assertEqual(result, expected)

    def test_out_of_order_ranges(self):
        """Test that ranges are sorted before processing."""
        processed_ranges = [
            {
                "start_date": "2025-08-15",  # Later range listed first
                "end_date": "2025-08-20"
            },
            {
                "start_date": "2025-08-05",  # Earlier range listed second
                "end_date": "2025-08-10"
            }
        ]
        
        complete_days = [
            datetime(2025, 8, 7),   # In first chronological range
            datetime(2025, 8, 12),  # Between ranges
            datetime(2025, 8, 17)   # In second chronological range
        ]
        
        result = filter_unprocessed_dates(processed_ranges, complete_days)
        
        # Only the day between ranges should be unprocessed
        expected = [datetime(2025, 8, 12)]
        self.assertEqual(result, expected)

    def test_empty_complete_days(self):
        """Test with empty complete_days list."""
        processed_ranges = [
            {
                "start_date": "2025-08-01",
                "end_date": "2025-08-31"
            }
        ]
        
        result = filter_unprocessed_dates(processed_ranges, [])
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
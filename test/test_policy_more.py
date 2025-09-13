import unittest
from datetime import datetime

from lib.policy import Rules, calculate_late_minutes, calculate_overtime_minutes


class W:
    def __init__(self, ci=None, co=None, date=datetime(2025,7,1)):
        class Rec:
            def __init__(self, t):
                self.actual_time = t
        self.checkin_record = Rec(ci) if ci else None
        self.checkout_record = Rec(co) if co else None
        self.date = date


class TestPolicyMore(unittest.TestCase):
    def test_late_over_120_before_lunch_no_deduction(self):
        # Make latest_checkin very early so 11:30 becomes >120 mins late, but before lunch start.
        rules = Rules(latest_checkin='09:00')  # lunch_start default 12:30
        wd = W(ci=datetime(2025,7,1,11,30), co=datetime(2025,7,1,20,0))
        mins, tr, calc = calculate_late_minutes(wd, rules)
        self.assertGreater(mins, 120)
        self.assertIn('遲到:', calc)
        self.assertNotIn('午休', calc)  # no deduction branch

    def test_late_early_return_when_missing_checkin(self):
        rules = Rules()
        wd = W(ci=None, co=datetime(2025,7,1,18,0))
        mins, tr, calc = calculate_late_minutes(wd, rules)
        self.assertEqual((mins, tr, calc), (0, '', ''))

    def test_overtime_early_return_when_incomplete(self):
        rules = Rules()
        wd = W(ci=datetime(2025,7,1,9,0), co=None)
        actual, applicable, tr, calc = calculate_overtime_minutes(wd, rules)
        self.assertEqual((actual, applicable, tr, calc), (0, 0, '', ''))


if __name__ == '__main__':
    unittest.main()
"""Category: Policy
Purpose: Additional late/overtime guard branches and no-deduction scenario."""

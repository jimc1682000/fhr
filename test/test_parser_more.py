import unittest

from lib import parser


class TestParserMore(unittest.TestCase):
    def test_too_few_fields_returns_none(self):
        # Fewer than 3 fields after split -> early None
        self.assertIsNone(parser.parse_line("only-one\tfield"))

    def test_bad_scheduled_datetime_returns_none(self):
        # scheduled_str present but bad format -> scheduled_dt None -> None
        line = "bad-dt\t2025/07/01 09:00\t上班\t卡\t源\t\t\t\t"
        self.assertIsNone(parser.parse_line(line))


if __name__ == "__main__":
    unittest.main()
"""Category: Parsing
Purpose: Minimal-field handling and bad scheduled datetime."""

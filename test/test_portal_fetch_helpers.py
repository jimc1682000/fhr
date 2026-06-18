"""Unit tests for `lib/commands/portal_fetch.py` helpers (Tier 1)."""

import argparse
import os
import unittest
from datetime import date

from lib.commands.portal_fetch import (
    _default_out,
    _default_range,
    _parse_date,
    _prev_day,
    _resolve_base_url,
)


class TestParseDate(unittest.TestCase):
    def test_slash_format(self):
        self.assertEqual(_parse_date("2026/04/01"), date(2026, 4, 1))

    def test_dash_format(self):
        self.assertEqual(_parse_date("2026-04-01"), date(2026, 4, 1))

    def test_malformed_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_date("not-a-date")


class TestDefaultRange(unittest.TestCase):
    def test_mid_month(self):
        start, end = _default_range(today=date(2026, 5, 15))
        self.assertEqual(start, date(2026, 5, 1))
        self.assertEqual(end, date(2026, 5, 31))

    def test_december_year_wrap(self):
        start, end = _default_range(today=date(2026, 12, 10))
        self.assertEqual(start, date(2026, 12, 1))
        self.assertEqual(end, date(2026, 12, 31))

    def test_february_leap(self):
        # 2024 was leap
        start, end = _default_range(today=date(2024, 2, 10))
        self.assertEqual(end, date(2024, 2, 29))


class TestPrevDay(unittest.TestCase):
    def test_subtract_one(self):
        self.assertEqual(_prev_day(date(2026, 5, 2)), date(2026, 5, 1))

    def test_month_boundary(self):
        self.assertEqual(_prev_day(date(2026, 6, 1)), date(2026, 5, 31))


class TestDefaultOut(unittest.TestCase):
    def test_same_month(self):
        out = _default_out("JimmyChen", date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(out.name, "202605-JimmyChen-出勤資料.txt")
        self.assertEqual(out.parent.name, "tmp")

    def test_cross_month(self):
        out = _default_out("JimmyChen", date(2026, 4, 1), date(2026, 5, 31))
        self.assertEqual(out.name, "202604-202605-JimmyChen-出勤資料.txt")


class TestResolveBaseUrl(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        os.environ.pop("EHR_URL", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def _ns(self, **kw):
        defaults = {"base_url": None}
        return argparse.Namespace(**{**defaults, **kw})

    def test_arg_overrides_env(self):
        os.environ["EHR_URL"] = "http://from-env"
        self.assertEqual(
            _resolve_base_url(self._ns(base_url="http://from-arg")), "http://from-arg"
        )

    def test_env_used(self):
        os.environ["EHR_URL"] = "http://x.example/ehrPortal"
        self.assertEqual(_resolve_base_url(self._ns()), "http://x.example/ehrPortal")

    def test_strip_login_suffix(self):
        os.environ["EHR_URL"] = "http://x.example/ehrPortal/LoginFOrginal.asp"
        self.assertEqual(_resolve_base_url(self._ns()), "http://x.example/ehrPortal")

    def test_missing_raises(self):
        with self.assertRaises(RuntimeError):
            _resolve_base_url(self._ns())


if __name__ == "__main__":
    unittest.main()

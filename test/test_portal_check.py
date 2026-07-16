"""Tests for `lib/commands/portal_check.py`."""

import argparse
import unittest
from unittest import mock

from lib.commands import portal_check


def _entry(date, **kw):
    base = {
        "date": date,
        "start_time": "0930",
        "end_time": "1830",
        "hours": 8,
        "leave_type": None,
        "location": None,
        "reason": "",
        "status": "流程結束(駁回)",
    }
    base.update(kw)
    return base


class TestFilterSince(unittest.TestCase):
    def test_none_keeps_all(self):
        entries = [_entry("2024/01/01"), _entry("2026/07/01")]
        self.assertEqual(len(portal_check.filter_since(entries, None)), 2)

    def test_month_prefix_boundary(self):
        entries = [
            _entry("2026/04/30"),
            _entry("2026/05/01"),
            _entry("2026/06/15"),
        ]
        kept = portal_check.filter_since(entries, "2026/05")
        self.assertEqual([e["date"] for e in kept], ["2026/05/01", "2026/06/15"])

    def test_full_date_since(self):
        entries = [_entry("2026/05/01"), _entry("2026/05/20")]
        kept = portal_check.filter_since(entries, "2026/05/10")
        self.assertEqual([e["date"] for e in kept], ["2026/05/20"])


class TestFormatReport(unittest.TestCase):
    def test_clean(self):
        text, clean = portal_check.format_report(
            {"overtime": [], "leave": []}, {"overtime": [], "leave": []}, "2026/05"
        )
        self.assertTrue(clean)
        self.assertIn("乾淨", text)
        self.assertIn("2026/05", text)

    def test_rejected_and_pending(self):
        rejected = {"overtime": [_entry("2026/05/01", location="在辦公室", hours=2)], "leave": []}
        pending = {"overtime": [], "leave": [_entry("2026/06/02", status="簽核中")]}
        text, clean = portal_check.format_report(rejected, pending, None)
        self.assertFalse(clean)
        self.assertIn("被駁回 1 筆", text)
        self.assertIn("簽核中/未處理 1 筆", text)
        self.assertIn("[加班單]", text)
        self.assertIn("[請假單]", text)
        self.assertIn("全部歷史", text)

    def test_only_rejected(self):
        rejected = {"overtime": [], "leave": [_entry("2026/05/05")]}
        pending = {"overtime": [], "leave": []}
        text, clean = portal_check.format_report(rejected, pending, None)
        self.assertFalse(clean)
        self.assertIn("被駁回 1 筆", text)
        self.assertNotIn("仍在簽核中/未處理", text)


class TestResolveBaseUrl(unittest.TestCase):
    def test_arg_wins(self):
        args = argparse.Namespace(base_url="http://x/")
        self.assertEqual(portal_check._resolve_base_url(args), "http://x")

    def test_env_strips_login_page(self):
        args = argparse.Namespace(base_url=None)
        with mock.patch.dict("os.environ", {"EHR_URL": "http://ehr/portal/LoginFOrginal.asp"}):
            self.assertEqual(portal_check._resolve_base_url(args), "http://ehr/portal")

    def test_missing_raises(self):
        args = argparse.Namespace(base_url=None)
        with mock.patch.dict("os.environ", {"EHR_URL": ""}):
            with self.assertRaises(RuntimeError):
                portal_check._resolve_base_url(args)


class TestRun(unittest.TestCase):
    def _args(self, **kw):
        base = dict(
            since=None,
            kinds=["overtime", "leave"],
            base_url="http://x",
            session=None,
            debug=False,
        )
        base.update(kw)
        return argparse.Namespace(**base)

    def _run_capture(self, args, rejected, pending):
        """Run portal_check.run() with the portal + approvals layer mocked.

        Returns (joined_logs, fetch_mock). Patches the concrete symbols the
        lazy imports resolve to (patching sys.modules would not intercept
        `from lib.portal import approvals` once the real module is loaded)."""
        session_cm = mock.MagicMock()
        session_cm.__enter__.return_value = mock.MagicMock()
        logs: list[str] = []

        with (
            mock.patch(
                "lib.portal.approvals.fetch_all_applied_forms",
                side_effect=[rejected, pending],
            ) as fetch,
            mock.patch("lib.portal.client.PortalSession", return_value=session_cm),
            mock.patch("lib.portal.client.ensure_login"),
            mock.patch("attendance_analyzer.logger") as logger,
        ):
            logger.info.side_effect = lambda fmt, *a: logs.append(fmt % a if a else fmt)
            portal_check.run(args)
        return "\n".join(logs), fetch

    def test_run_clean(self):
        joined, fetch = self._run_capture(
            self._args(),
            {"overtime": [], "leave": []},
            {"overtime": [], "leave": []},
        )
        self.assertIn("乾淨", joined)
        # queried both 已駁回 + 未處理
        self.assertEqual(fetch.call_count, 2)

    def test_run_reports_rejected(self):
        joined, _ = self._run_capture(
            self._args(),
            {"overtime": [_entry("2026/07/01")], "leave": []},
            {"overtime": [], "leave": []},
        )
        self.assertIn("被駁回 1 筆", joined)

    def test_run_with_since_filters(self):
        # the 2024 rejection is filtered out by --since 2026/05 → clean
        joined, _ = self._run_capture(
            self._args(since="2026/05"),
            {"overtime": [_entry("2024/01/01")], "leave": []},
            {"overtime": [], "leave": []},
        )
        self.assertIn("乾淨", joined)

    def test_run_missing_base_url_exits(self):
        args = self._args(base_url=None)
        with (
            mock.patch.dict("os.environ", {"EHR_URL": ""}),
            mock.patch("lib.env.load"),
            mock.patch("attendance_analyzer.logger"),
        ):
            with self.assertRaises(SystemExit) as cm:
                portal_check.run(args)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

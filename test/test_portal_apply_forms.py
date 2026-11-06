"""Tests for `lib/portal/apply_forms.py`.

We mock PortalSession; verify the right JS lands at the right time. The
Portal list lookup (`_find_in_portal`) is patched: the first call is the
pre-submit duplicate check, the second the post-submit confirmation.
"""

import unittest
from unittest import mock

from lib.portal.apply_forms import (
    ALREADY_PENDING,
    BLOCKED,
    CONFIRMED,
    DRY_RUN,
    FAILED,
    UNCONFIRMED,
    _find_in_portal,
    batch_submit,
    submit_leave,
    submit_overtime,
)

FIND = "lib.portal.apply_forms._find_in_portal"


def _make_portal(snapshot_after: str = "加班單  主管簽核") -> mock.Mock:
    portal = mock.Mock()
    portal.eval_json.return_value = {"success": True}
    portal._run.return_value = snapshot_after
    return portal


class TestSubmitOvertime(unittest.TestCase):
    def test_happy_path(self):
        portal = _make_portal()
        entry = {
            "date": "2026/04/20",
            "start_time": "1830",
            "end_time": "2030",
            "hours": 2,
            "location": "在辦公室",
        }
        with mock.patch(FIND, side_effect=[False, True]):
            ok = submit_overtime(portal, "http://x", entry, reason="上線部署")
        self.assertEqual(ok, CONFIRMED)
        # open form + fill + location + reason + trigger_hour_calc + submit
        self.assertGreaterEqual(portal.eval_json.call_count, 5)

    def test_in_external_location(self):
        portal = _make_portal()
        entry = {
            "date": "2026/04/25",
            "start_time": "1400",
            "end_time": "1500",
            "hours": 1,
            "location": "在外地",
        }
        with mock.patch(FIND, side_effect=[False, True]):
            ok = submit_overtime(portal, "http://x", entry, reason="供應鏈事件")
        self.assertEqual(ok, CONFIRMED)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertIn("在外地", joined)

    def test_not_on_portal_list_is_unconfirmed(self):
        portal = _make_portal()
        entry = {
            "date": "2026/04/20",
            "start_time": "1830",
            "end_time": "2030",
            "hours": 2,
            "location": "在辦公室",
        }
        with mock.patch(FIND, side_effect=[False, False]):
            self.assertEqual(submit_overtime(portal, "http://x", entry, reason="x"), UNCONFIRMED)


class TestSubmitLeave(unittest.TestCase):
    def test_wfh_skips_proxy(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},  # open form
            {"matched": 1, "matches": [{"index": 27, "text": "異地辦公(8hr一週)"}]},
            {"ok": True},  # fill datetime
            None,  # trigger
            {"ok": True},  # reason
            None,  # click submit
        ]
        portal._run.return_value = "請假單  主管簽核"
        entry = {
            "date": "2026/04/24",
            "start_time": "0930",
            "end_time": "1830",
            "hours": 9,
        }
        with mock.patch(FIND, side_effect=[False, True]):
            ok = submit_leave(
                portal,
                "http://x",
                entry,
                leave_type_name="異地辦公(8hr一週)",
                reason="WFH",
                proxy_employee="賴菁甫",
            )
        self.assertEqual(ok, CONFIRMED)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertNotIn("AGENT_ID_ddlDelegate", joined)

    def test_non_wfh_selects_proxy(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},  # open form
            {"ok": True},  # proxy select
            {"matched": 1, "matches": [{"index": 30, "text": "補休假"}]},
            {"ok": True},  # fill datetime
            None,  # trigger
            {"ok": True},  # reason
            None,  # submit
        ]
        portal._run.return_value = "請假單  主管簽核"
        entry = {
            "date": "2026/04/20",
            "start_time": "0930",
            "end_time": "1130",
            "hours": 2,
        }
        with mock.patch(FIND, side_effect=[False, True]):
            ok = submit_leave(
                portal,
                "http://x",
                entry,
                leave_type_name="補休假",
                reason="個人事務",
                proxy_employee="賴菁甫",
            )
        self.assertEqual(ok, CONFIRMED)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertIn("AGENT_ID_ddlDelegate", joined)

    def test_unmatched_leave_type_returns_false(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},
            True,  # proxy select
            {"matched": 0, "matches": []},
        ]
        portal._run.return_value = "請假單"
        entry = {
            "date": "2026/04/20",
            "start_time": "0930",
            "end_time": "1030",
            "hours": 1,
        }
        with mock.patch(FIND, return_value=False):
            ok = submit_leave(
                portal,
                "http://x",
                entry,
                leave_type_name="不存在的假別",
                reason="x",
                proxy_employee="P",
            )
        self.assertEqual(ok, FAILED)

    def test_ambiguous_leave_type_returns_false(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},
            True,  # proxy select
            {
                "matched": 2,
                "matches": [
                    {"index": 1, "text": "補休假"},
                    {"index": 2, "text": "補休假B"},
                ],
            },
        ]
        portal._run.return_value = "請假單"
        entry = {
            "date": "2026/04/20",
            "start_time": "0930",
            "end_time": "1030",
            "hours": 1,
        }
        with mock.patch(FIND, return_value=False):
            ok = submit_leave(
                portal, "http://x", entry, leave_type_name="補休假", reason="x", proxy_employee="P"
            )
        self.assertEqual(ok, FAILED)


class TestBatchSubmit(unittest.TestCase):
    def test_callbacks_fire_per_entry(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        portal._run.return_value = "加班單  主管簽核"
        overtime_plan = [
            {
                "action": "submit",
                "entry": {
                    "date": "2026/04/20",
                    "start_time": "1830",
                    "end_time": "2030",
                    "hours": 2,
                    "location": "在辦公室",
                },
                "reason": "上線",
            },
            {
                "action": "skip",
                "entry": {
                    "date": "2026/04/21",
                    "start_time": "1830",
                    "end_time": "1930",
                    "hours": 1,
                },
            },
        ]
        leave_plan = []
        ot_cb = mock.Mock()
        with mock.patch(FIND, side_effect=[False, True]):
            ot_ok, ot_total, lv_ok, lv_total = batch_submit(
                portal,
                "http://x",
                overtime_plan,
                leave_plan,
                on_overtime_done=ot_cb,
            )
        self.assertEqual((ot_ok, ot_total, lv_ok, lv_total), (1, 1, 0, 0))
        # Only the submit plan fires the callback, with its status
        ot_cb.assert_called_once_with(overtime_plan[0], CONFIRMED)


class TestDryRunScreenshot(unittest.TestCase):
    def test_overtime_dry_run_takes_screenshot(self):
        import tempfile
        from pathlib import Path

        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        portal._run.return_value = ""
        portal.screenshot.return_value = True
        with tempfile.TemporaryDirectory() as d:
            entry = {
                "date": "2026/04/20",
                "start_time": "1830",
                "end_time": "2030",
                "hours": 2,
                "location": "在辦公室",
            }
            ok = submit_overtime(
                portal,
                "http://x",
                entry,
                reason="x",
                dry_run=True,
                dry_run_pause_secs=0,
                screenshot_dir=Path(d),
                screenshot_seq=1,
            )
            self.assertTrue(ok)
            portal.screenshot.assert_called_once()
            saved_path = portal.screenshot.call_args[0][0]
            self.assertTrue(saved_path.endswith("001-overtime-20260420-1830-2030.png"))

    def test_no_screenshot_when_dir_is_none(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        portal._run.return_value = ""
        entry = {
            "date": "2026/04/20",
            "start_time": "1830",
            "end_time": "2030",
            "hours": 2,
            "location": "在辦公室",
        }
        submit_overtime(portal, "http://x", entry, reason="x", dry_run=True, dry_run_pause_secs=0)
        portal.screenshot.assert_not_called()


class TestDryRun(unittest.TestCase):
    def test_overtime_skips_submit_click(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        # Sentinel snapshot — wouldn't match the verify heuristic, but
        # dry_run never asks for verification so the result stays True.
        portal._run.return_value = ""
        entry = {
            "date": "2026/04/20",
            "start_time": "1830",
            "end_time": "2030",
            "hours": 2,
            "location": "在辦公室",
        }
        ok = submit_overtime(
            portal, "http://x", entry, reason="x", dry_run=True, dry_run_pause_secs=0
        )
        self.assertTrue(ok)
        # No 確定送出 JS — none of the eval calls should contain that string
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertNotIn("確定送出", joined)
        # And no post-submit snapshot read for verification
        snap_calls = [
            c for c in portal._run.call_args_list if c[0] and c[0][0] and c[0][0][0] == "snapshot"
        ]
        self.assertEqual(snap_calls, [])

    def test_leave_skips_submit_click(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},  # open form
            True,  # proxy select
            {"matched": 1, "matches": [{"index": 30, "text": "補休假"}]},
            {"ok": True},  # fill datetime
            None,  # trigger hour calc
            {"ok": True},  # reason fill
        ]
        portal._run.return_value = ""
        entry = {
            "date": "2026/04/20",
            "start_time": "0930",
            "end_time": "1130",
            "hours": 2,
        }
        ok = submit_leave(
            portal,
            "http://x",
            entry,
            leave_type_name="補休假",
            reason="x",
            proxy_employee="P",
            dry_run=True,
            dry_run_pause_secs=0,
        )
        self.assertEqual(ok, DRY_RUN)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertNotIn("確定送出", joined)

    def test_batch_submit_propagates_dry_run(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        portal._run.return_value = ""
        overtime_plan = [
            {
                "action": "submit",
                "entry": {
                    "date": "2026/04/20",
                    "start_time": "1830",
                    "end_time": "2030",
                    "hours": 2,
                    "location": "在辦公室",
                },
                "reason": "x",
            }
        ]
        ot_ok, ot_total, _, _ = batch_submit(
            portal,
            "http://x",
            overtime_plan,
            [],
            dry_run=True,
            dry_run_pause_secs=0,
        )
        self.assertEqual((ot_ok, ot_total), (1, 1))
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertNotIn("確定送出", joined)


class TestPortalListVerification(unittest.TestCase):
    """Regression for the false "提交成功": the Portal silently dropped a
    non-WFH leave without a proxy, the page stayed at 新增 with disabled
    widgets, and the old snapshot heuristic reported success."""

    ENTRY = {"date": "2026/10/08", "start_time": "1200", "end_time": "1900", "hours": 6}

    def _leave_portal(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},  # open form
            True,  # proxy select
            {"matched": 1, "matches": [{"index": 30, "text": "補休假"}]},
            {"ok": True},  # fill datetime
            None,  # trigger
            {"ok": True},  # reason
            None,  # submit
        ]
        # The page a silently-rejected form leaves behind
        portal._run.return_value = (
            "請假單 目前狀態：新增\n- combobox [expanded=false, disabled, ref=e35]: 請選擇"
        )
        return portal

    def test_rejected_page_with_disabled_widgets_is_not_success(self):
        portal = self._leave_portal()
        with mock.patch(FIND, side_effect=[False, False]):
            status = submit_leave(
                portal, "http://x", self.ENTRY, "補休假", "個人事務", proxy_employee="P"
            )
        self.assertEqual(status, UNCONFIRMED)

    def test_non_wfh_without_proxy_is_blocked_before_opening_form(self):
        for dry_run in (False, True):
            portal = mock.Mock()
            with mock.patch(FIND) as find:
                status = submit_leave(
                    portal, "http://x", self.ENTRY, "補休假", "個人事務", dry_run=dry_run
                )
            self.assertEqual(status, BLOCKED)
            find.assert_not_called()
            self.assertEqual(portal.method_calls, [])

    def test_already_pending_form_is_not_resubmitted(self):
        portal = mock.Mock()
        with mock.patch(FIND, return_value=True):
            status = submit_leave(
                portal, "http://x", self.ENTRY, "補休假", "個人事務", proxy_employee="P"
            )
        self.assertEqual(status, ALREADY_PENDING)
        portal.eval_json.assert_not_called()

    def test_unreadable_list_before_submit_skips_entry(self):
        portal = mock.Mock()
        with mock.patch(FIND, side_effect=RuntimeError("eval 失敗")):
            status = submit_overtime(portal, "http://x", self.ENTRY, reason="x")
        self.assertEqual(status, FAILED)
        portal.eval_json.assert_not_called()

    def test_unreadable_list_after_submit_is_unconfirmed(self):
        portal = self._leave_portal()
        with mock.patch(FIND, side_effect=[False, RuntimeError("timeout")]):
            status = submit_leave(
                portal, "http://x", self.ENTRY, "補休假", "個人事務", proxy_employee="P"
            )
        self.assertEqual(status, UNCONFIRMED)

    def test_find_matches_date_and_time_window_in_pending_list(self):
        rows = [
            {"date": "2026/10/08", "start_time": "0900", "end_time": "1200"},
            {"date": "2026/10/08", "start_time": "1200", "end_time": "1900"},
        ]
        with mock.patch("lib.portal.approvals.fetch_form_entries", return_value=rows) as fetch:
            self.assertTrue(_find_in_portal(mock.Mock(), "http://x", "請假單", self.ENTRY))
            other = {**self.ENTRY, "end_time": "1800"}
            self.assertFalse(_find_in_portal(mock.Mock(), "http://x", "請假單", other))
        self.assertEqual(fetch.call_args[0][2:], ("請假單", "未處理"))

    def test_batch_counts_only_confirmed(self):
        plans = [
            {"action": "submit", "entry": {**self.ENTRY, "start_time": t}, "reason": "x"}
            for t in ("1200", "1300")
        ]
        portal = _make_portal()
        cb = mock.Mock()
        with mock.patch(FIND, side_effect=[False, True, False, False]):
            ot_ok, ot_total, _, _ = batch_submit(portal, "http://x", plans, [], on_overtime_done=cb)
        self.assertEqual((ot_ok, ot_total), (1, 2))
        self.assertEqual([c[0][1] for c in cb.call_args_list], [CONFIRMED, UNCONFIRMED])


if __name__ == "__main__":
    unittest.main()

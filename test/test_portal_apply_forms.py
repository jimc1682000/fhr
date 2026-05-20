"""Tests for `lib/portal/apply_forms.py`.

We mock PortalSession; verify the right JS lands at the right time and
the result flag matches the snapshot heuristic.
"""
import unittest
from unittest import mock

from lib.portal.apply_forms import (
    batch_submit,
    submit_leave,
    submit_overtime,
)


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
        ok = submit_overtime(portal, "http://x", entry, reason="上線部署")
        self.assertTrue(ok)
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
        ok = submit_overtime(portal, "http://x", entry, reason="供應鏈事件")
        self.assertTrue(ok)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertIn("在外地", joined)

    def test_verify_failure_returns_false(self):
        portal = _make_portal(snapshot_after="something else")
        entry = {
            "date": "2026/04/20", "start_time": "1830", "end_time": "2030",
            "hours": 2, "location": "在辦公室",
        }
        self.assertFalse(submit_overtime(portal, "http://x", entry, reason="x"))


class TestSubmitLeave(unittest.TestCase):
    def test_wfh_skips_proxy(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},                  # open form
            {"matched": 1, "matches": [{"index": 27, "text": "異地辦公(8hr一週)"}]},
            {"ok": True},                       # fill datetime
            None,                               # trigger
            {"ok": True},                       # reason
            None,                               # click submit
        ]
        portal._run.return_value = "請假單  主管簽核"
        entry = {
            "date": "2026/04/24", "start_time": "0930",
            "end_time": "1830", "hours": 9,
        }
        ok = submit_leave(portal, "http://x", entry,
                          leave_type_name="異地辦公(8hr一週)",
                          reason="WFH",
                          proxy_employee="賴菁甫")
        self.assertTrue(ok)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertNotIn("AGENT_ID_ddlDelegate", joined)

    def test_non_wfh_selects_proxy(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},                  # open form
            {"ok": True},                       # proxy select
            {"matched": 1, "matches": [{"index": 30, "text": "補休假"}]},
            {"ok": True},                       # fill datetime
            None,                               # trigger
            {"ok": True},                       # reason
            None,                               # submit
        ]
        portal._run.return_value = "請假單  主管簽核"
        entry = {"date": "2026/04/20", "start_time": "0930",
                 "end_time": "1130", "hours": 2}
        ok = submit_leave(portal, "http://x", entry,
                          leave_type_name="補休假",
                          reason="個人事務",
                          proxy_employee="賴菁甫")
        self.assertTrue(ok)
        joined = "\n".join(str(c[0]) for c in portal.eval_json.call_args_list)
        self.assertIn("AGENT_ID_ddlDelegate", joined)

    def test_unmatched_leave_type_returns_false(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},
            {"matched": 0, "matches": []},
        ]
        portal._run.return_value = "請假單"
        entry = {"date": "2026/04/20", "start_time": "0930",
                 "end_time": "1030", "hours": 1}
        ok = submit_leave(portal, "http://x", entry,
                          leave_type_name="不存在的假別",
                          reason="x")
        self.assertFalse(ok)

    def test_ambiguous_leave_type_returns_false(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"success": True},
            {"matched": 2, "matches": [
                {"index": 1, "text": "補休假"},
                {"index": 2, "text": "補休假B"},
            ]},
        ]
        portal._run.return_value = "請假單"
        entry = {"date": "2026/04/20", "start_time": "0930",
                 "end_time": "1030", "hours": 1}
        ok = submit_leave(portal, "http://x", entry,
                          leave_type_name="補休假",
                          reason="x")
        self.assertFalse(ok)


class TestBatchSubmit(unittest.TestCase):
    def test_callbacks_fire_per_entry(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"success": True}
        portal._run.return_value = "加班單  主管簽核"
        overtime_plan = [
            {"action": "submit",
             "entry": {"date": "2026/04/20", "start_time": "1830",
                       "end_time": "2030", "hours": 2, "location": "在辦公室"},
             "reason": "上線"},
            {"action": "skip",
             "entry": {"date": "2026/04/21", "start_time": "1830",
                       "end_time": "1930", "hours": 1}},
        ]
        leave_plan = []
        ot_cb = mock.Mock()
        ot_ok, ot_total, lv_ok, lv_total = batch_submit(
            portal, "http://x", overtime_plan, leave_plan,
            on_overtime_done=ot_cb,
        )
        self.assertEqual((ot_ok, ot_total, lv_ok, lv_total), (1, 1, 0, 0))
        # Only the submit plan fires the callback
        ot_cb.assert_called_once()


if __name__ == "__main__":
    unittest.main()

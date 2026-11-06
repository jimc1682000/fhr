"""Invariant tests for form submission against a stateful fake Portal.

The fake replaces only `PortalSession._run` (the agent-browser boundary), so
the real `submit_leave` / `batch_submit` code runs. `_find_in_portal` reads
the fake's ground truth. Invariants, whatever the Portal does:

  - a status in OK_STATUSES ⇔ the form exists on the Portal (no false success)
  - re-running after a timeout never creates a duplicate form
"""

import json
import re
import unittest
from unittest import mock

from lib.portal import apply_forms as af
from lib.portal.client import AgentBrowserError, PortalSession

WFH = "異地辦公"
LEAVE_TYPES = ["補休假", "特休假", WFH]
ENTRY = {"date": "2026/10/08", "start_time": "1200", "end_time": "1900", "hours": 6}


class FakePortal(PortalSession):
    """Stateful stand-in for the HR Portal.

    reject_all: the backend silently drops every form (page stays at 新增),
        standing in for any constraint we don't know about yet.
    timeout_after_commit: the first 確定送出 creates the form but the CLI
        reports a timeout.
    """

    def __init__(self, forms, *, reject_all=False, timeout_after_commit=False):
        super().__init__(session="fake", check=False)
        self.forms = forms
        self.reject_all = reject_all
        self.timeout_after_commit = timeout_after_commit
        self.draft = {}

    def _run(self, args, *, timeout=None, capture=True):  # noqa: ARG002
        cmd = args[0]
        if cmd == "open":
            self.draft = {}
            return ""
        if cmd == "dialog":
            raise AgentBrowserError("no dialog open")
        if cmd == "snapshot":
            return "請假單 目前狀態：新增\n- combobox [expanded=false, disabled, ref=e35]: 請選擇"
        if cmd == "eval":
            return self._eval(args[1])
        return ""

    def _eval(self, js):
        if "AGENT_ID_ddlDelegate" in js:
            self.draft["proxy"] = re.search(r"includes\('(.+?)'\)", js).group(1)
            return "true"
        if "LEAVE_CLASS_DropDownList1" in js:
            name = re.search(r"const name = '(.+?)';", js).group(1)
            self.draft["leave_type"] = name
            return json.dumps({"matched": 1, "matches": [{"index": 0, "text": name}]})
        if "StartDate" in js:
            self.draft["date"], self.draft["start"], _, self.draft["end"] = re.findall(
                r"\[(?:sd|st|ed|et),'(.*?)'\]", js
            )
            return '{"ok": true}'
        if "確定送出" in js:
            return self._submit()
        if "c.textContent.trim() ===" in js:
            return '{"success": true}'
        return "true"

    def _submit(self):
        if self.reject_all:
            return "true"
        self.forms.append((self.draft["date"], self.draft["start"], self.draft["end"]))
        if self.timeout_after_commit:
            self.timeout_after_commit = False
            raise AgentBrowserError("agent-browser timed out after 30s")
        return "true"


def _submit(portal, leave_type="補休假", proxy="P"):
    def find(_portal, _base, _form, entry):
        return (entry["date"], entry["start_time"], entry["end_time"]) in portal.forms

    with mock.patch.object(af, "_find_in_portal", side_effect=find):
        return af.submit_leave(portal, "http://x", ENTRY, leave_type, "個人事務", proxy)


class TestSubmitInvariants(unittest.TestCase):
    def test_ok_status_iff_form_exists(self):
        for reject_all in (False, True):
            for leave_type in LEAVE_TYPES:
                for proxy in ("P", None):
                    with self.subTest(reject_all=reject_all, leave_type=leave_type, proxy=proxy):
                        forms = []
                        status = _submit(
                            FakePortal(forms, reject_all=reject_all), leave_type, proxy
                        )
                        self.assertEqual(status in af.OK_STATUSES, len(forms) == 1, status)
                        self.assertLessEqual(len(forms), 1)

    def test_unknown_silent_rejection_is_unconfirmed_not_success(self):
        forms = []
        self.assertEqual(_submit(FakePortal(forms, reject_all=True)), af.UNCONFIRMED)
        self.assertEqual(forms, [])

    def test_rerun_after_timeout_does_not_duplicate(self):
        forms = []
        with self.assertRaises(AgentBrowserError):
            _submit(FakePortal(forms, timeout_after_commit=True))
        self.assertEqual(len(forms), 1)
        # The caller retries (e.g. the user re-runs portal-apply)
        self.assertEqual(_submit(FakePortal(forms)), af.ALREADY_PENDING)
        self.assertEqual(len(forms), 1)


if __name__ == "__main__":
    unittest.main()

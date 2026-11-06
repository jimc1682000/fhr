"""Invariant tests for form submission against a stateful fake Portal.

The fake replaces only `PortalSession._run` (the agent-browser boundary), so
the real submission and approvals parser code runs against raw list rows. Invariants, whatever the Portal does:

  - a status in OK_STATUSES ⇔ the form exists on the Portal (no false success)
  - re-running after a timeout never creates a duplicate form
"""

import json
import re
import unittest
from unittest import mock

from lib.portal import apply_forms as af
from lib.portal.client import AgentBrowserError, PortalSession

WFH = "異地辦公(8hr一週)"
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
        self.leave_options = ["補休假", "特休假", "事假(含家庭照顧假)", WFH, "異地辦公(12hr一週)"]
        self.forms = forms
        self.reject_all = reject_all
        self.timeout_after_commit = timeout_after_commit
        self.draft = {}
        self.list_page = False
        self.status_filter = "全部"

    def _run(self, args, *, timeout=None, capture=True):  # noqa: ARG002
        cmd = args[0]
        if cmd == "open":
            self.list_page = "Search/Default.aspx" in args[1]
            self.draft = {}
            return ""
        if cmd == "dialog":
            raise AgentBrowserError("no dialog open")
        if cmd == "select" and args[1] == "@s":
            self.status_filter = args[2]
        if cmd == "snapshot" and self.list_page:
            return '- combobox [ref=s]\n- combobox [ref=f]\n- button "提交" [ref=q]'
        if cmd == "snapshot":
            return "請假單 目前狀態：新增\n- combobox [expanded=false, disabled, ref=e35]: 請選擇"
        if cmd == "eval":
            return self._eval(args[1])
        return ""

    def _eval(self, js):
        if "tbWorkSheetDataList_" in js:
            rows = []
            for i, form in enumerate(self.forms):
                if (
                    self.status_filter != "全部"
                    and form.get("status", "未處理") != self.status_filter
                ):
                    continue
                start = f"{form['start_time'][:2]}:{form['start_time'][2:]}"
                end = f"{form['end_time'][:2]}:{form['end_time'][2:]}"
                text = (
                    f"(開始時間 StartDate) {form['date']} {start}"
                    f"(結束時間 EndDate) {form.get('end_date', form['date'])} {end}\n"
                )
                if form.get("leave_type"):
                    text += f"可申請假勤項目：{form['leave_type']}\n"
                rows.append(
                    {"id": str(i), "wsdinfotext": text, "status_cell": form.get("status", "未處理")}
                )
            return json.dumps({"totalPages": 1, "page": 0, "rows": rows})
        if "AGENT_ID_ddlDelegate" in js:
            self.draft["proxy"] = re.search(r"includes\('(.+?)'\)", js).group(1)
            return "true"
        if "LEAVE_CLASS_DropDownList1" in js:
            name = re.search(r"const name = '(.+?)';", js).group(1)
            exact = [o for o in self.leave_options if o == name]
            names = exact or [o for o in self.leave_options if name in o]
            if len(names) == 1:
                self.draft["leave_type"] = names[0]
            return json.dumps(
                {
                    "matched": len(names),
                    "matches": [{"index": self.leave_options.index(o), "text": o} for o in names],
                }
            )
        if "StartDate" in js:
            self.draft["date"], self.draft["start"], self.draft["end_date"], self.draft["end"] = (
                re.findall(r"\[(?:sd|st|ed|et),'(.*?)'\]", js)
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
        self.forms.append(
            {
                "date": self.draft["date"],
                "start_time": self.draft["start"],
                "end_date": self.draft["end_date"],
                "end_time": self.draft["end"],
                "leave_type": self.draft["leave_type"],
            }
        )
        if self.timeout_after_commit:
            self.timeout_after_commit = False
            raise AgentBrowserError("agent-browser timed out after 30s")
        return "true"


def _submit(portal, leave_type="補休假", proxy="P"):
    return af.submit_leave(portal, "http://fake.invalid", ENTRY, leave_type, "個人事務", proxy)


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

    def test_other_leave_type_or_end_date_is_not_existing_success(self):
        for other in ({"leave_type": "特休假"}, {"end_date": "2026/10/09"}, {"leave_type": None}):
            with self.subTest(other=other):
                forms = [{**ENTRY, "leave_type": "補休假", **other}]
                status = _submit(FakePortal(forms, reject_all=True))
                self.assertNotIn(status, af.OK_STATUSES)
                self.assertEqual(len(forms), 1)

    def test_approved_form_is_not_resubmitted(self):
        forms = [{**ENTRY, "leave_type": "補休假", "status": "已核准"}]
        self.assertEqual(_submit(FakePortal(forms)), af.ALREADY_PENDING)
        self.assertEqual(len(forms), 1)

    def test_rejected_and_withdrawn_forms_allow_new_submission(self):
        for status in ("已駁回", "退件", "已撤回", "流程結束(駁回)"):
            forms = [{**ENTRY, "leave_type": "補休假", "status": status}]
            self.assertEqual(_submit(FakePortal(forms)), af.CONFIRMED)
            self.assertEqual(len(forms), 2)

    def test_unreadable_or_repeated_list_never_submits(self):
        row = {
            "id": "r0",
            "wsdinfotext": "(開始時間 StartDate) 2026/10/01 12:00"
            "(結束時間 EndDate) 2026/10/01 19:00\n可申請假勤項目：補休假",
            "status_cell": "未處理",
        }
        for pages in (
            [{"totalPages": 1, "page": 0, "rows": [{"id": "bad", "wsdinfotext": "?"}]}],
            [
                {
                    "totalPages": 1,
                    "page": 0,
                    "rows": [{"id": "bad", "wsdinfotext": "(開始時間 StartDate) 2026/10/01 12:00"}],
                }
            ],
            [{"totalPages": 2, "page": i, "rows": [row]} for i in range(2)],
            [{"totalPages": 2, "page": 0, "rows": [row]}] * 2,
        ):
            with self.subTest(pages=pages):
                portal = FakePortal([])
                original = portal._eval
                page_iter = iter(pages)

                def evaluate(js, page_iter=page_iter, original=original):
                    if "tbWorkSheetDataList_" in js:
                        return json.dumps(next(page_iter))
                    return original(js)

                with mock.patch.object(portal, "_eval", side_effect=evaluate):
                    self.assertEqual(_submit(portal), af.FAILED)
                self.assertEqual(portal.forms, [])

    def test_timeout_without_form_reconciles_as_unconfirmed(self):
        portal = FakePortal([])
        with mock.patch.object(portal, "_submit", side_effect=AgentBrowserError("timeout")):
            with self.assertRaises(AgentBrowserError) as cm:
                _submit(portal)
        self.assertEqual(cm.exception.status, af.UNCONFIRMED)
        self.assertEqual(portal.forms, [])

    def test_unknown_silent_rejection_is_unconfirmed_not_success(self):
        forms = []
        self.assertEqual(_submit(FakePortal(forms, reject_all=True)), af.UNCONFIRMED)
        self.assertEqual(forms, [])

    def test_rerun_after_timeout_does_not_duplicate(self):
        forms = []
        with self.assertRaises(AgentBrowserError) as cm:
            _submit(FakePortal(forms, timeout_after_commit=True))
        self.assertEqual(cm.exception.status, af.CONFIRMED)
        self.assertEqual(len(forms), 1)
        # The caller retries (e.g. the user re-runs portal-apply)
        self.assertEqual(_submit(FakePortal(forms)), af.ALREADY_PENDING)
        self.assertEqual(len(forms), 1)


if __name__ == "__main__":
    unittest.main()

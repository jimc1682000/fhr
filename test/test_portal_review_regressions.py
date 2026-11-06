"""交叉 review 的離線驗收：狀態、假別、分頁與 hook 命令辨識。"""

import importlib.util
import json
import unittest
from unittest import mock

from lib.portal import apply_forms as af, approvals
from test.test_claude_hook_post_portal_apply import HOOK
from test.test_portal_submit_reliability import ENTRY, FakePortal

spec = importlib.util.spec_from_file_location("post_portal_apply", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def submit(portal, leave_type="補休假"):
    return af.submit_leave(portal, "http://fake.invalid", ENTRY, leave_type, "個人事務", "P")


class TestReviewSubmission(unittest.TestCase):
    def test_withdrawn_form_is_not_success(self):
        forms = [{**ENTRY, "leave_type": "補休假", "status": "流程停止(抽單)"}]
        self.assertEqual(submit(FakePortal(forms, reject_all=True)), af.UNCONFIRMED)
        self.assertEqual(len(forms), 1)

    def test_withdrawn_form_allows_new_submission(self):
        forms = [{**ENTRY, "leave_type": "補休假", "status": "流程停止(抽單)"}]
        self.assertEqual(submit(FakePortal(forms)), af.CONFIRMED)
        self.assertEqual(len(forms), 2)

    def test_unknown_status_never_submits(self):
        for status in ("", "新狀態", "流程停止(未知原因)", "駁回後待確認"):
            with self.subTest(status=status):
                forms = [{**ENTRY, "leave_type": "補休假", "status": status}]
                self.assertEqual(submit(FakePortal(forms)), af.FAILED)
                self.assertEqual(len(forms), 1)

    def test_observed_active_statuses_prevent_duplicates(self):
        for status in ("主管簽核 - 一階主管", "流程結束(完成)", "未處理", "已核准"):
            with self.subTest(status=status):
                forms = [{**ENTRY, "leave_type": "補休假", "status": status}]
                self.assertEqual(submit(FakePortal(forms)), af.ALREADY_PENDING)
                self.assertEqual(len(forms), 1)

    def test_short_name_does_not_duplicate_existing_form(self):
        forms = [{**ENTRY, "leave_type": "事假(含家庭照顧假)", "status": "流程結束(完成)"}]
        self.assertEqual(submit(FakePortal(forms), "事假"), af.ALREADY_PENDING)
        self.assertEqual(len(forms), 1)

    def test_short_name_fresh_submission_is_confirmed_and_retry_skips(self):
        forms = []
        self.assertEqual(submit(FakePortal(forms), "事假"), af.CONFIRMED)
        self.assertEqual(forms[0]["leave_type"], "事假(含家庭照顧假)")
        self.assertEqual(submit(FakePortal(forms), "事假"), af.ALREADY_PENDING)
        self.assertEqual(len(forms), 1)

    def test_unmatched_or_ambiguous_alias_never_submits(self):
        for name in ("不存在的假別", "假", "異地辦公"):
            with self.subTest(name=name):
                forms = []
                self.assertEqual(submit(FakePortal(forms), name), af.FAILED)
                self.assertEqual(forms, [])

    def test_exact_option_wins_over_substring(self):
        portal = FakePortal([])
        portal.leave_options = ["補休假", "補休假B"]
        self.assertEqual(submit(portal), af.CONFIRMED)
        self.assertEqual(portal.forms[0]["leave_type"], "補休假")

    def test_missing_leave_type_is_not_parsed_twice(self):
        portal = FakePortal([{**ENTRY, "status": "未處理"}])
        with mock.patch.object(
            approvals, "parse_wsdinfotext", wraps=approvals.parse_wsdinfotext
        ) as parse:
            self.assertEqual(submit(portal), af.FAILED)
        self.assertEqual(parse.call_count, 1)


class TestReviewPagination(unittest.TestCase):
    def _fetch(self, change):
        portal = FakePortal([{**ENTRY, "leave_type": "補休假"}])
        original = portal._eval

        def evaluate(js):
            raw = original(js)
            if "tbWorkSheetDataList_" in js:
                page = json.loads(raw)
                page.update(change)
                return json.dumps(page)
            return raw

        with mock.patch.object(portal, "_eval", side_effect=evaluate):
            return approvals.fetch_form_entries(portal, "http://fake.invalid", "請假單")

    def test_wrong_page_is_rejected_without_duplicate_rows(self):
        with self.assertRaisesRegex(RuntimeError, "指定頁次"):
            self._fetch({"page": 1})

    def test_empty_later_page_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "分頁內容不完整"):
            # Each page has the requested index, but page 1 is empty.
            portal = FakePortal([])
            with mock.patch.object(
                portal,
                "eval_json",
                side_effect=[
                    {"totalPages": 2, "page": 0, "rows": []},
                    {"totalPages": 2, "page": 1, "rows": []},
                ],
            ):
                approvals.fetch_form_entries(portal, "http://fake.invalid", "請假單")


class TestReviewHook(unittest.TestCase):
    def test_redirections_are_foreground(self):
        for suffix in ("> log.txt 2>&1", "&> log", ">& log", "2>&1", "2>&1 | cat"):
            with self.subTest(suffix=suffix):
                invocations = hook._invocations("fhr portal-apply --auto " + suffix)
                self.assertEqual(len(invocations), 1)
                self.assertFalse(invocations[0][1])

    def test_background_operators(self):
        for suffix in ("&", "& wait", "> log.txt 2>&1 &"):
            with self.subTest(suffix=suffix):
                self.assertTrue(hook._invocations("fhr portal-apply --auto " + suffix)[0][1])

    def test_wrappers_are_recognized(self):
        for prefix in (
            "uv run fhr",
            "timeout 30 fhr",
            "timeout 30s uv run fhr",
            "python3 -m attendance_analyzer",
        ):
            with self.subTest(prefix=prefix):
                self.assertEqual(
                    hook._invocations(prefix + " portal-apply --auto"), [(["--auto"], False)]
                )

    def test_wrapper_help_and_echo_do_not_invoke(self):
        for command in (
            "echo uv run fhr portal-apply",
            "uv --help run fhr portal-apply",
            "timeout --help fhr portal-apply",
        ):
            with self.subTest(command=command):
                self.assertEqual(hook._invocations(command), [])

"""結果來源驗收。所有送單走 FakePortal，hook 查詢走假的命令。"""

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from lib.commands import portal_apply as apply
from lib.portal import apply_forms as af
from lib.portal.client import AgentBrowserMissing, LoginTimeout
from test import test_portal_apply_helpers as auto_helpers
from test.test_claude_hook_post_portal_apply import HOOK
from test.test_portal_submit_reliability import ENTRY, FakePortal

spec = importlib.util.spec_from_file_location("provenance_hook", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

RUN_ID = "12345678-1234-4234-8234-123456789abc"


class TestResultProvenance(unittest.TestCase):
    def setUp(self):
        self.fixture = auto_helpers.TestRunAutoMode()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = Path(self.fixture.tmp.name)
        self.path = apply._result_path(str(self.fixture.analysis_path))
        self.result = {
            "run_id": RUN_ID,
            "completed": True,
            "overtime": [],
            "leave": [{"entry": ENTRY, "status": "confirmed", "submitted": True, "dry_run": False}],
        }
        self.path.write_text(json.dumps(self.result))
        self.command = f"fhr portal-apply --input {self.fixture.analysis_path}"
        self.home = mock.patch.dict(os.environ, {"HOME": str(self.directory)})
        self.home.start()
        self.addCleanup(self.home.stop)

    def receipt(self):
        return f"結果寫入：{self.path}（run_id={RUN_ID}）\n"

    def call_hook(
        self, stdout="", *, interrupted=False, command=None, exit_code=0, response=None, **fields
    ):
        payload = {
            "hook_event_name": "PostToolUseFailure" if exit_code else "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command or self.command},
            "cwd": str(self.directory),
            # Bash 物件格式來自官方 hooks reference，並非 exit_code 假設。
            "tool_response": {
                "stdout": stdout,
                "stderr": "",
                "interrupted": interrupted,
                "isImage": False,
            },
        }
        if exit_code:
            payload["tool_response"] = None
            payload["error"] = f"Exit code {exit_code}\n{stdout}"
            payload["is_interrupt"] = False
        if response is not None:
            payload["tool_response"] = response
        payload.update(fields)
        output = io.StringIO()
        with (
            mock.patch("sys.stdin", io.StringIO(json.dumps(payload))),
            contextlib.redirect_stdout(output),
            mock.patch.object(hook.subprocess, "run") as check,
        ):
            check.return_value.returncode = 0
            check.return_value.stdout = "沒有需注意項目"
            check.return_value.stderr = ""
            hook.main()
        return output.getvalue(), check

    def assert_no_result(self, stdout="", *, exit_code=0):
        context, check = self.call_hook(stdout, exit_code=exit_code)
        self.assertIn("目前沒有對帳結果", context)
        self.assertIn("不可說任何單已送出或已確認", context)
        self.assertNotIn("以本次 portal-apply 結果檔", context)
        check.assert_not_called()

    def run_apply(self, args, **patches):
        output = io.StringIO()
        forms = []
        real_batch = af.batch_submit

        def fake_batch(_portal, base, ot, lv, **kwargs):
            return real_batch(FakePortal(forms), base, ot, lv, **kwargs)

        with contextlib.ExitStack() as stack:
            for target, value in patches.items():
                stack.enter_context(mock.patch(target, **value))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                self.fixture._run_patched(args, fake_batch)
                rc = 0
            except SystemExit as error:
                rc = error.code
        return rc, output.getvalue(), forms

    def test_auto_background_with_busy_lock_only_reminds(self):
        with apply._apply_lock():
            context, check = self.call_hook(
                response={"stdout": "", "backgroundTaskId": "task-test", "timedOutAfterMs": 1000}
            )
        check.assert_not_called()
        self.assertIn("送單仍在背景執行中，完成後再對帳", context)
        self.assertNotIn("沒有送單", context)

    def test_replayed_receipt_outside_tool_execution_is_rejected(self):
        # 同一 stdout 只有舊收據，run_id 與路徑均吻合也不能歸屬本次。
        now = time.time()
        os.utime(self.path, (now - 10, now - 10))
        context, check = self.call_hook(
            self.receipt(), command=self.command + "; cat apply.log", duration_ms=100
        )
        check.assert_not_called()
        self.assertIn("目前沒有對帳結果", context)

    def test_replayed_receipt_without_duration_is_rejected(self):
        old = time.time() - 3600
        os.utime(self.path, (old, old))
        context, check = self.call_hook(self.receipt())
        check.assert_not_called()
        self.assertIn("目前沒有對帳結果", context)

    def test_future_result_is_rejected(self):
        future = time.time() + 60
        os.utime(self.path, (future, future))
        context, check = self.call_hook(self.receipt(), duration_ms=1000)
        check.assert_not_called()
        self.assertIn("目前沒有對帳結果", context)

    def test_current_receipt_with_duration_is_accepted(self):
        context, check = self.call_hook(self.receipt(), duration_ms=1000)
        check.assert_called_once()
        self.assertIn(RUN_ID, context)

    def test_truncated_output_cannot_claim_nothing_was_submitted(self):
        for exit_code in (0, 5):
            with self.subTest(exit_code=exit_code):
                stdout = ("x" * 30001 + self.receipt())[:30000]
                context, check = self.call_hook(stdout, exit_code=exit_code)
                check.assert_not_called()
                self.assertIn("無法確認是否送單或送了哪些單，目前沒有對帳結果", context)
                self.assertNotIn("沒有送任何單", context)
                self.assertNotIn("沒有送單", context)

    def test_large_snapshot_prioritizes_non_ok_and_keeps_path(self):
        ok = self.result["leave"][0]
        pending = dict(ok, status="unconfirmed", submitted=False)
        pending["entry"] = dict(ENTRY, date="2026/11/07", reason="x" * 20000)
        self.result["leave"] = [ok] * 500 + [pending]
        self.path.write_text(json.dumps(self.result))
        context, check = self.call_hook(self.receipt())
        check.assert_called_once()
        text = json.loads(context)["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text), 10000)
        self.assertIn("總筆數：501", text)
        self.assertIn("confirmed：500", text)
        self.assertIn("unconfirmed：1", text)
        self.assertIn("2026/11/07", text)
        self.assertIn(str(self.path), text)
        self.assertNotIn('"status": "confirmed"', text)

    def test_large_non_ok_snapshot_and_report_stay_bounded(self):
        entry = dict(self.result["leave"][0], status="unconfirmed")
        self.result["leave"] = [entry] * 500
        self.path.write_text(json.dumps(self.result))
        payload = {
            "cwd": str(self.directory),
            "tool_response": {"stdout": self.receipt()},
        }
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(
                hook.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="y" * 20000, stderr=""),
            ),
        ):
            hook._check(payload, ["--input", str(self.fixture.analysis_path)])
        text = json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text), 10000)
        self.assertIn("總筆數：500", text)
        self.assertIn("unconfirmed：500", text)
        self.assertIn("省略", text)
        self.assertIn(str(self.path), text)

    def test_emoji_report_fits_utf16_context_limit(self):
        payload = {
            "cwd": str(self.directory),
            "tool_response": {"stdout": self.receipt()},
        }
        output = io.StringIO()
        with (
            contextlib.redirect_stdout(output),
            mock.patch.object(
                hook.subprocess,
                "run",
                return_value=mock.Mock(returncode=0, stdout="🟢" * 10000, stderr=""),
            ),
        ):
            hook._check(payload, ["--input", str(self.fixture.analysis_path)])
        text = json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 10000)
        self.assertIn(str(self.path), text)
        self.assertIn("省略", text)

    def test_failure_event_returns_context_from_error_receipt(self):
        context, check = self.call_hook(self.receipt(), exit_code=5)
        check.assert_called_once()
        output = json.loads(context)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PostToolUseFailure")
        self.assertIn(RUN_ID, output["additionalContext"])

    def test_failure_event_is_registered(self):
        settings = json.loads((HOOK.parents[1] / "settings.json").read_text())
        self.assertEqual(
            settings["hooks"].get("PostToolUseFailure"),
            settings["hooks"]["PostToolUse"],
        )

    def test_old_result_exit_2(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{
                "lib.commands.portal_apply._resolve_base_url": {
                    "side_effect": RuntimeError("bad args")
                }
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (2, [], before))
        self.assert_no_result(stdout, exit_code=rc)

    def test_old_result_exit_3(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{
                "lib.commands.portal_apply._maybe_sync": {
                    "side_effect": AgentBrowserMissing("missing")
                }
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (3, [], before))
        self.assert_no_result(stdout, exit_code=rc)

    def test_old_result_exit_4(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{"lib.commands.portal_apply._maybe_sync": {"side_effect": LoginTimeout("timeout")}},
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (4, [], before))
        self.assert_no_result(stdout, exit_code=rc)

    def test_old_result_exit_5_never_reads_or_writes_result(self):
        before = self.path.read_bytes()
        with apply._apply_lock():
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("不得讀結果")):
                rc, stdout, forms = self.run_apply(self.fixture._args())
                context, check = self.call_hook(stdout, exit_code=rc)
        self.assertEqual((rc, forms, self.path.read_bytes()), (5, [], before))
        check.assert_not_called()
        self.assertIn("無法確認是否送單或送了哪些單，目前沒有對帳結果", context)
        self.assertNotIn("confirmed / already_pending", context)

    def test_no_items_keeps_old_result_untrusted(self):
        self.fixture.analysis_path.write_text(
            json.dumps({"schema_version": "attendance-analysis/v1", "overtime": [], "leave": []})
        )
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(self.fixture._args())
        self.assertEqual((rc, forms, self.path.read_bytes()), (0, [], before))
        self.assert_no_result(stdout)

    def test_cancel_keeps_old_result_untrusted(self):
        args = self.fixture._args()
        args.auto = False

        def choose(*, plan, **kwargs):
            plan["overtime"].append({"entry": ENTRY, "action": "submit", "reason": "test"})

        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            args,
            **{
                "lib.commands.portal_apply._interactive_overtime": {"side_effect": choose},
                "lib.commands.portal_apply._interactive_leave": {},
                "builtins.input": {"return_value": "n"},
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (0, [], before))
        self.assert_no_result(stdout)

    def test_missing_result(self):
        self.path = self.directory / "missing_apply_result.json"
        self.command = f"fhr portal-apply --input {self.directory / 'missing_analysis.json'}"
        self.assert_no_result(self.receipt())

    def test_partial_result(self):
        self.result["completed"] = False
        self.path.write_text(json.dumps(self.result))
        self.assert_no_result(self.receipt())

    def test_malformed_result(self):
        for content in ('{"run_id":', "[]", '{"completed": true}', "null"):
            with self.subTest(content=content):
                self.path.write_text(content)
                self.assert_no_result(self.receipt())

    def test_wrong_run_id(self):
        self.result["run_id"] = "different-run"
        self.path.write_text(json.dumps(self.result))
        self.assert_no_result(self.receipt())

    def test_invalid_entries(self):
        for entries in ({}, [None], [{"status": "confirmed"}]):
            with self.subTest(entries=entries):
                self.result["leave"] = entries
                self.path.write_text(json.dumps(self.result))
                self.assert_no_result(self.receipt())

    def test_normal_completion_receipt_matches_finalized_result(self):
        args = self.fixture._args()
        args.leave_only = True
        rc, stdout, forms = self.run_apply(args)
        self.assertEqual(rc, 0)
        self.assertEqual(len(forms), 1)
        data = json.loads(self.path.read_text())
        self.assertIs(data.get("completed"), True)
        self.assertNotEqual(data.get("run_id"), RUN_ID)
        self.assertIn(f"結果寫入：{self.path.resolve()}（run_id={data['run_id']}）", stdout)
        context, check = self.call_hook(stdout)
        check.assert_called_once()
        self.assertIn(data["run_id"], context)
        self.assertIn("confirmed", context)

    def test_interrupted_submission_finalizes_only_observed_entries(self):
        args = self.fixture._args()
        args.leave_only = True
        portal = FakePortal([], timeout_after_commit=True)
        real_batch = af.batch_submit

        def interrupted(_portal, base, ot, lv, **kwargs):
            return real_batch(portal, base, ot, lv, **kwargs)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            self.fixture._run_patched(args, interrupted)
        self.assertEqual(stopped.exception.code, 5)
        data = json.loads(self.path.read_text())
        self.assertIs(data.get("completed"), True)
        self.assertEqual(data["leave"][0]["status"], "confirmed")
        self.assertIn(data["run_id"], output.getvalue())
        context, check = self.call_hook(output.getvalue(), exit_code=5)
        check.assert_called_once()
        self.assertIn(data["run_id"], context)

    def test_progress_writes_are_incomplete_without_receipt(self):
        snapshots = []
        real_save = apply._save_results
        output = io.StringIO()

        def save(path, data):
            snapshots.append(json.loads(json.dumps(data)))
            self.assertEqual(output.getvalue(), "")
            real_save(path, data)

        args = self.fixture._args()
        with mock.patch.object(apply, "_save_results", side_effect=save):
            with contextlib.redirect_stdout(output):
                self.fixture._run_patched(args, self.fixture._fake_batch_submit("confirmed"))
        self.assertEqual([s.get("completed") for s in snapshots], [False, False, True])
        self.assertEqual(len({s["run_id"] for s in snapshots}), 1)

    def test_absent_receipt_never_reads_result(self):
        with mock.patch.object(Path, "read_text", return_value="{}") as read:
            self.assert_no_result()
        read.assert_not_called()

    def test_busy_lock_even_with_receipt_never_reads_result(self):
        with apply._apply_lock():
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("不得讀結果")):
                context, check = self.call_hook(self.receipt())
        check.assert_not_called()
        self.assertIn("不可說任何單已送出或已確認", context)
        self.assertNotIn("confirmed / already_pending", context)

    def test_wrong_result_path(self):
        self.command = f"fhr portal-apply --input {self.directory / 'other_analysis.json'}"
        self.assert_no_result(self.receipt())

    def test_dry_run_result_cannot_confirm_submission(self):
        self.result["leave"][0]["dry_run"] = True
        self.path.write_text(json.dumps(self.result))
        self.assert_no_result(self.receipt())

    def test_validated_snapshot_survives_replacement_during_check(self):
        def replace_result(*args, **kwargs):
            self.path.write_text('{"run_id": "another-run"}')
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(hook.subprocess, "run", side_effect=replace_result):
            # 直接呼叫 _check，以觀察查詢期間結果被替換的情況。
            output = io.StringIO()
            payload = {"cwd": str(self.directory), "tool_response": {"stdout": self.receipt()}}
            with contextlib.redirect_stdout(output):
                hook._check(payload, ["--input", str(self.fixture.analysis_path)])
        self.assertIn(RUN_ID, output.getvalue())
        self.assertIn("confirmed", output.getvalue())

    def test_missing_entries_do_not_mean_unconfirmed(self):
        context, _ = self.call_hook(self.receipt())
        self.assertIn("沒出現在結果檔，不代表未確認", context)
        self.assertIn("先前已確認", context)

    def test_multiple_invocations_are_not_attributed_to_one_result(self):
        context, check = self.call_hook(self.receipt(), command=self.command + " ; " + self.command)
        self.assertIn("不可說任何單已送出或已確認", context)
        check.assert_not_called()

    def test_interrupted_tool_response_does_not_authorize_result(self):
        context, check = self.call_hook(self.receipt(), interrupted=True)
        self.assertIn("不可說任何單已送出或已確認", context)
        check.assert_not_called()


class TestAtomicResults(unittest.TestCase):
    def test_replacement_only_exposes_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"old": true}')
            real_replace = os.replace
            observed = []

            def replace(source, destination):
                observed.append((path.read_text(), json.loads(Path(source).read_text())))
                self.assertEqual(Path(source).parent, path.parent)
                real_replace(source, destination)

            with mock.patch.object(apply.os, "replace", side_effect=replace):
                apply._save_results(path, {"completed": True})
            self.assertEqual(observed, [('{"old": true}', {"completed": True})])
            self.assertEqual(json.loads(path.read_text()), {"completed": True})

"""送單提醒的事件、指令辨識與無副作用驗收。"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "post_portal_apply.py"
spec = importlib.util.spec_from_file_location("post_portal_apply", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class TestPostPortalApplyHook(unittest.TestCase):
    def _run(self, command="fhr portal-apply --auto", event="PostToolUse", **fields):
        payload = {
            "hook_event_name": event,
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": "confirmed"},
        }
        payload.update(fields)
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            check=True,
        )
        self.assertEqual(proc.stderr, "")
        return json.loads(proc.stdout)["hookSpecificOutput"] if proc.stdout else None

    def test_both_events_return_matching_event_and_same_reminder(self):
        for event, response in (("PostToolUse", {}), ("PostToolUseFailure", None)):
            with self.subTest(event=event):
                output = self._run(event=event, tool_response=response, error="Exit code 5")
                self.assertEqual(output["hookEventName"], event)
                self.assertEqual(output["additionalContext"], hook.REMINDER)

    def test_reminder_explains_status_exit_code_and_reconciliation(self):
        context = self._run()["additionalContext"]
        for text in (
            "逐筆狀態與 exit code",
            "confirmed、already_pending",
            "unconfirmed、failed、blocked 都不算",
            "exit 5",
            "fhr portal-check --since <最早日期>",
            "不可以直接重送",
            "任何一筆沒有確認",
            "「已送出」或「簽核中」",
            "已核准的單不會列出",
        ):
            with self.subTest(text=text):
                self.assertIn(text, context)

    def test_background_forms_receive_reminder_for_both_events(self):
        forms = (
            {"tool_input": {"command": "fhr portal-apply", "run_in_background": True}},
            {"tool_response": {"backgroundTaskId": "fake-task", "stdout": ""}},
            {"tool_input": {"command": "fhr portal-apply &"}},
        )
        for event in ("PostToolUse", "PostToolUseFailure"):
            for fields in forms:
                with self.subTest(event=event, fields=fields):
                    output = self._run(event=event, **fields)
                    self.assertEqual(output["additionalContext"], hook.REMINDER)
                    self.assertIn("必須等它完成、看完輸出再對帳", output["additionalContext"])
                    self.assertIn("不可以說成「沒有送單」", output["additionalContext"])

    def test_cli_aliases_paths_quotes_and_wrappers(self):
        for prefix in (
            "fhr",
            "'/some path/fhr'",
            "./attendance_analyzer.py",
            "python3 attendance_analyzer.py",
            "python3 '/some path/attendance_analyzer.py'",
            "python -m attendance_analyzer",
            "uv run fhr",
            "uv run python -m attendance_analyzer",
            "timeout 120 fhr",
            "timeout 120s uv run fhr",
            "X=1 timeout 1.5m uv run python3 attendance_analyzer.py",
        ):
            for subcommand in ("portal-apply", "portal_apply"):
                with self.subTest(prefix=prefix, subcommand=subcommand):
                    self.assertIsNotNone(self._run(f"{prefix} {subcommand} --input=missing.json"))

    def test_help_and_dry_run_are_ignored(self):
        for command in (
            "fhr portal-apply --help",
            "fhr portal_apply -h",
            "python3 attendance_analyzer.py portal-apply --dry-run",
            "uv run fhr portal-apply --dry-run",
            "timeout 120 fhr portal-apply --help",
            "uv --help run fhr portal-apply",
            "timeout --help fhr portal-apply",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command))

    def test_unrelated_commands_and_text_are_ignored(self):
        for command in (
            "ls",
            "fhr portal-check",
            "grep -n portal-apply README.md",
            "grep 'fhr portal-apply' README.md",
            "echo fhr portal-apply",
            "echo uv run fhr portal-apply",
            "printf '%s' 'python -m attendance_analyzer portal_apply'",
            "python unrelated.py portal-apply",
            "python -m unrelated portal-apply",
            "fhr portal-apply-extra",
            "",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self._run(command))

    def test_unrelated_events_and_tools_are_ignored(self):
        self.assertIsNone(self._run(tool_name="Read"))
        self.assertIsNone(self._run(event="PreToolUse"))
        self.assertIsNone(self._run(tool_input=None))

    def test_shell_separators_redirection_and_continuation(self):
        for command in (
            "cd /tmp\nfhr portal-apply",
            "cd /tmp &&\\\n fhr portal-apply",
            "sleep 1 &\nfhr portal-apply",
            "fhr portal-apply > log 2>&1",
            "fhr portal-apply &> log",
            "fhr portal-apply 2>&1 | cat",
            "fhr portal-apply --dry-run-pause-secs 1",
            "fhr portal-apply --help; fhr portal-apply --auto",
            "fhr portal-apply; fhr portal-apply",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self._run(command))

    def test_truncated_missing_or_replayed_output_does_not_change_reminder(self):
        for response in (
            None,
            {"stdout": ""},
            {"stdout": "結果寫入：/missing/result.json（run_id=old）"},
            {"stdout": "truncated", "interrupted": True},
        ):
            with self.subTest(response=response):
                self.assertEqual(
                    self._run(tool_response=response)["additionalContext"], hook.REMINDER
                )

    def test_reminder_does_not_read_files_lock_or_launch_commands(self):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "fhr portal-apply --input=/missing/analysis.json"},
            "tool_response": {"stdout": "結果寫入：/missing/result.json（run_id=old）"},
        }
        with (
            mock.patch("sys.stdin", io.StringIO(json.dumps(payload))),
            contextlib.redirect_stdout(io.StringIO()) as output,
            mock.patch("builtins.open", side_effect=AssertionError("不得讀寫檔案")),
            mock.patch.object(Path, "open", side_effect=AssertionError("不得讀寫檔案")),
            mock.patch("subprocess.run", side_effect=AssertionError("不得執行查詢")),
            mock.patch(
                "lib.commands.portal_apply._apply_lock", side_effect=AssertionError("不得取鎖")
            ),
        ):
            self.assertEqual(hook.main(), 0)
        self.assertEqual(
            json.loads(output.getvalue())["hookSpecificOutput"]["additionalContext"], hook.REMINDER
        )

    def test_malformed_json_and_shell_are_ignored(self):
        self.assertIsNone(self._run("fhr portal-apply '"))
        with (
            mock.patch("sys.stdin", io.StringIO("{")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(hook.main(), 0)
        self.assertEqual(output.getvalue(), "")

    def test_both_events_remain_registered(self):
        settings = json.loads((HOOK.parents[1] / "settings.json").read_text())
        for event in ("PostToolUse", "PostToolUseFailure"):
            self.assertEqual(settings["hooks"][event][0]["matcher"], "Bash")
            self.assertIn(
                "post_portal_apply.py", settings["hooks"][event][0]["hooks"][0]["command"]
            )

"""Tests for `.claude/hooks/post_portal_apply.py` (Claude Code PostToolUse hook).

The real `portal-check` is never run: FHR_PORTAL_CHECK_CMD points at a small
script that records its argv, so we can tell whether and how it was called.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "post_portal_apply.py"


class TestPostPortalApplyHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.calls = self.dir / "calls.txt"
        self.fake = self.dir / "fake_check.py"
        self.fake.write_text(
            "import sys\n"
            f"open({str(self.calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            "print('\\x1b[32m✅ 請假單: 1 筆\\x1b[0m')\n"
            "print('- 2026/10/08 12:00-19:00 補休假 [未處理]')\n"
            "sys.exit(int(sys.argv[3]))\n",
            encoding="utf-8",
        )
        analysis = self.dir / "analysis.json"
        analysis.write_text(
            json.dumps({"overtime": [{"date": "2026/10/09"}], "leave": [{"date": "2026/10/08"}]}),
            encoding="utf-8",
        )

    def _run(self, tool_input, *, tool_name="Bash", check_rc=1, timeout=None):
        env = dict(
            os.environ,
            CLAUDE_PROJECT_DIR=str(self.dir),
            FHR_PORTAL_CHECK_CMD=f"{sys.executable} {self.fake} --since {{since}} {check_rc}",
        )
        if timeout:
            env["FHR_PORTAL_CHECK_TIMEOUT"] = str(timeout)
        payload = {"tool_name": tool_name, "tool_input": tool_input, "cwd": str(self.dir)}
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        out = proc.stdout.strip()
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else None
        calls = self.calls.read_text().splitlines() if self.calls.exists() else []
        return context, calls

    def test_ignores_unrelated_commands(self):
        for tool_input, tool_name in [
            ({"command": "ls"}, "Bash"),
            ({"command": "grep -n portal-apply README.md"}, "Bash"),
            ({"file_path": "x"}, "Read"),
        ]:
            context, calls = self._run(tool_input, tool_name=tool_name)
            self.assertIsNone(context)
            self.assertEqual(calls, [])

    def test_ignores_dry_run_and_help(self):
        for cmd in (
            "python3 attendance_analyzer.py portal-apply --input analysis.json --dry-run",
            "fhr portal-apply --help",
        ):
            context, calls = self._run({"command": cmd})
            self.assertIsNone(context)
            self.assertEqual(calls, [])

    def test_runs_portal_check_from_earliest_input_date(self):
        cmd = "python3 attendance_analyzer.py portal-apply --input analysis.json --auto"
        context, calls = self._run({"command": cmd})
        self.assertEqual(calls, ["--since 2026/10/08 1"])
        self.assertIn("exit 1", context)
        self.assertIn("2026/10/08 12:00-19:00 補休假 [未處理]", context)
        self.assertIn("未確認", context)
        self.assertNotIn("\x1b[", context)

    def test_background_run_only_reminds(self):
        cmd = "fhr portal-apply --input analysis.json --auto"
        context, calls = self._run({"command": cmd, "run_in_background": True})
        self.assertEqual(calls, [])
        self.assertIn("背景", context)
        self.assertIn("portal-check", context)

    def test_failed_check_says_nothing_is_reconciled(self):
        cmd = "fhr portal-apply --input analysis.json"
        context, _ = self._run({"command": cmd}, check_rc=4)
        self.assertIn("沒有成功", context)
        self.assertIn("不可說任何單已送出", context)

    def test_command_tokens_do_not_confuse_echo_or_pause_with_dry_run(self):
        context, calls = self._run({"command": 'echo "fhr portal-apply"'})
        self.assertIsNone(context)
        self.assertEqual(calls, [])
        context, calls = self._run({"command": '"fhr" "portal-apply" --dry-run-pause-secs 3'})
        self.assertIsNotNone(context)
        self.assertEqual(len(calls), 1)

    def test_shell_background_does_not_start_check(self):
        context, calls = self._run({"command": "fhr portal-apply --input analysis.json & wait"})
        self.assertEqual(calls, [])
        self.assertIn("背景", context)

    def test_forwards_context_and_reads_equals_input(self):
        context, calls = self._run(
            {
                "command": '"fhr" portal-apply --input=analysis.json --base-url "https://fake.invalid/portal" --session=test'
            }
        )
        self.assertIn("2026/10/08", context)
        self.assertEqual(
            calls, ["--since 2026/10/08 1 --base-url https://fake.invalid/portal --session test"]
        )

    def test_invalid_timeout_uses_default(self):
        context, calls = self._run({"command": "fhr portal-apply"}, timeout="not-a-number")
        self.assertIsNotNone(context)
        self.assertEqual(len(calls), 1)

    def test_query_failure_is_not_a_portal_list(self):
        context, calls = self._run({"command": "fhr portal-apply"}, check_rc=6)
        self.assertEqual(len(calls), 1)
        self.assertIn("exit 6", context)
        self.assertIn("不可當成對帳證據", context)
        self.assertNotIn("以下是 Portal 的實際清單", context)

    def test_missing_input_falls_back_to_recent_window(self):
        context, calls = self._run({"command": "fhr portal-apply --auto"})
        self.assertEqual(len(calls), 1)
        self.assertRegex(calls[0], r"^--since \d{4}/\d{2}/\d{2} 1$")
        self.assertIsNotNone(context)


if __name__ == "__main__":
    unittest.main()

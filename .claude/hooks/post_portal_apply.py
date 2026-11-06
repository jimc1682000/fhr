#!/usr/bin/env python3
"""Claude Code PostToolUse hook: reconcile with the Portal after `portal-apply`.

When a Bash call ran `portal-apply` (not a dry run), run `portal-check` and hand
its report back to the model as additional context, so "已送出" claims are made
against the Portal's actual list rather than the tool's own message. For a
background run the form submission hasn't finished yet, so we only remind.

Env:
  FHR_PORTAL_CHECK_CMD  override the check command (tests); `{since}` is replaced
  FHR_PORTAL_CHECK_TIMEOUT  seconds, default 150
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*m")
MAX_LINES = 60


def _since(command: str, cwd: Path) -> str:
    """Earliest work date in the --input analysis JSON; else 45 days ago."""
    try:
        args = shlex.split(command)
        path = Path(args[args.index("--input") + 1])
        data = json.loads((path if path.is_absolute() else cwd / path).read_text("utf-8"))
        dates = [e["date"] for k in ("overtime", "leave") for e in data.get(k, []) if e.get("date")]
        if dates:
            return min(dates)
    except (ValueError, IndexError, OSError, KeyError, TypeError, json.JSONDecodeError):
        pass
    return (date.today() - timedelta(days=45)).strftime("%Y/%m/%d")


def _emit(text: str) -> None:
    out = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
    print(json.dumps(out, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") or ""
    # Only an actual CLI invocation, not e.g. `grep portal-apply README.md`
    if not re.search(r"(attendance_analyzer\.py|\bfhr)\s+portal[-_]apply\b", command):
        return 0
    if re.search(r"--dry-run\b|(^|\s)(-h|--help)\b", command):
        return 0

    if tool_input.get("run_in_background"):
        _emit(
            "[fhr hook] portal-apply 在背景執行，送單還沒結束。完成後以結果檔每筆的 status 為準"
            "（只有 confirmed / already_pending 代表單子在 Portal 上），回報前再跑 "
            "`fhr portal-check --since <最早日期>` 對帳；對帳前不可說任何單已送出或簽核中。"
        )
        return 0

    cwd = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    since = _since(command, cwd)
    override = os.environ.get("FHR_PORTAL_CHECK_CMD")
    cmd = (
        shlex.split(override.replace("{since}", since))
        if override
        else [sys.executable, "attendance_analyzer.py", "portal-check", "--since", since]
    )
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
    timeout = int(os.environ.get("FHR_PORTAL_CHECK_TIMEOUT", "150"))
    try:
        proc = subprocess.run(
            cmd, cwd=project, capture_output=True, text=True, timeout=timeout, check=False
        )
        rc, output = proc.returncode, ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))
    except (OSError, subprocess.TimeoutExpired) as e:
        rc, output = None, f"{type(e).__name__}: {e}"

    lines = output.strip().splitlines()[-MAX_LINES:]
    report = "\n".join(lines) or "(沒有輸出)"
    if rc in (0, 1):  # 1 = has pending / rejected forms, expected right after submitting
        _emit(
            f"[fhr hook] portal-apply 之後自動跑了 portal-check --since {since}（exit {rc}）。"
            "以下是 Portal 的實際清單。回報任何單「已送出／簽核中」前，必須在這份清單裡逐筆找到；"
            f"找不到的請回報為「未確認」，不要直接重送。\n{report}"
        )
    else:
        _emit(
            f"[fhr hook] portal-apply 之後的 portal-check 沒有成功（exit {rc}），目前沒有對帳結果。"
            "不可說任何單已送出或簽核中；請先處理登入或錯誤後再跑 portal-check。\n" + report
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

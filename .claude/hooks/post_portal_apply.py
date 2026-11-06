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


def _option(args: list[str], name: str) -> str | None:
    for idx, arg in enumerate(args):
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
        if arg == name and idx + 1 < len(args):
            return args[idx + 1]
    return None


def _invocations(command: str) -> list[tuple[list[str], bool]]:
    """辨識簡單命令的位置，避免把 echo 等指令的參數誤當成執行。"""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    found = []
    segment: list[str] = []
    for token in [*tokens, ";"]:
        if token not in (";", "&&", "||", "|", "&", "(", ")", "\n"):
            segment.append(token)
            continue
        args = segment
        segment = []
        while args and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", args[0]):
            args = args[1:]
        if not args:
            continue
        while args:
            executable = Path(args[0]).name
            if executable == "uv" and len(args) > 2 and args[1] == "run":
                args = args[2:]
            elif (
                executable == "timeout"
                and len(args) > 2
                and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", args[1])
            ):
                args = args[2:]
            else:
                break
        executable = Path(args[0]).name
        start = 1
        if executable.startswith("python"):
            if len(args) >= 3 and args[1:3] == ["-m", "attendance_analyzer"]:
                start = 3
            elif len(args) >= 2 and Path(args[1]).name == "attendance_analyzer.py":
                start = 2
            else:
                continue
        elif executable not in ("fhr", "attendance_analyzer.py"):
            continue
        if len(args) > start and args[start] in ("portal-apply", "portal_apply"):
            found.append((args[start + 1 :], token == "&"))
    return found


def _since(args: list[str], cwd: Path) -> str:
    """Earliest work date in the --input analysis JSON; else 45 days ago."""
    try:
        path = Path(_option(args, "--input") or "")
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
    invocations = [
        (args, background)
        for args, background in _invocations(command)
        if not any(arg in ("--dry-run", "-h", "--help") for arg in args)
    ]
    if not invocations:
        return 0
    if tool_input.get("run_in_background") or any(bg for _, bg in invocations):
        _emit(
            "[fhr hook] portal-apply 在背景執行，送單還沒結束。完成後以結果檔每筆的 status 為準"
            "（只有 confirmed / already_pending 代表單子在 Portal 上），回報前再跑 "
            "`fhr portal-check --since <最早日期>` 對帳；對帳前不可說任何單已送出或簽核中。"
        )
        return 0
    for args, _ in invocations:
        _check(payload, args)
    return 0


def _check(payload: dict, args: list[str]) -> None:
    cwd = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    since = _since(args, cwd)
    override = os.environ.get("FHR_PORTAL_CHECK_CMD")
    cmd = (
        shlex.split(override.replace("{since}", since))
        if override
        else [sys.executable, "attendance_analyzer.py", "portal-check", "--since", since]
    )
    for option in ("--base-url", "--session"):
        value = _option(args, option)
        if value is not None:
            cmd.extend([option, value])
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
    try:
        timeout = int(os.environ.get("FHR_PORTAL_CHECK_TIMEOUT", "150"))
        if timeout <= 0:
            timeout = 150
    except ValueError:
        timeout = 150
    try:
        proc = subprocess.run(
            cmd, cwd=project, capture_output=True, text=True, timeout=timeout, check=False
        )
        rc, output = proc.returncode, ANSI.sub("", (proc.stdout or "") + (proc.stderr or ""))
    except (OSError, subprocess.TimeoutExpired) as e:
        rc, output = None, f"{type(e).__name__}: {e}"

    lines = output.strip().splitlines()[-MAX_LINES:]
    report = "\n".join(lines) or "(沒有輸出)"
    if rc in (0, 1):  # 1 表示查詢成功但有待處理事項；查詢失敗為 6
        _emit(
            f"[fhr hook] portal-apply 之後自動跑了 portal-check --since {since}（exit {rc}）。"
            "以下是 Portal 的實際清單。回報任何單「已送出／簽核中」前，必須在這份清單裡逐筆找到；"
            f"找不到的請回報為「未確認」，不要直接重送。\n{report}"
        )
    else:
        if rc == 6:
            report = "Portal 清單查詢失敗，以下錯誤輸出不可當成對帳證據。\n" + report
        _emit(
            f"[fhr hook] portal-apply 之後的 portal-check 沒有成功（exit {rc}），目前沒有對帳結果。"
            "不可說任何單已送出或簽核中；請先處理登入或錯誤後再跑 portal-check。\n" + report
        )


if __name__ == "__main__":
    sys.exit(main())

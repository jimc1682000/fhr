#!/usr/bin/env python3
"""Claude Code PostToolUse hook: reconcile with the Portal after `portal-apply`.

When a Bash call ran `portal-apply` (not a dry run), run `portal-check` and hand
its attention-only report back as supplemental context. Per-entry results from
this apply remain the primary confirmation evidence, including approved forms
absent from that report. Background submissions only receive a reminder.

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
RESULT_GUIDANCE = (
    "以本次 portal-apply 結果檔每筆的 status 為主要依據；"
    "confirmed / already_pending 代表送單時已確認 Portal 上有有效單，未必仍在簽核中。"
    "其他狀態請回報為「未確認」，不要直接重送。"
    "先前已確認、這次跳過的單不會列出；沒出現在結果檔，不代表未確認，"
    "也不可據此聲稱本次已送出或已確認，請另查先前證據。"
)
LOCK_BUSY = "[fhr hook] 另一個 portal-apply 或 portal-check 正在執行，稍後再對帳。"
NO_RESULT = (
    "本次 portal-apply 沒有產生可核對的結果（或沒有送任何單），目前沒有對帳結果，"
    "不可說任何單已送出或已確認。不要直接重送，先確認執行狀態。"
)
RECEIPT = re.compile(r"^結果寫入：(.+)（run_id=([0-9a-f-]{36})）$", re.MULTILINE)


def _receipt(payload: dict) -> tuple[Path, str] | None:
    # 官方 Bash tool_response 是物件，含 stdout／stderr／interrupted／isImage。
    # https://code.claude.com/docs/en/hooks#posttooluse-decision-control
    response = payload.get("tool_response")
    if not isinstance(response, dict) or response.get("interrupted"):
        return None
    stdout = response.get("stdout")
    if not isinstance(stdout, str):
        return None
    matches = RECEIPT.findall(stdout)
    if len(matches) != 1:
        return None
    path, run_id = matches[0]
    return (Path(path), run_id) if Path(path).is_absolute() else None


def _current_result(receipt: tuple[Path, str], args: list[str], cwd: Path) -> dict | None:
    path, run_id = receipt
    input_path = _option(args, "--input")
    if input_path:
        source = cwd / input_path
        expected = source.with_name(source.stem.replace("analysis", "apply_result") + ".json")
        if path.resolve() != expected.resolve():
            return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(data, dict)
        or data.get("run_id") != run_id
        or data.get("completed") is not True
    ):
        return None
    for kind in ("overtime", "leave"):
        entries = data.get(kind)
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or not isinstance(entry.get("entry"), dict)
                or not all(
                    isinstance(entry["entry"].get(k), str)
                    for k in ("date", "start_time", "end_time")
                )
                or not isinstance(entry.get("status"), str)
                or not isinstance(entry.get("submitted"), bool)
                or entry.get("dry_run") is not False
            ):
                return None
    return data


def _option(args: list[str], name: str) -> str | None:
    for idx, arg in enumerate(args):
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
        if arg == name and idx + 1 < len(args):
            return args[idx + 1]
    return None


def _invocations(command: str) -> list[tuple[list[str], bool]]:
    """辨識簡單命令的位置，避免把 echo 等指令的參數誤當成執行。"""
    # 換行在 shell 裡等同命令分隔；先接回續行，再把換行換成前後有空白的 `;`，
    # 避免和 `&` 等標點黏成同一個 token。
    command = command.replace("\\\n", " ").replace("\n", " ; ")
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
            "[fhr hook] portal-apply 在背景執行，送單還沒結束。完成後"
            + "須另行核對該次結果；目前不可說任何單已送出或已確認。"
            + "再跑 `fhr portal-check --since <最早日期>` 補充查詢需注意的單。"
        )
        return 0
    if len(invocations) != 1:
        _emit("[fhr hook] 同一工具呼叫包含多次 portal-apply，無法唯一歸屬結果。" + NO_RESULT)
        return 0
    for args, _ in invocations:
        _check(payload, args)
    return 0


def _check(payload: dict, args: list[str]) -> None:
    # Hook 可從其他 cwd 啟動；鎖的來源必須與此 checkout 的 portal-apply 相同。
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from lib.commands.portal_apply import ApplyInProgress, _apply_lock

    receipt = _receipt(payload)
    cwd = Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    try:
        with _apply_lock():
            if receipt is None:
                _emit("[fhr hook] " + NO_RESULT)
                return
            results = _current_result(receipt, args, cwd)
            if results is None:
                _emit("[fhr hook] " + NO_RESULT)
                return
    except ApplyInProgress:
        message = "本次沒有送單，目前沒有對帳結果。" if receipt is None else "尚未核對本次結果。"
        _emit(LOCK_BUSY + message + "不可說任何單已送出或已確認。")
        return
    # 用鎖內讀到的快照回報，避免後續程序替換固定路徑造成錯誤歸屬。
    guidance = (
        RESULT_GUIDANCE + "已核對的本次結果快照：" + json.dumps(results, ensure_ascii=False) + "\n"
    )
    # portal-check 會重新取鎖並持有到查詢結束，涵蓋此處釋放後的競爭。
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
            + guidance
            + "以下報告只列出需要注意的單，作為補充；已核准的單不會列出，"
            f"沒出現在報告裡不代表沒送出。\n{report}"
        )
    elif rc == 5:
        _emit(LOCK_BUSY + guidance)
    else:
        if rc == 6:
            report = "Portal 清單查詢失敗，以下錯誤輸出不可當成對帳證據。\n" + report
        _emit(
            f"[fhr hook] portal-apply 之後的 portal-check 沒有成功（exit {rc}），目前沒有對帳結果。"
            + guidance
            + "請先處理登入或錯誤後再跑 portal-check 補充查詢。\n"
            + report
        )


if __name__ == "__main__":
    sys.exit(main())

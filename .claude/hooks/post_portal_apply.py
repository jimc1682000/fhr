#!/usr/bin/env python3
"""送單後只提醒結果判讀與人工對帳，不讀檔、不取鎖、不執行查詢。"""

import json
import re
import shlex
import sys
from pathlib import Path

REMINDER = (
    "[fhr hook] 結果以 portal-apply 印出的逐筆狀態與 exit code 為準。"
    "只有 confirmed、already_pending 代表送單時已確認 Portal 上有有效單，未必仍在簽核中；"
    "unconfirmed、failed、blocked 都不算。"
    "exit 5 代表有未確認的單、送出中斷，或另一個 portal-apply／portal-check 正在執行。"
    "回報前先跑 fhr portal-check --since <最早日期> 對帳，不可以直接重送。"
    "若 run_in_background、tool_response.backgroundTaskId 或 shell 的 & 表示背景執行，"
    "送單可能還在進行，必須等它完成、看完輸出再對帳，不可以說成「沒有送單」。"
    "任何一筆沒有確認，就不可以把該筆或整批回報為「已送出」或「簽核中」。"
    "portal-check 只列需注意的單，已核准的單不會列出，報告缺單不推翻已確認的逐筆結果。"
)


def _is_apply(command: str) -> bool:
    command = command.replace("\\\n", " ").replace("\n", " ; ")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return False
    args = []
    for token in [*tokens, ";"]:
        if token not in (";", "&&", "||", "|", "&", "(", ")"):
            args.append(token)
            continue
        segment, args = args, []
        while segment and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", segment[0]):
            segment = segment[1:]
        while len(segment) > 2:
            executable = Path(segment[0]).name
            if (executable == "uv" and segment[1] == "run") or (
                executable == "timeout" and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", segment[1])
            ):
                segment = segment[2:]
            else:
                break
        if segment and Path(segment[0]).name.startswith("python"):
            segment = segment[1:]
            if segment[:2] == ["-m", "attendance_analyzer"]:
                segment = ["attendance_analyzer.py", *segment[2:]]
        if (
            len(segment) > 1
            and Path(segment[0]).name in ("fhr", "attendance_analyzer.py")
            and segment[1] in ("portal-apply", "portal_apply")
            and not any(arg in ("--dry-run", "-h", "--help") for arg in segment[2:])
        ):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    event = payload.get("hook_event_name")
    if event not in ("PostToolUse", "PostToolUseFailure") or payload.get("tool_name") != "Bash":
        return 0
    if _is_apply((payload.get("tool_input") or {}).get("command") or ""):
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": event, "additionalContext": REMINDER}},
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

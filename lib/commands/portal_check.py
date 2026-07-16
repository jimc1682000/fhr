"""`fhr portal-check` — pre-flight before submitting a new batch of forms.

Queries the Portal's eWorkFlow Search page for two states that need the
user's attention **before** applying the next wave of 加班 / 請假 forms:

  - 已駁回 (rejected)  → decide whether to re-submit
  - 未處理 (in-flow)   → still waiting on an approver; don't pile new forms on top

Anything else (已核准 / withdrawn) is terminal and irrelevant to the gate,
so we only surface these two buckets. Read-only against the Portal — it
never writes forms or mutates the state cache.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

# Portal 狀態 dropdown values we treat as "needs attention".
REJECTED_STATUS = "已駁回"
PENDING_STATUS = "未處理"


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "portal-check",
        aliases=["portal_check"],
        help="送單前先行確認:列出被駁回 / 仍在簽核中的加班・請假單 (需 agent-browser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 檢查全部歷史
  fhr portal-check

  # 只看某月之後的單子 (下一波送單前的常用範圍)
  fhr portal-check --since 2026/05

送單流程建議先跑此指令,乾淨再 fhr portal-apply。需在 .env 設定 EHR_URL。
        """,
    )
    parser.add_argument(
        "--since",
        help="只列出假勤日 >= 此日期的單 (YYYY/MM 或 YYYY/MM/DD);預設列出全部",
    )
    parser.add_argument(
        "--kinds",
        nargs="+",
        default=["overtime", "leave"],
        choices=["overtime", "leave"],
        help="要檢查哪些表單種類 (預設全部)",
    )
    parser.add_argument("--base-url", help="EHR base URL (預設讀 env EHR_URL)")
    parser.add_argument("--session", help="agent-browser session 名稱 (預設 'fhr')")
    parser.add_argument("--debug", action="store_true", help="啟用 debug 日誌")
    return parser


def _resolve_base_url(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url.rstrip("/")
    raw = os.environ.get("EHR_URL", "").rstrip("/")
    if not raw:
        raise RuntimeError("找不到 EHR_URL — 請在 .env 設定 `EHR_URL=...` 或傳 --base-url")
    for suffix in ("/LoginFOrginal.asp", "/LoginFOpen.asp"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw


def filter_since(entries: list[dict], since: str | None) -> list[dict]:
    """Keep entries whose 假勤日 (`date`, YYYY/MM/DD) is >= `since`.

    `since` may be a prefix like ``2026/05`` — lexical comparison on the
    zero-padded YYYY/MM/DD format sorts correctly. ``None`` keeps all."""
    if not since:
        return list(entries)
    return [e for e in entries if e.get("date", "") >= since]


_KIND_ZH = {"overtime": "加班單", "leave": "請假單"}


def _fmt_entry(kind: str, e: dict) -> str:
    span = f"{e.get('start_time', '')}~{e.get('end_time', '')}".strip("~")
    hours = e.get("hours")
    hours_s = f"{hours}h" if hours is not None else "?h"
    extra = e.get("leave_type") or e.get("location") or ""
    reason = e.get("reason") or ""
    status = e.get("status") or ""
    bits = [f"[{_KIND_ZH.get(kind, kind)}]", e.get("date", "?"), span, hours_s]
    if extra:
        bits.append(extra)
    if status:
        bits.append(f"[{status}]")
    line = "  ・" + " | ".join(b for b in bits if b)
    if reason:
        line += f"  — {reason}"
    return line


def format_report(
    rejected: dict[str, list[dict]],
    pending: dict[str, list[dict]],
    since: str | None,
) -> tuple[str, bool]:
    """Build the human report. Returns (text, clean) where clean is True
    when nothing needs attention."""
    scope = f"(假勤日 >= {since})" if since else "(全部歷史)"
    n_rej = sum(len(v) for v in rejected.values())
    n_pen = sum(len(v) for v in pending.values())
    lines = [f"# 🚦 送單前先行確認 {scope}", ""]

    if n_rej == 0 and n_pen == 0:
        lines.append("✅ 乾淨:沒有被駁回、也沒有仍在簽核中的單。可以進下一波送單。")
        return "\n".join(lines), True

    if n_rej:
        lines.append(f"❌ 被駁回 {n_rej} 筆 — 請評估是否重新申請:")
        for kind, items in rejected.items():
            lines.extend(_fmt_entry(kind, e) for e in items)
        lines.append("")
    if n_pen:
        lines.append(f"⏳ 仍在簽核中/未處理 {n_pen} 筆 — 建議等流程結束再疊新單:")
        for kind, items in pending.items():
            lines.extend(_fmt_entry(kind, e) for e in items)
        lines.append("")
    lines.append("⚠️ 有需要處理的項目,建議先解決再送下一波。")
    return "\n".join(lines), False


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.env import load as load_env
    from lib.portal import approvals
    from lib.portal.client import (
        AgentBrowserMissing,
        LoginTimeout,
        PortalSession,
        ensure_login,
    )

    if args.debug:
        logger.setLevel(logging.DEBUG)

    load_env()

    try:
        base_url = _resolve_base_url(args)
    except RuntimeError as e:
        logger.error("❌ %s", e)
        sys.exit(2)

    kinds = tuple(args.kinds)
    try:
        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            rejected_raw = approvals.fetch_all_applied_forms(
                portal, base_url, kinds=kinds, status_zh=REJECTED_STATUS
            )
            pending_raw = approvals.fetch_all_applied_forms(
                portal, base_url, kinds=kinds, status_zh=PENDING_STATUS
            )
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)
    except Exception as e:
        logger.error("❌ Portal check 失敗: %s", e)
        sys.exit(1)

    rejected = {k: filter_since(v, args.since) for k, v in rejected_raw.items()}
    pending = {k: filter_since(v, args.since) for k, v in pending_raw.items()}

    report, _clean = format_report(rejected, pending, args.since)
    for line in report.splitlines():
        logger.info("%s", line)

"""`fhr portal-sync` — mirror Portal-submitted forms into the state cache.

Truth = Portal's eWorkFlow Search page. We scrape both 加班單 and 請假單,
parse each row's `wsdinfotext`, and overwrite the `applied_forms` block on
`AttendanceStateManager` so future runs (`fhr portal-apply`, `fhr analyze`)
can dedup against the local mirror.

This subcommand is idempotent — running it twice in a row produces no diff
beyond `last_full_sync`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "portal-sync",
        aliases=["portal_sync"],
        help="把 Portal 已申請的加班/請假單同步到本地 state cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  fhr portal-sync --user JimmyChen

需在 .env 設定 EHR_URL (或傳 --base-url)。state 預設寫到 ./attendance_state.json
        """,
    )
    parser.add_argument("--user", required=True, help="state cache 上的使用者名稱")
    parser.add_argument(
        "--kinds",
        nargs="+",
        default=["overtime", "leave"],
        choices=["overtime", "leave"],
        help="要同步哪些表單種類 (預設全部)",
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
        raise RuntimeError(
            "找不到 EHR_URL — 請在 .env 設定 `EHR_URL=...` 或傳 --base-url"
        )
    for suffix in ("/LoginFOrginal.asp", "/LoginFOpen.asp"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw


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
    from lib.state import AttendanceStateManager

    if args.debug:
        logger.setLevel(logging.DEBUG)

    load_env()

    try:
        base_url = _resolve_base_url(args)
    except RuntimeError as e:
        logger.error("❌ %s", e)
        sys.exit(2)

    try:
        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            entries_by_kind = approvals.fetch_all_applied_forms(
                portal, base_url, kinds=tuple(args.kinds)
            )
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)
    except Exception as e:
        logger.error("❌ Portal sync 失敗: %s", e)
        sys.exit(1)

    sm = AttendanceStateManager(read_only=False)
    synced_at = datetime.now().isoformat(timespec="seconds")
    sm.replace_applied_forms(args.user, entries_by_kind, synced_at)
    sm.save_state()

    for kind, entries in entries_by_kind.items():
        logger.info("✅ %s: %d 筆", kind, len(entries))
    logger.info("💾 已寫入 state cache (synced_at=%s)", synced_at)

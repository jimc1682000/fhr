"""`fhr portal-balances` — print leave-balance table from the Portal.

Opens the 請假單 form and reads both the items panel (補休 / 事假 /
有薪病假 / 半薪病假 / 異地辦公 ...) plus the 特休統計 panel. Useful
for cascade allocation planning (see `fhr portal-apply --interactive`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "portal-balances",
        aliases=["portal_balances"],
        help="顯示 Portal 上的假別餘額表 (含特休)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", help="EHR base URL (預設讀 env EHR_URL)")
    parser.add_argument("--session", help="agent-browser session 名稱")
    parser.add_argument(
        "--json", action="store_true", dest="as_json", help="輸出 JSON 而不是表格"
    )
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
    from lib.portal import balances as bal
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

    try:
        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            data = bal.fetch_balances(portal, base_url)
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)
    except Exception as e:
        logger.error("❌ 抓取餘額失敗: %s", e)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(bal.format_balance_table(data))

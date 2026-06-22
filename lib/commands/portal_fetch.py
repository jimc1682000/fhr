"""`fhr portal fetch` — scrape 全部刷卡資料 → fhr-native .txt.

Wraps `lib/portal/attendance.fetch_to_txt()` with .env-driven config
and date-range CLI flags. The output file is named in the
`YYYYMM-[YYYYMM-]<user>-出勤資料.txt` convention so the analyzer can
parse the user/date metadata from the filename (see
`lib/filename.py`).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path


def _parse_date(value: str) -> date:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"無法解析日期 {value!r}（預期 YYYY/MM/DD 或 YYYY-MM-DD）")


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "portal-fetch",
        aliases=["portal_fetch"],
        help="從 104 EHR Portal 抓出勤紀錄 → fhr 可吃的 .txt (需 agent-browser)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 抓本月,自動命名為 YYYYMM-<user>-出勤資料.txt 放到 ./tmp/
  fhr portal-fetch --user JimmyChen

  # 指定日期範圍
  fhr portal-fetch --user JimmyChen \\
      --date-s 2026/04/01 --date-e 2026/05/31

需在 .env 設定 EHR_URL（之後若擴增其他欄位再補）。
        """,
    )
    parser.add_argument("--user", required=True, help="檔名 user 段（會出現在輸出檔名）")
    parser.add_argument("--date-s", dest="date_s", type=_parse_date, help="起始日 (預設本月 1 日)")
    parser.add_argument(
        "--date-e", dest="date_e", type=_parse_date, help="結束日 (預設本月最後一日)"
    )
    parser.add_argument("--out", help="輸出 .txt 路徑 (預設 ./tmp/<auto>.txt)")
    parser.add_argument("--session", help="agent-browser session 名稱 (預設 'fhr')")
    parser.add_argument("--base-url", help="EHR base URL (預設讀 env EHR_URL)")
    parser.add_argument("--debug", action="store_true", help="啟用 debug 日誌")
    return parser


def _default_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = today.replace(day=1)
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        end = today.replace(month=today.month + 1, day=1)
    return start, _prev_day(end)


def _prev_day(d: date) -> date:
    from datetime import timedelta

    return d - timedelta(days=1)


def _default_out(user: str, start: date, end: date) -> Path:
    if start.year == end.year and start.month == end.month:
        stem = f"{start.year}{start.month:02d}-{user}-出勤資料.txt"
    else:
        stem = f"{start.year}{start.month:02d}-{end.year}{end.month:02d}-{user}-出勤資料.txt"
    return Path("tmp") / stem


def _resolve_base_url(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url.rstrip("/")
    raw = os.environ.get("EHR_URL", "").rstrip("/")
    if not raw:
        raise RuntimeError("找不到 EHR_URL — 請在 .env 設定 `EHR_URL=...` 或傳 --base-url")
    # `.env` may carry a full login URL like .../LoginFOrginal.asp; strip the
    # trailing page so the rest of the code can append paths.
    for suffix in ("/LoginFOrginal.asp", "/LoginFOpen.asp"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.env import load as load_env
    from lib.portal import attendance as att
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

    start, end = (args.date_s, args.date_e)
    if not start or not end:
        d_start, d_end = _default_range()
        start = start or d_start
        end = end or d_end
    if start > end:
        logger.error("❌ --date-s 不可晚於 --date-e (%s > %s)", start, end)
        sys.exit(2)

    out_path = Path(args.out) if args.out else _default_out(args.user, start, end)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            count = att.fetch_to_txt(
                portal,
                base_url,
                str(out_path),
                start_year=start.year,
                start_month=start.month,
                end_year=end.year,
                end_month=end.month,
            )
        logger.info("✅ %s (%d 筆)", out_path, count)
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)
    except Exception as e:
        logger.error("❌ 錯誤: %s", e)
        sys.exit(1)

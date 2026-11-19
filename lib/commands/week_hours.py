"""`fhr week-hours` — weekly work hours for timesheets, from Portal forms.

A weekday counts as 8h, minus leave-form hours, plus overtime-form hours;
national holidays count as 0. Reads the Portal-mirrored `applied_forms`
in the state cache (run a full `fhr portal-sync` first; a cache missing
either form kind is refused). An optional attendance .txt only flags days
with neither a punch nor a form, or outside the file's date range.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta


def _parse_date(value: str) -> date:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"無法解析日期 {value!r}（預期 YYYY/MM/DD 或 YYYY-MM-DD）")


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "week-hours",
        aliases=["week_hours"],
        help="依 Portal 假單／加班單計算週工時（工時表 TTL／請假／加班）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 上一個完整工作週
  fhr week-hours --user ExampleUser

  # 指定週（給該週任一天），並用出勤檔標出沒打卡的日子
  fhr week-hours --user ExampleUser --week 2033/06/21 \\
      --attendance tmp/203306-ExampleUser-出勤資料.txt

規則：平日 8h − 請假 ＋ 加班；國定假日 0。異地辦公／在家工作／忘刷卡算工時；公假算請假。
抽單、駁回、退件、已撤回的單不計；簽核中的單照計並標註。跨日的單依起訖時間分到各天。
資料來自 state cache，先跑 fhr portal-sync（加班單、請假單都要同步過）。
        """,
    )
    parser.add_argument("--user", required=True, help="state cache 使用者")
    parser.add_argument("--week", type=_parse_date, help="該週任一天 (預設：週五已過的最近一週)")
    parser.add_argument("--attendance", help="出勤 .txt，用來標出無打卡、無假單的日子")
    parser.add_argument("--json", action="store_true", dest="as_json", help="輸出 JSON")
    parser.add_argument("--debug", action="store_true", help="啟用 debug 日誌")
    return parser


def _punch_days(path: str) -> tuple[set[date], tuple[date, date] | None]:
    """Dates with a punch, and the first/last date the file covers."""
    from lib.parser import parse_line

    days: set[date] = set()
    covered: list[date] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parsed = parse_line(line.rstrip("\n"))
            if not parsed or parsed[0] is None:
                continue
            scheduled, actual = parsed[0], parsed[1]
            covered.append(scheduled.date())
            if actual:
                days.add(scheduled.date())
    return days, ((min(covered), max(covered)) if covered else None)


FORM_KINDS = ("leave", "overtime")


def _unsynced_kinds(applied: dict) -> list[str]:
    """Form kinds this cache can't vouch for.

    A kind counts only when portal-sync recorded its sync time and its list
    is present; caches from before per-kind sync times need a fresh sync."""
    by_kind = applied.get("synced_at_by_kind")
    if not isinstance(by_kind, dict):
        by_kind = {}
    return [k for k in FORM_KINDS if not by_kind.get(k) or not isinstance(applied.get(k), list)]


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.env import load as load_env
    from lib.holidays import HolidayService
    from lib.portal.statuses import is_dead_status
    from lib.state import AttendanceStateManager
    from lib.week_hours import (
        compute_week,
        default_week_start,
        display_hours,
        form_span,
        format_week,
        week_start,
    )

    if args.debug:
        logger.setLevel(logging.DEBUG)
    load_env()

    start = week_start(args.week) if args.week else default_week_start(date.today())
    end = start + timedelta(days=7)

    sm = AttendanceStateManager(read_only=True)
    applied = sm.get_applied_forms(args.user)
    if not isinstance(applied, dict) or not applied:
        logger.error("❌ state cache 沒有 %s 的 applied_forms — 先跑 fhr portal-sync", args.user)
        sys.exit(1)
    missing = _unsynced_kinds(applied)
    if missing:
        logger.error(
            "❌ state cache 沒同步過 %s 的 %s，週工時會少算 — 先跑 fhr portal-sync --user %s"
            "（不要加 --kinds）",
            args.user,
            "、".join(missing),
            args.user,
        )
        sys.exit(1)
    last_sync = applied.get("last_full_sync", "")
    by_kind = applied.get("synced_at_by_kind") or {}
    if by_kind and len(set(by_kind.values())) > 1:
        logger.warning(
            "⚠️ 加班單、請假單不是同一次同步（%s），建議重跑完整 portal-sync",
            "、".join(f"{k} {v}" for k, v in sorted(by_kind.items())),
        )
    elif last_sync:
        logger.info("applied_forms 最後同步：%s", last_sync)

    leave_forms = applied.get("leave", [])
    overtime_forms = applied.get("overtime", [])
    # Multi-day forms are apportioned over their whole span, so holidays are
    # needed for every year a form touching this week covers.
    years = {start.year, (end - timedelta(days=1)).year}
    for form in leave_forms:
        if is_dead_status(form.get("status")):
            continue
        f_start, f_end = form_span(form)
        if f_start.date() < end and f_end.date() >= start:
            years.update(range(f_start.year, f_end.year + 1))
    holiday_service = HolidayService()
    holidays = holiday_service.load_years(years)

    punch_days = punch_range = None
    if args.attendance:
        punch_days, punch_range = _punch_days(args.attendance)

    try:
        week = compute_week(
            start,
            leave_forms,
            overtime_forms,
            holidays,
            punch_days=punch_days,
            punch_range=punch_range,
        )
    except ValueError as e:
        logger.error("❌ %s", e)
        sys.exit(1)
    for year in sorted(holiday_service.fallback_years):
        week.warnings.append(f"{year} 年國定假日只載入基本固定假日，平日假日可能漏算")
    for warning in week.warnings:
        logger.warning("⚠️ 總計不完整：%s", warning)

    if args.as_json:
        out = {
            "week_start": start.isoformat(),
            "ttl": display_hours(week.ttl),
            "leave": display_hours(week.leave),
            "overtime": display_hours(week.overtime),
            "complete": week.complete,
            "warnings": week.warnings,
            "last_full_sync": last_sync,
            "days": [
                {
                    "date": d.day.isoformat(),
                    "hours": display_hours(d.total),
                    "leave": display_hours(d.leave),
                    "overtime": display_hours(d.overtime),
                    "notes": d.notes,
                }
                for d in week.days
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_week(week))

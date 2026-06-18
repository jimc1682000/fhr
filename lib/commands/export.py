"""`fhr export` — analyze a file and emit a versioned interop JSON.

Currently supports a single target (`code-agent-hr`), which produces
`attendance-analysis/v1` JSON consumable by code_agent_hr's
`apply_forms.py`. Future targets register here as additional `--to`
values."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime


def _parse_date(value: str) -> date:
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"無法解析日期 {value!r}（預期 YYYY/MM/DD 或 YYYY-MM-DD）"
    )


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "export",
        help="把分析結果輸出成下游工具吃的 JSON 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 分析 + 輸出 attendance-analysis/v1 JSON 給 code_agent_hr 用
  fhr export --to=code-agent-hr 202604-202605-JimmyChen-出勤資料.txt \\
      --out=tmp/analysis.json --cutoff 2026/04/17 --today 2026/05/19
        """,
    )
    parser.add_argument("filepath", help="考勤檔案路徑（同 `fhr analyze`）")
    parser.add_argument(
        "--to",
        required=True,
        choices=["code-agent-hr"],
        help="目標格式 (= schema 名稱)",
    )
    parser.add_argument("--out", required=True, help="輸出 JSON 路徑")
    parser.add_argument(
        "--cutoff",
        type=_parse_date,
        default=None,
        help="排除此日期(含)以前的條目；通常設為上一次申請的最後日期",
    )
    parser.add_argument(
        "--today",
        type=_parse_date,
        default=None,
        help="排除此日期之後的條目（用來剔除未來的 WFH 自動建議）",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help=(
            "啟用增量分析 (預設關閉)。export 預設走完整分析,因為下游 portal-apply"
            " 走 applied_forms dedup,不該被 analyzer state cache 影響。"
        ),
    )
    parser.add_argument("--debug", action="store_true", help="啟用 debug 模式")
    return parser


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import AttendanceAnalyzer, logger
    from lib.exporters import code_agent_hr as exporter

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        analyzer = AttendanceAnalyzer(debug=args.debug)
        # Default to full analysis so the export payload always represents
        # what the input file says, regardless of attendance_state.json
        # contents from earlier `analyze` runs. Dedup against already-
        # submitted forms is portal-apply's job (state.applied_forms).
        incremental = bool(args.incremental)
        if incremental:
            logger.info("📂 正在解析考勤檔案... (增量分析模式 — 顯式 --incremental)")
        else:
            logger.info("📂 正在解析考勤檔案... (完整分析模式)")
        analyzer.parse_attendance_file(args.filepath, incremental=incremental)
        analyzer.group_records_by_day()
        analyzer.analyze_attendance()

        if args.to == "code-agent-hr":
            options = exporter.ExportOptions(
                cutoff_date=args.cutoff,
                today=args.today,
                schedule_start_hhmm=analyzer.config.schedule_start.replace(":", ""),
                schedule_end_hhmm=analyzer.config.schedule_end.replace(":", ""),
            )
            payload = exporter.write(args.out, analyzer.issues, options)
            s = payload["summary"]
            logger.info(
                "✅ %s (%d 加班 / %d 小時, %d 請假 / %d 小時, %d skipped)",
                args.out,
                s["overtime_count"],
                s["overtime_hours"],
                s["leave_count"],
                s["leave_hours"],
                len(payload["skipped"]),
            )
        else:
            logger.error("❌ 未支援的 --to=%s", args.to)
            sys.exit(2)

    except Exception as e:
        logger.error("❌ 錯誤: %s", e)
        sys.exit(1)

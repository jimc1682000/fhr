"""Export fhr analyzer issues as `attendance-analysis/v1` JSON.

Consumed by code_agent_hr's `apply_forms.py` (and any future fhr v2
`portal apply` invocation that wants to round-trip through the schema
for inspection). See `docs/schema/attendance-analysis-v1.md`.

Time math:
  - overtime: hours = floor(duration_minutes / 60), >= 1
  - late / early_leave: hours = ceil(duration_minutes / 60), >= 1
  - WFH: full-day 0930-1830 / 9h (synthesised)
  - full_day (平日整日請假): 0930-1830 / 8h (午休不計)
  - end_time = start_time + hours * 1h  (NOT actual punch time;
    WFH / full_day use schedule_start~schedule_end directly)

Filters:
  - drop entries on or before `cutoff_date` (last applied form)
  - drop entries strictly after `today`
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from lib.schema import stamp

SCHEMA_VERSION = "attendance-analysis/v1"

_TIME_RANGE_RE = re.compile(r"^\s*(\d{2}):(\d{2})\s*~\s*(\d{2}):(\d{2})\s*$")


@dataclass
class ExportOptions:
    """Filter / shape knobs for the exporter."""

    cutoff_date: date | None = None  # drop entries with date <= cutoff
    today: date | None = None  # drop entries with date > today
    schedule_start_hhmm: str = "0930"  # WFH default start
    schedule_end_hhmm: str = "1830"  # WFH default end
    overtime_reason: str = "工作需要"
    leave_reason: str = "personal matter"
    wfh_reason: str = "WFH"
    overtime_location: str = "在辦公室"


def _to_hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}{minute:02d}"


def _parse_time_range(time_range: str) -> tuple[str, str] | None:
    m = _TIME_RANGE_RE.match(time_range or "")
    if not m:
        return None
    return _to_hhmm(int(m.group(1)), int(m.group(2))), _to_hhmm(
        int(m.group(3)), int(m.group(4))
    )


def _end_from_start_and_hours(start_hhmm: str, hours: int) -> str:
    sh, sm = int(start_hhmm[:2]), int(start_hhmm[2:])
    total = sh * 60 + sm + hours * 60
    return _to_hhmm(total // 60, total % 60)


def _to_date(issue_date) -> date:
    if isinstance(issue_date, datetime):
        return issue_date.date()
    if isinstance(issue_date, date):
        return issue_date
    raise TypeError(f"unsupported issue.date type: {type(issue_date).__name__}")


def _date_str(d: date) -> str:
    return d.strftime("%Y/%m/%d")


def issues_to_analysis(
    issues: Iterable,
    options: ExportOptions | None = None,
) -> dict:
    """Render an iterable of fhr `Issue` objects as a v1 analysis payload.

    The payload is dictionary-shaped — caller picks JSON / dict use.
    """
    opts = options or ExportOptions()
    overtime: list[dict] = []
    leave: list[dict] = []
    skipped: list[dict] = []

    for issue in issues:
        # Lazy import to keep the exporter standalone-testable without
        # pulling the whole analyzer just for the enum.
        from attendance_analyzer import IssueType

        d = _to_date(issue.date)
        d_str = _date_str(d)

        if opts.cutoff_date and d <= opts.cutoff_date:
            skipped.append(
                {"date": d_str, "type": _zh_type(issue.type), "reason": "<= cutoff"}
            )
            continue
        if opts.today and d > opts.today:
            skipped.append(
                {"date": d_str, "type": _zh_type(issue.type), "reason": "future"}
            )
            continue

        if issue.type == IssueType.OVERTIME:
            entry = _make_overtime(issue, opts, d_str, skipped)
            if entry:
                overtime.append(entry)
        elif issue.type == IssueType.LATE:
            entry = _make_leave_from_late(issue, opts, d_str, skipped, type_hint="late")
            if entry:
                leave.append(entry)
        elif issue.type == IssueType.EARLY_LEAVE:
            entry = _make_leave_from_late(
                issue, opts, d_str, skipped, type_hint="early_leave"
            )
            if entry:
                leave.append(entry)
        elif issue.type == IssueType.WFH:
            leave.append(_make_wfh(opts, d_str))
        elif issue.type == IssueType.WEEKDAY_LEAVE:
            leave.append(_make_full_day_leave(issue, opts, d_str))
        # FORGET_PUNCH etc. are not actionable through this schema today —
        # silently ignored. Future schema bumps can add them.

    payload = {
        "cutoff_date": _date_str(opts.cutoff_date) if opts.cutoff_date else None,
        "overtime": overtime,
        "leave": leave,
        "skipped": skipped,
        "summary": {
            "overtime_count": len(overtime),
            "overtime_hours": sum(e["hours"] for e in overtime),
            "leave_count": len(leave),
            "leave_hours": sum(e["hours"] for e in leave),
        },
    }
    stamp(payload, SCHEMA_VERSION)
    # Reorder so schema_version is first when serialized.
    return {"schema_version": payload.pop("schema_version"), **payload}


def _zh_type(issue_type) -> str:
    return getattr(issue_type, "value", str(issue_type))


def _make_overtime(
    issue, opts: ExportOptions, d_str: str, skipped: list
) -> dict | None:
    rng = _parse_time_range(issue.time_range)
    if not rng:
        skipped.append({"date": d_str, "type": "加班", "reason": "no time"})
        return None
    start, _actual_end = rng
    hours = int(issue.duration_minutes) // 60
    if hours < 1:
        skipped.append({"date": d_str, "type": "加班", "reason": "<1h"})
        return None
    return {
        "date": d_str,
        "start_time": start,
        "end_time": _end_from_start_and_hours(start, hours),
        "hours": hours,
        "location": opts.overtime_location,
        "reason": opts.overtime_reason,
    }


def _make_leave_from_late(
    issue, opts: ExportOptions, d_str: str, skipped: list, *, type_hint: str
) -> dict | None:
    rng = _parse_time_range(issue.time_range)
    if not rng:
        zh = "遲到" if type_hint == "late" else "早退"
        skipped.append({"date": d_str, "type": zh, "reason": "no time"})
        return None
    start, _actual_end = rng
    hours = max(1, math.ceil(int(issue.duration_minutes) / 60))
    return {
        "date": d_str,
        "start_time": start,
        "end_time": _end_from_start_and_hours(start, hours),
        "hours": hours,
        "type_hint": type_hint,
        "reason": opts.leave_reason,
    }


def _make_full_day_leave(issue, opts: ExportOptions, d_str: str) -> dict:
    """整天請假（平日整日缺勤）：09:30~18:30，時數取 duration（午休不計）。

    type_hint=full_day → cascade 走事假池（補休→特休→事假）；
    實際假別由 portal-apply 逐筆覆寫。"""
    start = opts.schedule_start_hhmm
    end = opts.schedule_end_hhmm
    hours = max(1, int(issue.duration_minutes) // 60)
    return {
        "date": d_str,
        "start_time": start,
        "end_time": end,
        "hours": hours,
        "type_hint": "full_day",
        "reason": opts.leave_reason,
    }


def _make_wfh(opts: ExportOptions, d_str: str) -> dict:
    start = opts.schedule_start_hhmm
    end = opts.schedule_end_hhmm
    sh, sm = int(start[:2]), int(start[2:])
    eh, em = int(end[:2]), int(end[2:])
    hours = (eh * 60 + em - sh * 60 - sm) // 60
    return {
        "date": d_str,
        "start_time": start,
        "end_time": end,
        "hours": hours,
        "type_hint": "WFH",
        "reason": opts.wfh_reason,
    }


def write(
    path: str | Path, issues: Iterable, options: ExportOptions | None = None
) -> dict:
    """Convenience: render + persist as pretty JSON. Returns the dict."""
    payload = issues_to_analysis(issues, options)
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload

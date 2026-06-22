"""Flag weekend / holiday dates that the user might want to claim as OT.

The fhr analyzer skips Sat/Sun + national holidays entirely (no
scheduled hours, so no overtime calc). But sometimes the user
actually works a Saturday and wants to claim it — like the
04/25 supply-chain CVE response we logged this session.

Approach (no Slack here — same constraint as `lib/reasons.py`):
  - Enumerate every weekend / holiday date in the requested range
  - Cross-reference against the user's git commits (any work on
    those days indicates real activity)
  - Emit OT candidates: location defaults to `在外地` (working
    remotely on a non-work day), time range derived from first /
    last commit, rounded to whole hours.

Slack evidence is layered on top by the same agent skill that
handles reasons — it has MCP access we deliberately don't ship here.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path

from lib.reasons import commits_on, discover_repos

logger = logging.getLogger(__name__)


def list_weekend_holiday_dates(
    start: date,
    end: date,
    *,
    holidays: set[date] | None = None,
) -> list[date]:
    """Enumerate non-working days in [start, end]: Saturdays, Sundays, and
    any explicit holiday date passed in `holidays`."""
    holidays = holidays or set()
    out: list[date] = []
    cur = start
    one_day = timedelta(days=1)
    while cur <= end:
        if cur.weekday() >= 5 or cur in holidays:
            out.append(cur)
        cur += one_day
    return out


def detect_candidates(
    start: date,
    end: date,
    authors: Iterable[str],
    *,
    roots: Iterable[str] | None = None,
    holidays: set[date] | None = None,
    repos: list[Path] | None = None,
    default_location: str = "在外地",
    min_minutes: int = 60,
) -> list[dict]:
    """Find weekend / holiday dates that have at least one matching commit.

    Returns one OT candidate per qualifying date:
      {
        "date": "YYYY/MM/DD",
        "weekday": "六" | "日" | "...",
        "is_holiday": bool,
        "start_time": "HHMM",
        "end_time": "HHMM",
        "hours": int,
        "location": "在外地",
        "source": "git",  # extend later when slack joins via skill
        "evidence": {"git": [<commits>]}
      }
    """
    repos = repos if repos is not None else discover_repos(list(roots) if roots else ())
    holidays = holidays or set()
    candidates: list[dict] = []
    for d in list_weekend_holiday_dates(start, end, holidays=holidays):
        commits: list[dict] = []
        for repo in repos:
            commits.extend(commits_on(repo, d, authors))
        if not commits:
            continue
        commits.sort(key=lambda c: c["time"])
        first = datetime.fromisoformat(commits[0]["time"])
        last = datetime.fromisoformat(commits[-1]["time"])
        total_min = max(min_minutes, int((last - first).total_seconds() // 60) + min_minutes)
        hours = max(1, math.floor(total_min / 60))
        start_hhmm = f"{first.hour:02d}{(first.minute // 30) * 30:02d}"
        end_total = first.hour * 60 + (first.minute // 30) * 30 + hours * 60
        end_hhmm = f"{end_total // 60:02d}{end_total % 60:02d}"
        candidates.append(
            {
                "date": d.strftime("%Y/%m/%d"),
                "weekday": "一二三四五六日"[d.weekday()],
                "is_holiday": d in holidays,
                "start_time": start_hhmm,
                "end_time": end_hhmm,
                "hours": hours,
                "location": default_location,
                "source": "git",
                "evidence": {"git": commits},
            }
        )
    return candidates


def merge_into_analysis(analysis: dict, candidates: list[dict]) -> int:
    """Add weekend candidates to the analysis-v1 payload's `overtime` array.

    Skips candidates that already match an existing entry by (date,
    start_time, end_time). Returns the number added."""
    existing = {(e["date"], e["start_time"], e["end_time"]) for e in analysis.get("overtime", [])}
    added = 0
    for c in candidates:
        key = (c["date"], c["start_time"], c["end_time"])
        if key in existing:
            continue
        analysis.setdefault("overtime", []).append(
            {
                "date": c["date"],
                "start_time": c["start_time"],
                "end_time": c["end_time"],
                "hours": c["hours"],
                "location": c["location"],
                "reason": "(待補,週末/假日工作)",
            }
        )
        added += 1
    if added:
        analysis.setdefault("summary", {})
        analysis["summary"]["overtime_count"] = len(analysis["overtime"])
        analysis["summary"]["overtime_hours"] = sum(e["hours"] for e in analysis["overtime"])
    return added

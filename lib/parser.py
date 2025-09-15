"""Parsing helpers for attendance analyzer.

Designed to be dependency-light and avoid importing analyzer types.
"""
from datetime import datetime
import re


def clean_line(line: str) -> str:
    """Remove leading line-number markers like '  12→' if present."""
    return re.sub(r"^\s*\d+→", "", line)


def split_fields(line: str, expected: int = 9) -> list[str]:
    """Split tab-separated fields and right-pad to the expected length."""
    parts = line.split("\t")
    while len(parts) < expected:
        parts.append("")
    return parts


def parse_datetime_str(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y/%m/%d %H:%M")
    except Exception:
        return None


def parse_line(line: str) -> tuple[datetime | None, datetime | None, str, str, str, str, str, str, str] | None:
    """Return parsed tuple for a single attendance line or None if invalid.

    Output tuple: (scheduled_dt, actual_dt, type_str, card_num, source, status, processed, operation, note)
    """
    line = clean_line(line)
    fields = split_fields(line)
    scheduled_str, actual_str, type_str = fields[0], fields[1], fields[2]
    card_num, source, status = fields[3], fields[4], fields[5]
    processed, operation, note = fields[6], fields[7], fields[8]

    if not scheduled_str or type_str not in ("上班", "下班"):
        return None

    scheduled_dt = parse_datetime_str(scheduled_str) if scheduled_str else None
    actual_dt = parse_datetime_str(actual_str) if actual_str else None
    if not scheduled_dt:
        return None

    return (
        scheduled_dt,
        actual_dt,
        type_str,
        card_num,
        source,
        status,
        processed,
        operation,
        note,
    )

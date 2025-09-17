"""Date-related helpers extracted from analyzer.

No dependency on analyzer types; operate on duck-typed records.
"""
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime


def years_from_records(records: Iterable) -> set[int]:
    years: set[int] = set()
    for rec in records:
        d = getattr(rec, "date", None)
        if d:
            years.add(d.year)
    return years


def identify_complete_work_days(records: Iterable) -> list[datetime]:
    """Return sorted list of dates (at 00:00) that have both checkin and checkout."""
    daily = defaultdict(lambda: {"checkin": False, "checkout": False})
    for rec in records:
        d = getattr(rec, "date", None)
        if not d:
            continue
        t = getattr(rec, "type", None)
        # support Enum with .name or direct string
        name = getattr(t, "name", None) or str(t)
        if name == "CHECKIN":
            daily[d]["checkin"] = True
        else:
            daily[d]["checkout"] = True

    out: list[datetime] = []
    for d, flags in daily.items():
        if flags["checkin"] and flags["checkout"]:
            out.append(datetime.combine(d, datetime.min.time()))
    return sorted(out)


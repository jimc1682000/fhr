"""Grouping helpers for attendance analyzer.

These helpers avoid importing analyzer types; they return simple dicts.
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict


def group_daily(records: list) -> Dict:
    """Group records into a mapping: date -> {checkin, checkout}.

    records are expected to have attributes: date, type and actual fields.
    """
    daily = defaultdict(lambda: {"checkin": None, "checkout": None})
    for rec in records:
        if not getattr(rec, "date", None):
            continue
        key = rec.date
        if getattr(rec, "type", None) and getattr(rec, "type").name == "CHECKIN":
            daily[key]["checkin"] = rec
        else:
            daily[key]["checkout"] = rec
    return daily


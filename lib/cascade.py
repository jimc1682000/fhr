"""Cascade allocation: pick the leave type for each entry per balance + config.

Given a chronological list of leave entries (with `type_hint`) and the
current Portal balance dict (from `lib/portal/balances.py`), greedily
assign each entry's `leave_type` by trying the user's configured order
until the entry fits inside the remaining balance.

Allocation is integer-hour, whole-entry: if an entry needs 2h and only
1h is left at the head of the cascade, the *entry* falls to the next
tier (we never split one form into two). This matches the company
rule that each submitted form is one continuous block.

Monthly-capped tiers (e.g. 異地辦公(8hr一週) → 40h/月) get a per-month
budget. Already-applied forms (from `state.applied_forms`) are also
deducted up-front so re-runs of `portal-apply` don't double-spend.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Maps the analyzer's type_hint → which cascade key from config to consult.
TYPE_HINT_TO_CASCADE = {
    "late": "leave_cascade_late",
    "early_leave": "leave_cascade_late",
    "sick": "leave_cascade_sick",
    "WFH": "leave_cascade_wfh",
}

# Defaults — match the live policy verified during this session. Override via
# AttendanceConfig or runtime kwarg.
DEFAULT_CASCADES: dict[str, list[str]] = {
    "leave_cascade_late": ["補休假", "特休假", "事假(含家庭照顧假)"],
    "leave_cascade_sick": ["有薪病假", "半薪病假"],
    "leave_cascade_wfh": ["異地辦公(8hr一週)"],
}

# Leave types tracked per-month rather than per-year. Hardcoded today — the
# Portal's items panel reports the monthly cap in `total_raw` ("40 小時 / 1 月").
MONTHLY_CAPS_HOURS: dict[str, int] = {
    "異地辦公(8hr一週)": 40,
    "異地辦公(12hr一週)": 60,
}


@dataclass
class AllocationDecision:
    """One assignment made by the cascade allocator."""
    entry: dict
    leave_type: str | None       # None when nothing in the cascade could absorb
    reason: str                  # human-readable explanation
    insufficient: bool = False


@dataclass
class AllocationResult:
    decisions: list[AllocationDecision] = field(default_factory=list)
    remaining: dict[str, int | None] = field(default_factory=dict)
    monthly_used: dict[tuple[str, str], int] = field(default_factory=dict)


def _month_key(date_str: str) -> str:
    """Return 'YYYY-MM' from a 'YYYY/MM/DD' date string."""
    d = datetime.strptime(date_str, "%Y/%m/%d")
    return d.strftime("%Y-%m")


def _remaining_for(name: str, balances: dict) -> int | None:
    """Pull the parsed `remaining` hours for a leave name from balances."""
    if name == "特休假":
        annual = balances.get("annual_leave") or {}
        return annual.get("remaining_hours")
    items = balances.get("items", {})
    info = items.get(name)
    if not info:
        return None
    rem = info.get("remaining")
    if isinstance(rem, int):
        return rem
    return None


def _cascade_for(type_hint: str, cascades: dict[str, list[str]]) -> list[str]:
    key = TYPE_HINT_TO_CASCADE.get(type_hint, "leave_cascade_late")
    return cascades.get(key, [])


def allocate(
    entries: list[dict],
    balances: dict,
    *,
    cascades: dict[str, list[str]] | None = None,
    already_applied: list[dict] | None = None,
) -> AllocationResult:
    """Return an AllocationDecision per entry.

    `entries`: list[ {date, start_time, end_time, hours, type_hint, ...} ]
    `balances`: output of `lib.portal.balances.fetch_balances()`
    `cascades`: overrides DEFAULT_CASCADES (typically read from config)
    `already_applied`: list of leave entries already on the Portal (from
                      state.applied_forms.leave). Their hours pre-deduct
                      from the balance so cascade reflects reality.
    """
    cascades = cascades or DEFAULT_CASCADES
    remaining: dict[str, int | None] = {}
    monthly_used: dict[tuple[str, str], int] = {}

    # Bootstrap remaining from balances; deduct already_applied
    candidate_types: set[str] = set()
    for c in cascades.values():
        candidate_types.update(c)
    for name in candidate_types:
        remaining[name] = _remaining_for(name, balances)
    # The Portal's "剩餘時數" already reflects approved 補休 / 特休 / 病假
    # forms — deducting `already_applied` from `remaining` would double-count
    # them and falsely cascade past tiers that still have room. Only the
    # monthly-capped categories (異地辦公 ...) aren't represented in the
    # items panel as a remaining-hours number; we track those locally.
    for applied in already_applied or []:
        lt = applied.get("leave_type")
        if not lt:
            continue
        hrs = applied.get("hours") or 0
        if lt in MONTHLY_CAPS_HOURS:
            mk = _month_key(applied["date"])
            monthly_used[(lt, mk)] = monthly_used.get((lt, mk), 0) + int(hrs)

    decisions: list[AllocationDecision] = []
    for entry in sorted(entries, key=lambda e: e["date"]):
        hours = int(entry.get("hours") or 0)
        type_hint = entry.get("type_hint", "late")
        cascade = _cascade_for(type_hint, cascades)
        picked: str | None = None
        reason = ""
        for cand in cascade:
            if cand in MONTHLY_CAPS_HOURS:
                cap = MONTHLY_CAPS_HOURS[cand]
                mk = _month_key(entry["date"])
                used = monthly_used.get((cand, mk), 0)
                if used + hours <= cap:
                    monthly_used[(cand, mk)] = used + hours
                    picked = cand
                    reason = f"月額 {cap}h，已用 {used}h，扣本筆 {hours}h"
                    break
                reason = f"{cand} {mk} 月額 {cap}h 不足 (已用 {used}h)"
                continue
            rem = remaining.get(cand)
            if rem is None:
                # No explicit cap (事假 / 半薪病假) — accept as-is once cascade reaches it
                picked = cand
                reason = f"{cand} 無額度上限 (legal default)"
                break
            if rem >= hours:
                remaining[cand] = rem - hours
                picked = cand
                reason = f"{cand} 剩 {rem}h，扣本筆 {hours}h → 餘 {remaining[cand]}h"
                break
            reason = f"{cand} 剩 {rem}h 不足 {hours}h"
        decisions.append(AllocationDecision(
            entry=entry,
            leave_type=picked,
            reason=reason,
            insufficient=(picked is None),
        ))
    return AllocationResult(decisions=decisions, remaining=remaining,
                            monthly_used=monthly_used)


def summarize(result: AllocationResult) -> str:
    """One-line-per-entry human readable summary."""
    lines = []
    for d in result.decisions:
        e = d.entry
        if d.leave_type:
            lines.append(
                f"  {e['date']} {e['start_time']}-{e['end_time']} ({e['hours']}h) "
                f"[{e.get('type_hint', '?')}] → {d.leave_type}  ({d.reason})"
            )
        else:
            lines.append(
                f"  {e['date']} {e['start_time']}-{e['end_time']} ({e['hours']}h) "
                f"[{e.get('type_hint', '?')}] → ❌ 無可用額度 ({d.reason})"
            )
    return "\n".join(lines)

"""Weekly work-hour totals from Portal forms (no raw clock arithmetic).

Each weekday counts as a full work day (8h), minus leave hours from the
Portal leave forms, plus overtime hours from live overtime forms. National
holidays count as 0. Clock data is only used to flag days that have
neither a punch nor a form, so the number never drifts into values like
9.70h that no form backs up.

A single-day form counts its stated hours on that day; a leave deduction
never takes the day below 0 (the excess marks the week incomplete). A
multi-day form is split by its start/end date and time: leave over
workday hours (09:30–18:30 minus lunch 12:30–13:30, weekends and holidays
skipped, at most 8h a day), overtime over the clock time on each calendar
day. The split is used only when it adds up to the stated hours (±0.01h);
otherwise the form is not counted at all, its start day gets a note and
the week is marked incomplete. A form is multi-day when its start and end
dates differ, so ending at 00:00 of the next day counts.

Rows portal-apply recorded locally are counted but mark the week
incomplete: their hours are the local draft's, not the Portal's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from functools import partial

from lib.portal.statuses import (
    ACTIVE_FORM_STATUSES,
    FINAL_FORM_STATUSES,
    is_dead_status,
    normalize_status,
)

WORK_DAY_HOURS = 8
WORK_START = "0930"
WORK_END = "1830"
LUNCH = ("1230", "1330")

# Leave types that are still paid work time (the day counts as 8h).
WORK_LEAVE_TYPES = ("異地辦公", "在家工作", "忘刷忘帶卡")

# Written by `fhr portal-apply` for a form it just submitted, until the next sync.
LOCAL_SUBMITTED_STATUS = "已送出 (本機新增)"

DEAD, FINAL, PENDING, UNKNOWN = "dead", "final", "pending", "unknown"

# A split must match the stated hours within 0.01h (0.6 minutes).
_TOLERANCE_MINUTES = Fraction(3, 5)

# Upper bound for one form's stated hours (a month of full days is ~184h).
_MAX_FORM_HOURS = 1000


def display_hours(value) -> int | float:
    """Round exact hours to 2 decimals, half away from zero, for output only.

    One integer rounding step on the exact value, so nothing just below a
    midpoint (41.005 − 1e-28) can be pushed over it first."""
    exact = Fraction(value)
    scaled = abs(exact) * 100
    cents, rest = divmod(scaled.numerator, scaled.denominator)
    if 2 * rest >= scaled.denominator:
        cents += 1
    if exact < 0:
        cents = -cents
    return cents // 100 if cents % 100 == 0 else cents / 100


def _fmt(value) -> str:
    return f"{display_hours(value):g}"


# Hours are kept exact (Fraction: minutes / 60, or the stated decimal) all the
# way through the week totals; only display_hours() rounds.
@dataclass
class DayHours:
    day: date
    work: Fraction = Fraction(0)
    leave: Fraction = Fraction(0)
    overtime: Fraction = Fraction(0)
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> Fraction:
        return self.work + self.overtime


@dataclass
class WeekHours:
    start: date
    days: list[DayHours]
    # Reasons the total may be wrong (missing hours, unknown status).
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.warnings

    @property
    def ttl(self) -> Fraction:
        return sum((d.total for d in self.days), Fraction(0))

    @property
    def leave(self) -> Fraction:
        return sum((d.leave for d in self.days), Fraction(0))

    @property
    def overtime(self) -> Fraction:
        return sum((d.overtime for d in self.days), Fraction(0))


def week_start(any_day: date) -> date:
    return any_day - timedelta(days=any_day.weekday())


def default_week_start(today: date) -> date:
    """Monday of the latest week whose Friday is already over."""
    return week_start(today - timedelta(days=5))


def classify_status(status: str | None) -> str:
    """DEAD / FINAL / PENDING / UNKNOWN, using the shared Portal status lists.

    Anything mentioning 抽單 or 駁回 is dead, even if the exact stage name
    isn't listed."""
    if is_dead_status(status):
        return DEAD
    status = normalize_status(status)
    if status in FINAL_FORM_STATUSES:
        return FINAL
    if status in ACTIVE_FORM_STATUSES or status == LOCAL_SUBMITTED_STATUS:
        return PENDING
    return UNKNOWN


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y/%m/%d").date()


def _at(day: date, hhmm: str) -> datetime:
    # timedelta instead of time() so "2400" means midnight of the next day.
    return datetime.combine(day, datetime.min.time()) + timedelta(
        hours=int(hhmm[:2]), minutes=int(hhmm[2:])
    )


def form_span(form: dict) -> tuple[datetime, datetime]:
    """Start/end datetimes; a missing time means the workday edge."""
    start = _at(_parse(form["date"]), form.get("start_time") or WORK_START)
    end = _at(_parse(form.get("end_date") or form["date"]), form.get("end_time") or WORK_END)
    if end <= start:  # e.g. overtime 22:00–01:00 recorded without an end_date
        end += timedelta(days=1)
    return start, end


def _overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> int:
    """Overlap in whole minutes (form times are HHMM, so this is exact)."""
    return max(0, int((min(a1, b1) - max(a0, b0)).total_seconds()) // 60)


def _dates(start: datetime, end: datetime) -> list[date]:
    last = (end - timedelta(microseconds=1)).date()
    return [start.date() + timedelta(days=i) for i in range((last - start.date()).days + 1)]


def _leave_split(start: datetime, end: datetime, holidays: set[date]) -> dict[date, int]:
    """Workday minutes of the span per day: 09:30–18:30 minus lunch, max 8h."""
    out: dict[date, int] = {}
    for d in _dates(start, end):
        if d.weekday() >= 5 or d in holidays:
            continue
        m = _overlap(start, end, _at(d, WORK_START), _at(d, WORK_END))
        m -= _overlap(start, end, _at(d, LUNCH[0]), _at(d, LUNCH[1]))
        m = max(0, min(WORK_DAY_HOURS * 60, m))
        if m:
            out[d] = m
    return out


def _overtime_split(start: datetime, end: datetime) -> dict[date, int]:
    """Clock minutes of the span on each calendar day."""
    out: dict[date, int] = {}
    for d in _dates(start, end):
        m = _overlap(start, end, _at(d, "0000"), _at(d + timedelta(days=1), "0000"))
        if m:
            out[d] = m
    return out


def _check_unique_row_ids(kind: str, forms: list[dict]) -> None:
    seen: set[str] = set()
    for form in forms:
        rid = form.get("row_id")
        if not rid:
            continue
        if rid in seen:
            raise ValueError(
                f"{kind} 有重複的 row_id {rid!r}；state cache 可能損壞，請重跑 portal-sync"
            )
        seen.add(rid)


def compute_week(
    start: date,
    leave_forms: list[dict],
    overtime_forms: list[dict],
    holidays: set[date],
    punch_days: set[date] | None = None,
    punch_range: tuple[date, date] | None = None,
) -> WeekHours:
    """Compute Mon–Sun hours for the week beginning `start` (a Monday).

    `punch_days` are dates with at least one clock record; `punch_range`
    is the first/last date the attendance file covers (None when it has
    no rows). Both only produce notes, never change the numbers.
    """
    _check_unique_row_ids("leave", leave_forms)
    _check_unique_row_ids("overtime", overtime_forms)

    dates = [start + timedelta(days=i) for i in range(7)]
    days = {d: DayHours(d) for d in dates}
    warnings: list[str] = []
    has_form: set[date] = set()

    for d in dates:
        if d.weekday() < 5 and d not in holidays:
            days[d].work = WORK_DAY_HOURS
        elif d in holidays and d.weekday() < 5:
            days[d].notes.append("國定假日")

    def shares_in_week(name: str, form: dict, split) -> list:
        """(day, hours, note) for the part of a live form inside the week."""
        state = classify_status(form.get("status"))
        if state == DEAD:
            return []
        local = normalize_status(form.get("status")) == LOCAL_SUBMITTED_STATUS
        span_start, span_end = form_span(form)
        span = _dates(span_start, span_end)
        in_week = [d for d in span if d in days]
        if not in_week:
            return []
        has_form.update(in_week)
        note_day = in_week[0]  # the start day, when it falls in this week
        status = form.get("status") or "空白"
        suffix = {PENDING: "（簽核中）", UNKNOWN: f"（狀態不明：{status}）"}.get(state, "")
        if state == UNKNOWN:
            warnings.append(f"{form['date']} {name} 狀態不明（{status}），已照計")
        if local:
            # portal-apply writes its own draft here, even when the Portal
            # already had a matching form with other hours or status.
            suffix = "（本機記錄，未經 Portal 確認）"
            warnings.append(
                f"{form['date']} {name} 是本機送單記錄，時數未經 Portal 確認"
                "，請重跑 fhr portal-sync"
            )
        stated = form.get("hours")
        if stated is None:
            warnings.append(f"{form['date']} {name} 沒有時數，未計入")
            return [(note_day, Fraction(0), f"{name} 時數不明，未計入{suffix}")]
        try:
            stated = Fraction(Decimal(str(stated)))  # str() so 1.5 stays exactly 1.5
        except (InvalidOperation, ValueError, TypeError, OverflowError):
            raise ValueError(
                f"{form['date']} {name} 的時數 {stated!r} 無法解析；請重跑 fhr portal-sync"
            ) from None
        # Portal hours are never negative and no form runs past _MAX_FORM_HOURS;
        # anything outside that is a corrupt cache, not data to total up.
        if not 0 <= stated <= _MAX_FORM_HOURS:
            raise ValueError(
                f"{form['date']} {name} 的時數 {form.get('hours')!r} 超出合理範圍"
                f"（0–{_MAX_FORM_HOURS}h）；請重跑 fhr portal-sync"
            )
        # Multi-day by dates, so an end at 00:00 of the next day still crosses.
        if span_start.date() == span_end.date():
            return [(span[0], stated, f"{name} {_fmt(stated)}h{suffix}")]
        minutes = split(span_start, span_end)
        # Exact: stated hours in minutes against whole computed minutes.
        if not minutes or abs(stated * 60 - sum(minutes.values())) > _TOLERANCE_MINUTES:
            warnings.append(
                f"{form['date']} {name} 跨日單 {_fmt(stated)}h 與時段不符，無法分配，未計入"
            )
            return [(note_day, Fraction(0), f"{name} 跨日單時數與時段不符，無法分配{suffix}")]
        return [
            (d, Fraction(m, 60), f"{name} {_fmt(Fraction(m, 60))}h{suffix}")
            for d, m in sorted(minutes.items())
            if d in days
        ]

    for form in leave_forms:
        leave_type = form.get("leave_type") or "請假"
        counts_as_work = any(t in leave_type for t in WORK_LEAVE_TYPES)
        for d, h, label in shares_in_week(
            leave_type, form, partial(_leave_split, holidays=holidays)
        ):
            days[d].notes.append(label)
            if counts_as_work:
                continue
            deducted = min(h, days[d].work)
            days[d].leave += deducted
            days[d].work -= deducted
            if h > deducted:
                days[d].notes.append(f"請假超過當日工時，只扣 {_fmt(deducted)}h")
                warnings.append(
                    f"{d:%Y/%m/%d} 請假 {_fmt(h)}h 超過當日剩餘工時，只扣 {_fmt(deducted)}h"
                )

    for form in overtime_forms:
        for d, h, label in shares_in_week("加班", form, _overtime_split):
            days[d].overtime += h
            days[d].notes.append(label)

    if punch_days is not None:
        for d in dates:
            if d.weekday() >= 5 or d in holidays or d in has_form or d in punch_days:
                continue
            if punch_range is None or not punch_range[0] <= d <= punch_range[1]:
                days[d].notes.append("打卡資料未涵蓋，暫以 8h 計（未驗證）")
            else:
                days[d].notes.append("無打卡也無假單，暫以 8h 計（未驗證）")

    weekend = [d for d in dates[5:] if days[d].overtime > 0 or days[d].notes]
    return WeekHours(
        start=start,
        days=[days[d] for d in dates[:5]] + [days[d] for d in weekend],
        warnings=warnings,
    )


def format_week(week: WeekHours) -> str:
    end = max(week.start + timedelta(days=4), week.days[-1].day)
    lines = [
        f"# 週工時 {week.start:%Y/%m/%d} ~ {end:%Y/%m/%d}",
        "",
        "| 日期 | 工時 | 請假 | 加班 | 備註 |",
        "|---|---|---|---|---|",
    ]
    wd = "一二三四五六日"
    for d in week.days:
        lines.append(
            f"| {d.day:%m/%d}（{wd[d.day.weekday()]}） | {_fmt(d.total)} | {_fmt(d.leave)} | "
            f"{_fmt(d.overtime)} | {'；'.join(d.notes)} |"
        )
    lines += [
        "",
        f"TTL: {_fmt(week.ttl)}",
        f"請假 (hr): {_fmt(week.leave)}",
        f"加班 (hr): {_fmt(week.overtime)}",
    ]
    if not week.complete:
        lines += ["", "⚠️ 總計不完整："] + [f"- {w}" for w in week.warnings]
    return "\n".join(lines)

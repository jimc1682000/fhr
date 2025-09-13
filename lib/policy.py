from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Tuple


@dataclass
class Rules:
    earliest_checkin: str = "08:30"
    latest_checkin: str = "10:30"
    lunch_start: str = "12:30"
    lunch_end: str = "13:30"
    work_hours: int = 8
    lunch_hours: int = 1
    min_overtime_minutes: int = 60
    overtime_increment_minutes: int = 60
    forget_punch_allowance_per_month: int = 2
    forget_punch_max_minutes: int = 60


def is_full_day_absent(workday: Any) -> bool:
    """True if both checkin and checkout records exist but actual times are missing (absent)."""
    ch = workday.checkin_record
    co = workday.checkout_record
    return (ch is not None and co is not None and
            (not getattr(ch, 'actual_time', None)) and (not getattr(co, 'actual_time', None)))


def calculate_late_minutes(workday: Any, rules: Rules) -> Tuple[int, str, str]:
    """Return (late_minutes, time_range, calculation_str)."""
    ch = workday.checkin_record
    if not ch or not ch.actual_time:
        return 0, "", ""

    latest_checkin = datetime.strptime(f"{workday.date.strftime('%Y/%m/%d')} {rules.latest_checkin}", "%Y/%m/%d %H:%M")
    actual_checkin = ch.actual_time

    if actual_checkin <= latest_checkin:
        return 0, "", ""

    delta = actual_checkin - latest_checkin
    late_minutes = int(delta.total_seconds() // 60)

    if late_minutes > 120:
        lunch_start = datetime.strptime(f"{workday.date.strftime('%Y/%m/%d')} {rules.lunch_start}", "%Y/%m/%d %H:%M")
        if actual_checkin > lunch_start:
            late_minutes -= 60
            calculation = (
                f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {rules.latest_checkin}, "
                f"遲到: {int(delta.total_seconds() // 60)}分鐘 - 60分鐘午休 = {late_minutes}分鐘"
            )
        else:
            calculation = (
                f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {rules.latest_checkin}, 遲到: {late_minutes}分鐘"
            )
    else:
        calculation = (
            f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {rules.latest_checkin}, 遲到: {late_minutes}分鐘"
        )

    time_range = f"{rules.latest_checkin}~{actual_checkin.strftime('%H:%M')}"
    return late_minutes, time_range, calculation


def calculate_overtime_minutes(workday: Any, rules: Rules) -> Tuple[int, int, str, str]:
    """Return (actual_minutes, applicable_minutes, time_range, calculation_str)."""
    ch = workday.checkin_record
    co = workday.checkout_record
    if not (ch and ch.actual_time and co and co.actual_time):
        return 0, 0, "", ""

    checkin_time = ch.actual_time
    checkout_time = co.actual_time
    expected_checkout = checkin_time + timedelta(hours=rules.work_hours + rules.lunch_hours)

    if checkout_time <= expected_checkout:
        return 0, 0, "", ""

    delta = checkout_time - expected_checkout
    actual_overtime_minutes = int(delta.total_seconds() // 60)
    if actual_overtime_minutes < rules.min_overtime_minutes:
        return actual_overtime_minutes, 0, "", ""

    intervals = (actual_overtime_minutes - rules.min_overtime_minutes) // rules.overtime_increment_minutes
    applicable_minutes = rules.min_overtime_minutes + (intervals * rules.overtime_increment_minutes)
    time_range = f"{expected_checkout.strftime('%H:%M')}~{checkout_time.strftime('%H:%M')}"
    calculation = (
        f"預期下班: {expected_checkout.strftime('%H:%M')}, 實際下班: {checkout_time.strftime('%H:%M')}, "
        f"實際加班: {actual_overtime_minutes}分鐘, 可申請: {applicable_minutes}分鐘"
    )
    return actual_overtime_minutes, applicable_minutes, time_range, calculation


import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class Rules:
    schedule_start: str = "09:30"  # 個人班表起始時間
    schedule_end: str = "18:30"  # 個人班表結束時間
    earliest_checkin: str = "08:00"  # 最早上班時間
    latest_checkin: str = "10:00"  # 遲到門檻（超過此時間需請假）
    lunch_start: str = "12:30"
    lunch_end: str = "13:30"
    work_hours: int = 8
    lunch_hours: int = 1
    min_overtime_minutes: int = 60
    overtime_increment_minutes: int = 60
    forget_punch_allowance_per_month: int = 2
    forget_punch_max_minutes: int = 60


def is_full_day_absent(workday: Any) -> bool:
    """True if checkin or checkout record is missing or lacks an actual time."""
    ch = workday.checkin_record
    co = workday.checkout_record
    return (
        ch is None
        or co is None
        or not getattr(ch, "actual_time", None)
        or not getattr(co, "actual_time", None)
    )


def calculate_late_minutes(workday: Any, rules: Rules) -> tuple[int, str, str]:
    """計算遲到時間（晚於遲到門檻需從班表起始請假）

    Returns:
        (late_minutes, time_range, calculation_str)
    """
    ch = workday.checkin_record
    if not ch or not ch.actual_time:
        return 0, "", ""

    date_str = workday.date.strftime("%Y/%m/%d")
    latest_checkin = datetime.strptime(
        f"{date_str} {rules.latest_checkin}", "%Y/%m/%d %H:%M"
    )
    actual_checkin = ch.actual_time

    if actual_checkin <= latest_checkin:
        return 0, "", ""

    # 遲到分鐘數 = 實際到班 - 班表起始時間
    schedule_start = datetime.strptime(
        f"{date_str} {rules.schedule_start}", "%Y/%m/%d %H:%M"
    )
    delta = actual_checkin - schedule_start
    late_minutes = int(delta.total_seconds() // 60)

    time_range = f"{rules.schedule_start}~{actual_checkin.strftime('%H:%M')}"
    calculation = (
        f"實際上班: {actual_checkin.strftime('%H:%M')}, "
        f"班表起始: {rules.schedule_start}, "
        f"需請假: {late_minutes}分鐘"
    )

    return late_minutes, time_range, calculation


def calculate_leave_suggestion(
    workday: Any, rules: Rules, late_minutes: int
) -> tuple[str, str, int, int]:
    """計算遲到請假建議（湊整到小時）

    遲到請假區間 = 班表起始 ~ 實際到班；若橫跨午休（12:30~13:30），
    午休非工時須扣除，再無條件進位到整點。

    Returns:
        (leave_start_time, leave_end_time, leave_hours, effective_minutes)
        leave_end_time 為「班表起始 + leave_hours」的整點請假塊；
        effective_minutes 為扣午休後實際缺工分鐘（供下游算時數）。
    """
    if late_minutes <= 0:
        return "", "", 0, 0

    ch = workday.checkin_record
    actual_checkin = ch.actual_time
    date_str = workday.date.strftime("%Y/%m/%d")
    schedule_start = datetime.strptime(
        f"{date_str} {rules.schedule_start}", "%Y/%m/%d %H:%M"
    )
    lunch_start = datetime.strptime(f"{date_str} {rules.lunch_start}", "%Y/%m/%d %H:%M")
    lunch_end = datetime.strptime(f"{date_str} {rules.lunch_end}", "%Y/%m/%d %H:%M")

    # 扣除遲到區間 [班表起始, 實際到班] 與午休 [lunch_start, lunch_end] 的重疊
    overlap_start = max(schedule_start, lunch_start)
    overlap_end = min(actual_checkin, lunch_end)
    lunch_overlap = max(0, int((overlap_end - overlap_start).total_seconds() // 60))
    effective_minutes = max(0, late_minutes - lunch_overlap)

    leave_hours = math.ceil(effective_minutes / 60)
    leave_end = schedule_start + timedelta(minutes=leave_hours * 60)

    return (
        schedule_start.strftime("%H:%M"),
        leave_end.strftime("%H:%M"),
        leave_hours,
        effective_minutes,
    )


def calculate_expected_checkout(
    workday: Any, rules: Rules, work_start_time: datetime
) -> datetime:
    """計算預期下班時間

    遲到（>10:00）：預期下班 = 班表結束時間
    正常（<=10:00）：預期下班 = 實際到班 + 9小時

    Args:
        workday: 工作日資料
        rules: 業務規則
        work_start_time: 實際工作起始時間

    Returns:
        預期下班時間
    """
    date_str = workday.date.strftime("%Y/%m/%d")
    latest_checkin = datetime.strptime(
        f"{date_str} {rules.latest_checkin}", "%Y/%m/%d %H:%M"
    )

    ch = workday.checkin_record
    actual_checkin = ch.actual_time if ch and ch.actual_time else work_start_time

    if actual_checkin > latest_checkin:
        # 遲到：預期下班 = 班表結束時間
        return datetime.strptime(f"{date_str} {rules.schedule_end}", "%Y/%m/%d %H:%M")

    # 正常：預期下班 = 實際到班 + 9小時
    total_hours = rules.work_hours + rules.lunch_hours
    return work_start_time + timedelta(hours=total_hours)


def optimize_forget_punch(
    workday: Any,
    rules: Rules,
    late_minutes: int,
    actual_checkout: datetime,
) -> tuple[str, str]:
    """優化忘刷卡時段以最小化早退請假

    Args:
        workday: 工作日資料
        rules: 業務規則
        late_minutes: 遲到分鐘數
        actual_checkout: 實際下班時間

    Returns:
        (optimized_start_time, forget_punch_end_time) 格式: "HH:MM"
    """
    ch = workday.checkin_record
    actual_checkin = ch.actual_time

    latest_checkin = datetime.strptime(
        f"{workday.date.strftime('%Y/%m/%d')} {rules.latest_checkin}", "%Y/%m/%d %H:%M"
    )

    # 預設忘刷卡時段：10:30 ~ 實際上班
    default_start = latest_checkin
    forget_end = actual_checkin

    # 計算使用預設時段的預期下班時間
    expected_checkout_default = calculate_expected_checkout(
        workday, rules, default_start
    )

    # 如果沒有早退，使用預設時段
    if actual_checkout >= expected_checkout_default:
        return default_start.strftime("%H:%M"), forget_end.strftime("%H:%M")

    # 有早退，嘗試優化
    early_leave_minutes = int(
        (expected_checkout_default - actual_checkout).total_seconds() // 60
    )
    early_leave_hours = math.ceil(early_leave_minutes / 60)

    # 計算優化調整量：讓早退時間剛好湊整
    optimal_adjustment = (early_leave_hours * 60) - early_leave_minutes

    # 如果調整量在合理範圍內（不超過遲到時間），則應用優化
    if 0 < optimal_adjustment <= late_minutes:
        optimized_start = latest_checkin - timedelta(minutes=optimal_adjustment)
        return optimized_start.strftime("%H:%M"), forget_end.strftime("%H:%M")

    # 否則使用預設時段
    return default_start.strftime("%H:%M"), forget_end.strftime("%H:%M")


def calculate_early_leave(
    workday: Any, rules: Rules, expected_checkout: datetime
) -> tuple[int, str, str]:
    """計算早退時間

    Returns:
        (early_leave_minutes, time_range, calculation_str)
    """
    co = workday.checkout_record
    if not co or not co.actual_time:
        return 0, "", ""

    actual_checkout = co.actual_time

    if actual_checkout >= expected_checkout:
        return 0, "", ""

    delta = expected_checkout - actual_checkout
    early_leave_minutes = int(delta.total_seconds() // 60)
    early_leave_hours = math.ceil(early_leave_minutes / 60)

    time_range = (
        f"{actual_checkout.strftime('%H:%M')}~{expected_checkout.strftime('%H:%M')}"
    )
    calculation = (
        f"實際下班: {actual_checkout.strftime('%H:%M')}, "
        f"預期下班: {expected_checkout.strftime('%H:%M')}, "
        f"早退: {early_leave_minutes}分鐘（建議請 {early_leave_hours} 小時）"
    )

    return early_leave_minutes, time_range, calculation


def calculate_overtime_minutes(
    workday: Any, rules: Rules, expected_checkout: datetime
) -> tuple[int, int, str, str]:
    """計算加班時間（基於新的預期下班時間）

    Returns:
        (actual_minutes, applicable_minutes, time_range, calculation_str)
    """
    co = workday.checkout_record
    if not co or not co.actual_time:
        return 0, 0, "", ""

    actual_checkout = co.actual_time

    if actual_checkout <= expected_checkout:
        return 0, 0, "", ""

    delta = actual_checkout - expected_checkout
    actual_overtime_minutes = int(delta.total_seconds() // 60)

    if actual_overtime_minutes < rules.min_overtime_minutes:
        return actual_overtime_minutes, 0, "", ""

    # 計算可申請的加班時數（60分鐘為單位）
    applicable_hours = actual_overtime_minutes // rules.overtime_increment_minutes
    applicable_minutes = applicable_hours * rules.overtime_increment_minutes

    # 時段顯示完整實際加班時間
    time_range = (
        f"{expected_checkout.strftime('%H:%M')}~{actual_checkout.strftime('%H:%M')}"
    )
    calculation = (
        f"預期下班: {expected_checkout.strftime('%H:%M')}, "
        f"實際下班: {actual_checkout.strftime('%H:%M')}, "
        f"實際加班: {actual_overtime_minutes}分鐘, 可申請: {applicable_minutes}分鐘"
    )

    return actual_overtime_minutes, applicable_minutes, time_range, calculation

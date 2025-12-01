import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class Rules:
    earliest_checkin: str = "08:00"  # 最早上班時間
    latest_checkin: str = "10:30"  # 最晚上班時間（晚於此算遲到）
    standard_checkout: str = "17:00"  # 標準下班時間
    latest_makeup: str = "19:30"  # 最晚補時下班時間
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
    """計算遲到時間（晚於 10:30 才算遲到）

    Returns:
        (late_minutes, time_range, calculation_str)
    """
    ch = workday.checkin_record
    if not ch or not ch.actual_time:
        return 0, "", ""

    latest_checkin = datetime.strptime(
        f"{workday.date.strftime('%Y/%m/%d')} {rules.latest_checkin}", "%Y/%m/%d %H:%M"
    )
    actual_checkin = ch.actual_time

    if actual_checkin <= latest_checkin:
        return 0, "", ""

    delta = actual_checkin - latest_checkin
    late_minutes = int(delta.total_seconds() // 60)

    # 午休時間扣除邏輯保持不變
    if late_minutes > 120:
        lunch_start = datetime.strptime(
            f"{workday.date.strftime('%Y/%m/%d')} {rules.lunch_start}", "%Y/%m/%d %H:%M"
        )
        if actual_checkin > lunch_start:
            late_minutes -= 60
            calculation = (
                f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {rules.latest_checkin}, "
                f"遲到: {int(delta.total_seconds() // 60)}分鐘 - 60分鐘午休 = {late_minutes}分鐘"
            )
        else:
            calculation = (
                f"實際上班: {actual_checkin.strftime('%H:%M')}, "
                f"最晚上班: {rules.latest_checkin}, 遲到: {late_minutes}分鐘"
            )
    else:
        calculation = (
            f"實際上班: {actual_checkin.strftime('%H:%M')}, "
            f"最晚上班: {rules.latest_checkin}, 遲到: {late_minutes}分鐘"
        )

    time_range = f"{rules.latest_checkin}~{actual_checkin.strftime('%H:%M')}"
    return late_minutes, time_range, calculation


def calculate_leave_suggestion(
    workday: Any, rules: Rules, late_minutes: int
) -> tuple[str, str, int]:
    """計算遲到請假建議（湊整到小時）

    注意：late_minutes 可能已扣除午休時間，這裡需要重新計算原始遲到時間

    Returns:
        (leave_start_time, leave_end_time, leave_hours)
    """
    if late_minutes <= 0:
        return "", "", 0

    ch = workday.checkin_record
    actual_checkin = ch.actual_time
    latest_checkin = datetime.strptime(
        f"{workday.date.strftime('%Y/%m/%d')} {rules.latest_checkin}", "%Y/%m/%d %H:%M"
    )

    # 計算原始遲到時間（不扣午休）
    delta = actual_checkin - latest_checkin
    original_late_minutes = int(delta.total_seconds() // 60)

    # 湊整到小時
    leave_hours = math.ceil(original_late_minutes / 60)

    # 計算需要補的時間（讓遲到時段湊整成整數小時）
    padding_minutes = (leave_hours * 60) - original_late_minutes

    # 請假起始 = 最晚上班時間 - 補的時間
    leave_start = latest_checkin - timedelta(minutes=padding_minutes)
    leave_end = actual_checkin

    return (leave_start.strftime("%H:%M"), leave_end.strftime("%H:%M"), leave_hours)


def calculate_expected_checkout(workday: Any, rules: Rules, work_start_time: datetime) -> datetime:
    """計算預期下班時間（工作起始時間 + 9小時）

    Args:
        workday: 工作日資料
        rules: 業務規則
        work_start_time: 工作起始時間（請假/忘刷卡後的時間）

    Returns:
        預期下班時間
    """
    latest_makeup = datetime.strptime(
        f"{workday.date.strftime('%Y/%m/%d')} {rules.latest_makeup}", "%Y/%m/%d %H:%M"
    )

    # 預期下班 = 工作起始時間 + 8小時工作 + 1小時午休
    total_hours = rules.work_hours + rules.lunch_hours
    expected_checkout = work_start_time + timedelta(hours=total_hours)

    # 補時上限是 19:30
    if expected_checkout > latest_makeup:
        expected_checkout = latest_makeup

    return expected_checkout


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
    expected_checkout_default = calculate_expected_checkout(workday, rules, default_start)

    # 如果沒有早退，使用預設時段
    if actual_checkout >= expected_checkout_default:
        return default_start.strftime("%H:%M"), forget_end.strftime("%H:%M")

    # 有早退，嘗試優化
    early_leave_minutes = int((expected_checkout_default - actual_checkout).total_seconds() // 60)
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

    time_range = f"{actual_checkout.strftime('%H:%M')}~{expected_checkout.strftime('%H:%M')}"
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
    time_range = f"{expected_checkout.strftime('%H:%M')}~{actual_checkout.strftime('%H:%M')}"
    calculation = (
        f"預期下班: {expected_checkout.strftime('%H:%M')}, "
        f"實際下班: {actual_checkout.strftime('%H:%M')}, "
        f"實際加班: {actual_overtime_minutes}分鐘, 可申請: {applicable_minutes}分鐘"
    )

    return actual_overtime_minutes, applicable_minutes, time_range, calculation

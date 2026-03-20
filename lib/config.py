from dataclasses import dataclass


@dataclass
class AttendanceConfig:
    schedule_start: str = "09:30"  # 個人班表起始時間
    schedule_end: str = "18:30"  # 個人班表結束時間
    earliest_checkin: str = "08:30"
    latest_checkin: str = "10:00"  # 遲到門檻（超過此時間需請假）
    lunch_start: str = "12:30"
    lunch_end: str = "13:30"
    work_hours: int = 8
    lunch_hours: int = 1
    min_overtime_minutes: int = 60
    overtime_increment_minutes: int = 60
    forget_punch_allowance_per_month: int = 2
    forget_punch_max_minutes: int = 60


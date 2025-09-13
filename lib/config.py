from dataclasses import dataclass


@dataclass
class AttendanceConfig:
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


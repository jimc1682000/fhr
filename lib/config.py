from dataclasses import dataclass


@dataclass
class AttendanceConfig:
    schedule_start: str = "09:30"  # 個人班表起始時間
    schedule_end: str = "18:30"  # 個人班表結束時間
    earliest_checkin: str = "08:30"
    latest_checkin: str = "10:00"  # 遲到門檻（超過此時間需請假）
    lunch_start: str = "12:30"  # 午休起（遲到請假時數會扣此區間）
    lunch_end: str = "13:30"  # 午休迄
    work_hours: int = 8
    lunch_hours: int = 1
    min_overtime_minutes: int = 60
    overtime_increment_minutes: int = 60
    # 忘刷卡政策已改為每年 4 次（稀缺手動額度）。analyzer 不自動拿忘刷卡抵遲到，
    # 一律走請假；下列欄位目前未被分析流程使用，保留供未來手動工具參考。
    forget_punch_allowance_per_month: int = 2
    forget_punch_max_minutes: int = 60

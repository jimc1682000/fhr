#!/usr/bin/env python3
"""
考勤分析系統
用於分析考勤記錄並計算遲到/加班時數
"""

import re
import sys
import json
import os
import logging
import time  # unused; kept previously, now removed for clarity
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Callable, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class AttendanceType(Enum):
    CHECKIN = "上班"
    CHECKOUT = "下班"


class IssueType(Enum):
    LATE = "遲到"
    FORGET_PUNCH = "忘刷卡"
    OVERTIME = "加班"
    WFH = "WFH假"
    WEEKDAY_LEAVE = "請假"


@dataclass
class AttendanceRecord:
    date: datetime
    scheduled_time: Optional[datetime]
    actual_time: Optional[datetime]
    type: AttendanceType
    card_number: str
    source: str
    status: str
    processed: str
    operation: str
    note: str


@dataclass
class WorkDay:
    date: datetime
    checkin_record: Optional[AttendanceRecord]
    checkout_record: Optional[AttendanceRecord]
    is_friday: bool
    is_holiday: bool = False


@dataclass
class Issue:
    date: datetime
    type: IssueType
    duration_minutes: int
    description: str
    time_range: str = ""
    calculation: str = ""
    is_new: bool = True  # 標示是否為本次新發現的問題


    # AttendanceStateManager 已抽離至 lib.state


class AttendanceAnalyzer:
    """考勤分析器"""
    
    # 規則配置（AttendanceConfig 封裝，可由設定檔覆蓋）
    

    def __init__(self, config_path: str = "config.json"):
        # 初始化配置
        from lib.config import AttendanceConfig
        self.config = AttendanceConfig()
        self._load_config(config_path)
        self.records: List[AttendanceRecord] = []
        self.workdays: List[WorkDay] = []
        self.issues: List[Issue] = []
        self.holidays: set = set()  # 存放國定假日日期
        self.forget_punch_usage: Dict[str, int] = defaultdict(int)  # 追蹤每月忘刷卡使用次數 {年月: 次數}
        self.loaded_holiday_years: set = set()  # 追蹤已載入假日的年份
        self.state_manager: Optional['AttendanceStateManager'] = None
        self.current_user: Optional[str] = None
        self.incremental_mode: bool = True
        self._progress_cb: Optional[Callable[[str, int, Optional[int]], None]] = None
        self._cancel_check: Optional[Callable[[], bool]] = None

    # 可選：供 TUI/外部注入進度與取消機制（不影響 CLI 舊行為）
    def set_progress_callback(self, cb: Optional[Callable[[str, int, Optional[int]], None]] = None) -> None:
        self._progress_cb = cb

    def set_cancel_check(self, fn: Optional[Callable[[], bool]] = None) -> None:
        self._cancel_check = fn

    def _load_config(self, config_path: str) -> None:
        """載入設定檔以覆蓋預設公司規則"""
        if not os.path.exists(config_path):
            logger.info("找不到設定檔 %s，使用預設值", config_path)
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("無法讀取設定檔 %s: %s", config_path, e)
    
    
    def _identify_complete_work_days(self) -> List[datetime]:
        """識別完整的工作日（委派至 lib.dates）"""
        from lib.dates import identify_complete_work_days
        return identify_complete_work_days(self.records)
    
    def _get_unprocessed_dates(self, user_name: str, complete_days: List[datetime]) -> List[datetime]:
        """取得需要處理的新日期（委派至 lib.state.filter_unprocessed_dates）"""
        if not self.state_manager or not self.incremental_mode:
            return complete_days
        from lib.state import filter_unprocessed_dates
        processed_ranges = self.state_manager.get_user_processed_ranges(user_name)
        return filter_unprocessed_dates(processed_ranges, complete_days)
    
    def _load_previous_forget_punch_usage(self, user_name: str) -> None:
        """載入之前的忘刷卡使用統計"""
        if not self.state_manager or not self.incremental_mode:
            return
        
        # 清空現有統計
        self.forget_punch_usage = defaultdict(int)
        
        # 從狀態管理器載入
        user_data = self.state_manager.state_data.get("users", {}).get(user_name, {})
        previous_usage = user_data.get("forget_punch_usage", {})
        
        # 複製到本地統計
        self.forget_punch_usage.update(previous_usage)
    
    def _get_years_from_records(self) -> set:
        """從出勤記錄中提取年份（委派至 lib.dates）"""
        from lib.dates import years_from_records
        return years_from_records(self.records)
    
    def _load_taiwan_holidays(self, years: set = None) -> None:
        """載入台灣國定假日資料
        Args:
            years: 需要載入的年份集合，None表示只載入當年(2025)
        """
        if years is None:
            years = {2025}  # 預設載入當年
        
        for year in years:
            if year not in self.loaded_holiday_years:
                from lib.holidays import HolidayService
                logger.info("資訊: 動態載入 %d 年國定假日...", year)
                service = HolidayService()
                self.holidays |= service.load_year(year)
                self.loaded_holiday_years.add(year)
    
    def _try_load_from_gov_api(self, year: int) -> bool:
        # 向後相容：保留本模組內的 scheme 檢查（供單元測試 patch）
        url = "https://data.gov.tw/api/v1/rest/datastore_search?resource_id=W2&filters={\"date\":\"%s\"}" % year
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            logger.warning("不支援的 URL scheme: %s", parsed.scheme)
            return False
        from lib.holidays import TaiwanGovOpenDataProvider
        out = TaiwanGovOpenDataProvider().load(year)
        if out:
            self.holidays |= out
            return True
        return False
    
    def parse_attendance_file(self, filepath: str, incremental: bool = True) -> None:
        """解析考勤資料檔案並初始化增量處理
        Args:
            filepath: 檔案路徑
            incremental: 是否啟用增量分析
        """
        self.incremental_mode = incremental
        
        # 初始化狀態管理器
        if self.incremental_mode:
            from lib.state import AttendanceStateManager
            self.state_manager = AttendanceStateManager()
            
            # 解析檔名取得使用者資訊
            from lib.filename import parse_range_and_user
            user_name, start_date, end_date = parse_range_and_user(filepath)
            if user_name:
                self.current_user = user_name
                logger.info("📋 識別使用者: %s", user_name)
                logger.info("📅 檔案涵蓋期間: %s 至 %s", start_date, end_date)
                
                # 檢查重疊日期
                if start_date and end_date:
                    overlaps = self.state_manager.detect_date_overlap(user_name, start_date, end_date)
                    if overlaps:
                        logger.warning("⚠️  發現重疊日期範圍: %s", overlaps)
                        logger.warning("將以舊資料為主，僅處理新日期")
                
                # 載入之前的忘刷卡使用統計
                self._load_previous_forget_punch_usage(user_name)
            else:
                logger.warning("⚠️  無法從檔名識別使用者，將使用完整分析模式")
                self.incremental_mode = False
        
        # 解析檔案內容
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line_num, line in enumerate(lines, 1):
            if line_num == 1:  # 跳過表頭
                continue
                
            line = line.strip()
            if not line:
                continue
                
            try:
                record = self._parse_attendance_line(line)
                if record:
                    self.records.append(record)
            except (ValueError, IndexError) as e:
                logger.warning("第%d行解析失敗: %s", line_num, e)
    
    def _parse_attendance_line(self, line: str) -> Optional[AttendanceRecord]:
        """解析單行考勤記錄（委派至 lib.parser）"""
        from lib import parser as p
        parsed = p.parse_line(line)
        if not parsed:
            return None
        scheduled_time, actual_time, type_str, card_num, source, status, processed, operation, note = parsed
        attendance_type = AttendanceType.CHECKIN if type_str == "上班" else AttendanceType.CHECKOUT
        return AttendanceRecord(
            date=scheduled_time.date() if scheduled_time else None,
            scheduled_time=scheduled_time,
            actual_time=actual_time,
            type=attendance_type,
            card_number=card_num,
            source=source,
            status=status,
            processed=processed,
            operation=operation,
            note=note,
        )
    
    def group_records_by_day(self) -> None:
        """將記錄按日期分組"""
        # 在分組前，先載入出勤資料中涉及的年份假日
        years_in_data = self._get_years_from_records()
        if years_in_data:
            self._load_taiwan_holidays(years_in_data)
        
        from lib.grouping import group_daily
        daily_records = group_daily(self.records)
        
        for date, records in daily_records.items():
            workday = WorkDay(
                date=datetime.combine(date, datetime.min.time()),
                checkin_record=records['checkin'],
                checkout_record=records['checkout'],
                is_friday=(date.weekday() == 4),  # 週五是4
                is_holiday=(date in self.holidays)  # 檢查是否為國定假日
            )
            self.workdays.append(workday)
        
        self.workdays.sort(key=lambda x: x.date)
    
    def analyze_attendance(self) -> None:
        """分析考勤記錄（支援增量分析）"""
        self.issues = []

        workdays_to_analyze = self._get_workdays_to_analyze()

        from lib.policy import Rules
        rules = Rules(
            earliest_checkin=self.config.earliest_checkin,
            latest_checkin=self.config.latest_checkin,
            lunch_start=self.config.lunch_start,
            lunch_end=self.config.lunch_end,
            work_hours=self.config.work_hours,
            lunch_hours=self.config.lunch_hours,
            min_overtime_minutes=self.config.min_overtime_minutes,
            overtime_increment_minutes=self.config.overtime_increment_minutes,
            forget_punch_allowance_per_month=self.config.forget_punch_allowance_per_month,
            forget_punch_max_minutes=self.config.forget_punch_max_minutes,
        )

        total = len(workdays_to_analyze)
        for idx, workday in enumerate(workdays_to_analyze, 1):
            if self._cancel_check and self._cancel_check():
                break
            self._analyze_single_workday(workday, rules)
            if self._progress_cb:
                try:
                    self._progress_cb("analyze", idx, total)
                except Exception:
                    pass

        if self.incremental_mode and self.current_user and workdays_to_analyze:
            self._update_processing_state()

    def _get_workdays_to_analyze(self) -> List[WorkDay]:
        if self.incremental_mode and self.current_user:
            complete_days = self._identify_complete_work_days()
            unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
            if unprocessed_dates:
                logger.info("🔄 增量分析: 發現 %d 個新的完整工作日需要處理", len(unprocessed_dates))
                logger.info("📊 跳過已處理的工作日: %d 個", len(complete_days) - len(unprocessed_dates))
                unprocessed_date_set = {d.date() for d in unprocessed_dates}
                return [wd for wd in self.workdays if wd.date.date() in unprocessed_date_set]
            logger.info("✅ 增量分析: 沒有新的工作日需要處理")
            return []
        return self.workdays

    def _handle_absent_day(self, workday: WorkDay) -> bool:
        from lib.policy import is_full_day_absent
        if is_full_day_absent(workday):
            if workday.is_friday and not workday.is_holiday:
                self.issues.append(Issue(
                    date=workday.date,
                    type=IssueType.WFH,
                    duration_minutes=9 * 60,
                    description="建議申請整天WFH假 🏠💻",
                ))
            elif not workday.is_holiday:
                self.issues.append(Issue(
                    date=workday.date,
                    type=IssueType.WEEKDAY_LEAVE,
                    duration_minutes=8 * 60,
                    description="整天沒進公司，建議請假 📝🏠",
                ))
            return True
        return False

    def _analyze_single_workday(self, workday: WorkDay, rules) -> None:
        from lib.policy import calculate_late_minutes, calculate_overtime_minutes
        if self._handle_absent_day(workday):
            return
        if workday.is_friday:
            return
        late_minutes, late_time_range, late_calculation = calculate_late_minutes(workday, rules)
        if late_minutes > 0:
            month_key = workday.date.strftime('%Y-%m')
            can_use_forget_punch = (
                late_minutes <= self.config.forget_punch_max_minutes and
                self.forget_punch_usage[month_key] < self.config.forget_punch_allowance_per_month
            )
            if can_use_forget_punch:
                self.forget_punch_usage[month_key] += 1
                remaining = self.config.forget_punch_allowance_per_month - self.forget_punch_usage[month_key]
                self.issues.append(Issue(
                    date=workday.date,
                    type=IssueType.FORGET_PUNCH,
                    duration_minutes=0,
                    description=f"遲到{late_minutes}分鐘，建議使用忘刷卡 🔄✅",
                    time_range=late_time_range,
                    calculation=f"{late_calculation} (使用忘刷卡，本月剩餘: {remaining}次)",
                ))
            else:
                reason = "超過1小時" if late_minutes > self.config.forget_punch_max_minutes else "本月忘刷卡額度已用完"
                self.issues.append(Issue(
                    date=workday.date,
                    type=IssueType.LATE,
                    duration_minutes=late_minutes,
                    description=f"遲到{late_minutes}分鐘 ⏱️ ({reason})",
                    time_range=late_time_range,
                    calculation=late_calculation,
                ))
        actual_overtime, applicable_overtime, overtime_time_range, overtime_calculation = calculate_overtime_minutes(workday, rules)
        if applicable_overtime >= self.config.min_overtime_minutes:
            self.issues.append(Issue(
                date=workday.date,
                type=IssueType.OVERTIME,
                duration_minutes=applicable_overtime,
                description=f"加班{applicable_overtime // 60}小時{applicable_overtime % 60}分鐘 💼",
                time_range=overtime_time_range,
                calculation=overtime_calculation,
            ))
    
    def _update_processing_state(self) -> None:
        """更新處理狀態到狀態檔案"""
        if not self.state_manager or not self.current_user:
            return
        
        # 計算處理範圍
        complete_days = self._identify_complete_work_days()
        if not complete_days:
            return
        
        start_date = min(complete_days).strftime("%Y-%m-%d")
        end_date = max(complete_days).strftime("%Y-%m-%d")
        
        # 構建範圍資訊
        range_info = {
            "start_date": start_date,
            "end_date": end_date,
            "source_file": os.path.basename(sys.argv[1]) if len(sys.argv) > 1 else "unknown",
            "last_analysis_time": datetime.now().isoformat()
        }
        
        # 更新狀態
        self.state_manager.update_user_state(
            self.current_user,
            range_info,
            self.forget_punch_usage
        )
        
        # 儲存狀態檔案
        self.state_manager.save_state()
        logger.info("💾 已更新處理狀態: %s 至 %s", start_date, end_date)
    
    
    
    def generate_report(self) -> str:
        """生成報告（支援增量分析資訊顯示）"""
        report = []
        report.append("# 🎯 考勤分析報告 ✨\n")
        
        # 顯示增量分析資訊
        if self.incremental_mode and self.current_user:
            complete_days = self._identify_complete_work_days()
            unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
            from lib.report import build_incremental_lines
            report.extend(
                build_incremental_lines(
                    self.current_user,
                    len(complete_days),
                    len(unprocessed_dates),
                    [d.strftime('%Y/%m/%d') for d in unprocessed_dates],
                )
            )
        
        # 忘刷卡建議
        forget_punch_issues = [issue for issue in self.issues if issue.type == IssueType.FORGET_PUNCH]
        from lib.report import build_issue_section, build_summary
        report.extend(
            build_issue_section("## 🔄 建議使用忘刷卡的日期：", "🔄", forget_punch_issues)
        )
        
        # 遲到統計
        late_issues = [issue for issue in self.issues if issue.type == IssueType.LATE]
        report.extend(
            build_issue_section("## 😰 需要請遲到的日期：", "😅", late_issues)
        )
        
        # 加班統計
        overtime_issues = [issue for issue in self.issues if issue.type == IssueType.OVERTIME]
        report.extend(
            build_issue_section("## 💪 需要請加班的日期：", "🔥", overtime_issues)
        )
        
        # 週一到週四請假建議
        weekday_leave_issues = [issue for issue in self.issues if issue.type == IssueType.WEEKDAY_LEAVE]
        if weekday_leave_issues:
            report.append("## 📝 需要請假的日期：\n")
            for i, issue in enumerate(weekday_leave_issues, 1):
                weekday_name = ['週一', '週二', '週三', '週四', '週五', '週六', '週日'][issue.date.weekday()]
                report.append(f"{i}. **{issue.date.strftime('%Y/%m/%d')} ({weekday_name})** - 📝 {issue.description}")
            report.append("")
        
        # WFH建議
        wfh_issues = [issue for issue in self.issues if issue.type == IssueType.WFH]
        if wfh_issues:
            report.append("## 🏠 建議申請WFH假的日期：\n")
            for i, issue in enumerate(wfh_issues, 1):
                report.append(f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - 😊 {issue.description}")
            report.append("")
        
        # 統計摘要
        report.extend(
            build_summary(
                len(forget_punch_issues),
                len(late_issues),
                len(overtime_issues),
                len(weekday_leave_issues),
                len(wfh_issues),
            )
        )
        
        return "\n".join(report)
    
    def export_csv(self, filepath: str) -> None:
        """匯出CSV格式報告（委派至 lib.csv_exporter）"""
        from lib import csv_exporter

        status_tuple = None
        if self.incremental_mode and not self.issues and self.current_user:
            status_tuple = self._compute_incremental_status_row()

        csv_exporter.save_csv(filepath, self.issues, self.incremental_mode, status_tuple)
    
    def export_excel(self, filepath: str) -> None:
        """匯出Excel格式報告（直接使用 openpyxl，避免循環導入）"""
        # Probe legacy exporter availability to keep warning behavior for tests
        try:
            from lib import excel_exporter  # noqa: F401
        except Exception:
            logger.warning("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            logger.info("💡 安裝指令: pip install openpyxl")
            csv_filepath = filepath.replace('.xlsx', '.csv')
            self.export_csv(csv_filepath)
            logger.info("✅ CSV報告已匯出: %s", csv_filepath)
            return
        try:
            from openpyxl import Workbook  # type: ignore
        except Exception:
            logger.warning("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            logger.info("💡 安裝指令: pip install openpyxl")
            csv_filepath = filepath.replace('.xlsx', '.csv')
            self.export_csv(csv_filepath)
            logger.info("✅ CSV報告已匯出: %s", csv_filepath)
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "考勤分析"
        headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
        if self.incremental_mode:
            headers.append('狀態')
        ws.append(headers)

        data_start_appended = False
        if self.incremental_mode and not self.issues and self.current_user:
            status_tuple = self._compute_incremental_status_row()
            if status_tuple:
                last_date, total, last_time = status_tuple
                ws.append([
                    last_date, '狀態資訊', 0,
                    f"📊 增量分析完成，已處理至 {last_date}，共 {total} 個完整工作日 | 上次分析時間: {last_time}",
                    '', '','系統狀態'
                ])
                data_start_appended = True

        for issue in self.issues:
            row = [
                issue.date.strftime('%Y/%m/%d'),
                issue.type.value,
                issue.duration_minutes,
                issue.description,
                issue.time_range,
                issue.calculation,
            ]
            if self.incremental_mode:
                row.append('[NEW] 本次新發現' if issue.is_new else '已存在')
            ws.append(row)

        # Atomic write
        tmp_path = filepath + '.tmp'
        wb.save(tmp_path)
        import os as _os
        _os.replace(tmp_path, filepath)
        return

    def _compute_incremental_status_row(self) -> Optional[Tuple[str, int, str]]:
        complete_days = self._identify_complete_work_days()
        if not complete_days:
            return None
        unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days) if self.current_user else []
        if unprocessed_dates:
            return None
        last_date = max(complete_days).strftime('%Y/%m/%d')
        last_time = ""
        if self.state_manager and self.current_user:
            last_time = self.state_manager.get_last_analysis_time(self.current_user)
        return (last_date, len(complete_days), last_time)

        

    def export_report(self, filepath: str, format_type: str = 'excel') -> None:
        """統一匯出介面
        Args:
            filepath: 檔案路徑
            format_type: 'excel' 或 'csv'
        """
        # 匯出前先備份現有檔案（移至 lib.backup）
        from lib.backup import backup_with_timestamp
        backup_path = backup_with_timestamp(filepath)
        if backup_path:
            logger.info("📦 備份現有檔案: %s", os.path.basename(backup_path))
        
        if format_type.lower() == 'csv':
            self.export_csv(filepath)
        else:
            self.export_excel(filepath)


def main():
    """主程式（委派至 lib.cli.run）"""
    from lib.cli import run
    run()


if __name__ == "__main__":
    main()

# Typing-time imports to satisfy static analyzers without importing at runtime.
if TYPE_CHECKING:  # pragma: no cover
    from lib.state import AttendanceStateManager  # noqa: F401

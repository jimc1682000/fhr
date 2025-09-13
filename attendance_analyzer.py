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
from typing import List, Dict, Tuple, Optional
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
    
    # 公司規則常數（可由設定檔覆蓋）
    EARLIEST_CHECKIN = "08:30"
    LATEST_CHECKIN = "10:30"
    LUNCH_START = "12:30"
    LUNCH_END = "13:30"
    WORK_HOURS = 8
    LUNCH_HOURS = 1
    MIN_OVERTIME_MINUTES = 60
    OVERTIME_INCREMENT_MINUTES = 60  # 改為每小時一個區間
    FORGET_PUNCH_ALLOWANCE_PER_MONTH = 2  # 每月忘刷卡次數
    FORGET_PUNCH_MAX_MINUTES = 60  # 忘刷卡最多可用於60分鐘內的遲到

    def __init__(self, config_path: str = "config.json"):
        self._load_config(config_path)
        self.records: List[AttendanceRecord] = []
        self.workdays: List[WorkDay] = []
        self.issues: List[Issue] = []
        self.holidays: set = set()  # 存放國定假日日期
        self.forget_punch_usage: Dict[str, int] = defaultdict(int)  # 追蹤每月忘刷卡使用次數 {年月: 次數}
        self.loaded_holiday_years: set = set()  # 追蹤已載入假日的年份
        self.state_manager: Optional[AttendanceStateManager] = None
        self.current_user: Optional[str] = None
        self.incremental_mode: bool = True

    def _load_config(self, config_path: str) -> None:
        """載入設定檔以覆蓋預設公司規則"""
        if not os.path.exists(config_path):
            logger.info("找不到設定檔 %s，使用預設值", config_path)
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("無法讀取設定檔 %s: %s", config_path, e)
    
    
    def _identify_complete_work_days(self) -> List[datetime]:
        """識別完整的工作日（有上班和下班記錄的日期）
        Returns:
            完整工作日的日期清單
        """
        complete_days = []
        daily_records = defaultdict(lambda: {'checkin': False, 'checkout': False})

        # 按日期分組記錄
        for record in self.records:
            if not record.date:
                continue

            if record.type == AttendanceType.CHECKIN:
                daily_records[record.date]['checkin'] = True
            else:
                daily_records[record.date]['checkout'] = True
        
        # 找出有上班和下班記錄的完整工作日
        for date, records in daily_records.items():
            if records['checkin'] and records['checkout']:
                complete_days.append(datetime.combine(date, datetime.min.time()))
        
        return sorted(complete_days)
    
    def _get_unprocessed_dates(self, user_name: str, complete_days: List[datetime]) -> List[datetime]:
        """取得需要處理的新日期（排除已處理的重疊日期）
        Args:
            user_name: 使用者姓名
            complete_days: 完整工作日清單
        Returns:
            需要處理的日期清單
        """
        if not self.state_manager or not self.incremental_mode:
            return complete_days
        
        processed_ranges = self.state_manager.get_user_processed_ranges(user_name)
        unprocessed_dates = []
        
        for day in complete_days:
            day_str = day.strftime("%Y-%m-%d")
            is_processed = False
            
            # 檢查這個日期是否已在之前處理過的範圍內
            for range_info in processed_ranges:
                if range_info["start_date"] <= day_str <= range_info["end_date"]:
                    is_processed = True
                    break
            
            if not is_processed:
                unprocessed_dates.append(day)
        
        return unprocessed_dates
    
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
        """從出勤記錄中提取年份"""
        years = set()
        for record in self.records:
            if record.date:
                years.add(record.date.year)
        return years
    
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
        
        # 增量分析模式：只分析新的完整工作日
        if self.incremental_mode and self.current_user:
            complete_days = self._identify_complete_work_days()
            unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
            
            if unprocessed_dates:
                logger.info("🔄 增量分析: 發現 %d 個新的完整工作日需要處理", len(unprocessed_dates))
                logger.info("📊 跳過已處理的工作日: %d 個", len(complete_days) - len(unprocessed_dates))
                
                # 只分析未處理的工作日
                unprocessed_date_set = {d.date() for d in unprocessed_dates}
                workdays_to_analyze = [wd for wd in self.workdays if wd.date.date() in unprocessed_date_set]
            else:
                logger.info("✅ 增量分析: 沒有新的工作日需要處理")
                workdays_to_analyze = []
        else:
            # 完整分析模式：分析所有工作日
            workdays_to_analyze = self.workdays
        
        from lib.policy import Rules, is_full_day_absent, calculate_late_minutes, calculate_overtime_minutes
        rules = Rules(
            earliest_checkin=self.EARLIEST_CHECKIN,
            latest_checkin=self.LATEST_CHECKIN,
            lunch_start=self.LUNCH_START,
            lunch_end=self.LUNCH_END,
            work_hours=self.WORK_HOURS,
            lunch_hours=self.LUNCH_HOURS,
            min_overtime_minutes=self.MIN_OVERTIME_MINUTES,
            overtime_increment_minutes=self.OVERTIME_INCREMENT_MINUTES,
            forget_punch_allowance_per_month=self.FORGET_PUNCH_ALLOWANCE_PER_MONTH,
            forget_punch_max_minutes=self.FORGET_PUNCH_MAX_MINUTES,
        )

        for workday in workdays_to_analyze:
            # 檢查是否整天沒有打卡記錄（曠職）
            if is_full_day_absent(workday):
                if workday.is_friday and not workday.is_holiday:
                    # 週五且非國定假日建議WFH假
                    self.issues.append(Issue(
                        date=workday.date,
                        type=IssueType.WFH,
                        duration_minutes=9 * 60,  # 9小時
                        description="建議申請整天WFH假 🏠💻"
                    ))
                elif not workday.is_holiday:
                    # 非國定假日的週一到週四建議請假
                    self.issues.append(Issue(
                        date=workday.date,
                        type=IssueType.WEEKDAY_LEAVE,
                        duration_minutes=8 * 60,  # 8小時
                        description="整天沒進公司，建議請假 📝🏠"
                    ))
                # 如果是國定假日，則不需要任何申請建議
                continue
            
            if workday.is_friday:
                # 週五已處理，跳過分析
                continue
            
            # 分析遲到
            late_minutes, late_time_range, late_calculation = calculate_late_minutes(workday, rules)
            if late_minutes > 0:
                # 檢查是否可以使用忘刷卡
                month_key = workday.date.strftime('%Y-%m')
                can_use_forget_punch = (
                    late_minutes <= self.FORGET_PUNCH_MAX_MINUTES and
                    self.forget_punch_usage[month_key] < self.FORGET_PUNCH_ALLOWANCE_PER_MONTH
                )
                
                if can_use_forget_punch:
                    # 使用忘刷卡
                    self.forget_punch_usage[month_key] += 1
                    self.issues.append(Issue(
                        date=workday.date,
                        type=IssueType.FORGET_PUNCH,
                        duration_minutes=0,  # 忘刷卡不需要請假
                        description=f"遲到{late_minutes}分鐘，建議使用忘刷卡 🔄✅",
                        time_range=late_time_range,
                        calculation=f"{late_calculation} (使用忘刷卡，本月剩餘: {self.FORGET_PUNCH_ALLOWANCE_PER_MONTH - self.forget_punch_usage[month_key]}次)"
                    ))
                else:
                    # 需要請遲到假
                    reason = "超過1小時" if late_minutes > self.FORGET_PUNCH_MAX_MINUTES else f"本月忘刷卡額度已用完"
                    self.issues.append(Issue(
                        date=workday.date,
                        type=IssueType.LATE,
                        duration_minutes=late_minutes,
                        description=f"遲到{late_minutes}分鐘 ⏱️ ({reason})",
                        time_range=late_time_range,
                        calculation=late_calculation
                    ))
            
            # 分析加班
            actual_overtime, applicable_overtime, overtime_time_range, overtime_calculation = calculate_overtime_minutes(workday, rules)
            if applicable_overtime >= self.MIN_OVERTIME_MINUTES:
                self.issues.append(Issue(
                    date=workday.date,
                    type=IssueType.OVERTIME,
                    duration_minutes=applicable_overtime,
                    description=f"加班{applicable_overtime // 60}小時{applicable_overtime % 60}分鐘 💼",
                    time_range=overtime_time_range,
                    calculation=overtime_calculation
                ))
        
        # 增量分析模式：更新狀態
        if self.incremental_mode and self.current_user and workdays_to_analyze:
            self._update_processing_state()
    
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
            complete_days = self._identify_complete_work_days()
            if complete_days:
                last_date = max(complete_days).strftime('%Y/%m/%d')
                unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
                # 讀取上次分析時間
                last_analysis_time = ""
                if self.state_manager and self.current_user:
                    user_data = self.state_manager.state_data.get("users", {}).get(self.current_user, {})
                    ranges = user_data.get("processed_date_ranges", [])
                    if ranges:
                        last_analysis_time = max((r.get("last_analysis_time", "") for r in ranges), default="")
                if not unprocessed_dates:
                    status_tuple = (last_date, len(complete_days), last_analysis_time)

        csv_exporter.save_csv(filepath, self.issues, self.incremental_mode, status_tuple)
    
    def export_excel(self, filepath: str) -> None:
        """匯出Excel格式報告"""
        try:
            from lib import excel_exporter
        except ImportError:
            logger.warning("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            logger.info("💡 安裝指令: pip install openpyxl")
            csv_filepath = filepath.replace('.xlsx', '.csv')
            self.export_csv(csv_filepath)
            logger.info("✅ CSV報告已匯出: %s", csv_filepath)
            return

        wb, ws, header_font, header_fill, border, center_alignment = (
            excel_exporter.init_workbook()
        )

        headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
        if self.incremental_mode:
            headers.append('狀態')
        excel_exporter.write_headers(
            ws, headers, header_font, header_fill, border, center_alignment
        )

        data_start_row = 2
        if self.incremental_mode and not self.issues and self.current_user:
            complete_days = self._identify_complete_work_days()
            if complete_days:
                last_date = max(complete_days).strftime('%Y/%m/%d')
                unprocessed_dates = self._get_unprocessed_dates(
                    self.current_user, complete_days
                )
                # 讀取上次分析時間
                last_analysis_time = ""
                if self.state_manager and self.current_user:
                    user_data = self.state_manager.state_data.get("users", {}).get(self.current_user, {})
                    ranges = user_data.get("processed_date_ranges", [])
                    if ranges:
                        last_analysis_time = max((r.get("last_analysis_time", "") for r in ranges), default="")
                if not unprocessed_dates:
                    data_start_row = excel_exporter.write_status_row(
                        ws, last_date, len(complete_days), last_analysis_time, border, center_alignment
                    )

        excel_exporter.write_issue_rows(
            ws,
            self.issues,
            data_start_row,
            self.incremental_mode,
            border,
            center_alignment,
        )

        excel_exporter.set_column_widths(ws, self.incremental_mode)
        excel_exporter.save_workbook(wb, filepath)

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
    """主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='考勤分析系統 - 支援增量分析避免重複處理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例用法:
  # 預設增量分析（推薦）
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt
  
  # 強制完整重新分析
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt --full
  
  # 清除使用者狀態後重新分析
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt --reset-state
  
  # 指定輸出格式
  python attendance_analyzer.py 202508-員工姓名-出勤資料.txt csv
        """
    )
    
    parser.add_argument('filepath', help='考勤檔案路徑')
    parser.add_argument('format', nargs='?', default='excel', 
                       choices=['excel', 'csv'], help='輸出格式 (預設: excel)')
    parser.add_argument('--incremental', '-i', action='store_true', default=True,
                       help='啟用增量分析模式 (預設開啟)')
    parser.add_argument('--full', '-f', action='store_true',
                       help='強制完整重新分析')
    parser.add_argument('--reset-state', '-r', action='store_true',
                       help='清除指定使用者的狀態記錄')
    
    args = parser.parse_args()
    
    filepath = args.filepath
    format_type = args.format
    
    # 處理分析模式
    incremental_mode = args.incremental and not args.full
    
    # 處理狀態重設
    if args.reset_state:
        analyzer_temp = AttendanceAnalyzer()
        from lib.filename import parse_range_and_user
        from lib.state import AttendanceStateManager
        user_name, _, _ = parse_range_and_user(filepath)
        if user_name:
            state_manager = AttendanceStateManager()
            if user_name in state_manager.state_data.get("users", {}):
                del state_manager.state_data["users"][user_name]
                state_manager.save_state()
                logger.info("🗑️  狀態檔 'attendance_state.json' 已清除使用者 %s 的記錄 @ %s", user_name, datetime.now().isoformat())
            else:
                logger.info("ℹ️  使用者 %s 沒有現有狀態需要清除", user_name)
        else:
            logger.warning("⚠️  無法從檔名識別使用者，無法執行狀態重設")
            sys.exit(1)
    
    try:
        analyzer = AttendanceAnalyzer()
        
        # 顯示分析模式
        if incremental_mode:
            logger.info("📂 正在解析考勤檔案... (增量分析模式)")
        else:
            logger.info("📂 正在解析考勤檔案... (完整分析模式)")
            
        analyzer.parse_attendance_file(filepath, incremental=incremental_mode)
        
        logger.info("📝 正在分組記錄...")
        analyzer.group_records_by_day()
        
        logger.info("🔍 正在分析考勤...")
        analyzer.analyze_attendance()
        
        logger.info("📊 正在生成報告...")
        report = analyzer.generate_report()
        
        # 強制顯示完整報告，每行單獨輸出
        logger.info("\n")
        for line in report.split('\n'):
            logger.info(line)
        
        # 根據指定格式匯出（使用統一介面，包含自動備份）
        if format_type.lower() == 'csv':
            output_filepath = filepath.replace('.txt', '_analysis.csv')
            analyzer.export_report(output_filepath, 'csv')
            logger.info("✅ CSV報告已匯出: %s", output_filepath)
        else:
            output_filepath = filepath.replace('.txt', '_analysis.xlsx')
            analyzer.export_report(output_filepath, 'excel')
            logger.info("✅ Excel報告已匯出: %s", output_filepath)
        
        # 同時保留CSV格式（向後相容）
        if format_type.lower() == 'excel':
            csv_filepath = filepath.replace('.txt', '_analysis.csv')
            analyzer.export_report(csv_filepath, 'csv')
            logger.info("📝 同時匯出CSV格式: %s", csv_filepath)
        
    except Exception as e:
        logger.error("❌ 錯誤: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()

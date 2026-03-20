#!/usr/bin/env python3
"""
考勤分析系統
用於分析考勤記錄並計算遲到/加班時數
"""

import json
import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from lib.state import AttendanceStateManager

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class AttendanceType(Enum):
    CHECKIN = "上班"
    CHECKOUT = "下班"


class IssueType(Enum):
    LATE = "遲到"
    FORGET_PUNCH = "忘刷卡"
    OVERTIME = "加班"
    EARLY_LEAVE = "早退"
    WFH = "WFH假"
    WEEKDAY_LEAVE = "請假"


@dataclass
class AttendanceRecord:
    date: datetime
    scheduled_time: datetime | None
    actual_time: datetime | None
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
    checkin_record: AttendanceRecord | None
    checkout_record: AttendanceRecord | None
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

    def __init__(
        self,
        config_path: str = "config.json",
        debug: bool | None = None,
        unprocessed_only: bool = False,
    ):
        # 初始化配置
        from lib.config import AttendanceConfig

        self.config = AttendanceConfig()
        self._load_config(config_path)
        self.records: list[AttendanceRecord] = []
        self.workdays: list[WorkDay] = []
        self.issues: list[Issue] = []
        self.holidays: set = set()  # 存放國定假日日期
        # 追蹤每月忘刷卡使用次數 {年月: 次數}
        self.forget_punch_usage: dict[str, int] = defaultdict(int)
        self.loaded_holiday_years: set = set()  # 追蹤已載入假日的年份
        self.state_manager: AttendanceStateManager | None = None
        self.current_user: str | None = None
        self.incremental_mode: bool = True
        # 來源檔名（供狀態管理使用；API 模式時不依賴 sys.argv）
        self.source_file_name: str | None = None
        self.unprocessed_only: bool = unprocessed_only  # 是否只分析未處理的記錄
        if debug is None:
            debug = _env_flag("FHR_DEBUG", False)
        self.debug_mode = debug
        if self.debug_mode:
            logger.setLevel(logging.DEBUG)
            logger.debug("🐞 Debug 模式啟用：將輸出詳細日誌並停用狀態寫入。")

    def _load_config(self, config_path: str) -> None:
        """載入設定檔以覆蓋預設公司規則"""
        if not os.path.exists(config_path):
            logger.info("找不到設定檔 %s，使用預設值", config_path)
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    logger.debug("⚙️  覆寫設定 %s=%s", key, value)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("無法讀取設定檔 %s: %s", config_path, e)

    def _identify_complete_work_days(self) -> list[datetime]:
        """識別完整的工作日（委派至 lib.dates）"""
        from lib.dates import identify_complete_work_days

        return identify_complete_work_days(self.records)

    def _get_unprocessed_dates(
        self, user_name: str, complete_days: list[datetime]
    ) -> list[datetime]:
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
        url = f'https://data.gov.tw/api/v1/rest/datastore_search?resource_id=W2&filters={{"date":"{year}"}}'
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
        # 保存來源檔名供狀態管理記錄
        try:
            self.source_file_name = os.path.basename(filepath)
        except Exception:
            self.source_file_name = None

        # 初始化狀態管理器
        if self.incremental_mode:
            self.state_manager = AttendanceStateManager(read_only=self.debug_mode)

            # 解析檔名取得使用者資訊
            from lib.filename import parse_range_and_user

            user_name, start_date, end_date = parse_range_and_user(filepath)
            if user_name:
                self.current_user = user_name
                logger.info("📋 識別使用者: %s", user_name)
                logger.info("📅 檔案涵蓋期間: %s 至 %s", start_date, end_date)

                # 檢查重疊日期
                if start_date and end_date:
                    overlaps = self.state_manager.detect_date_overlap(
                        user_name, start_date, end_date
                    )
                    if overlaps:
                        logger.debug("發現重疊日期範圍: %s", overlaps)
                        logger.debug("將以舊資料為主，僅處理新日期")

                # 載入之前的忘刷卡使用統計
                self._load_previous_forget_punch_usage(user_name)
            else:
                logger.warning("⚠️  無法從檔名識別使用者，將使用完整分析模式")
                self.incremental_mode = False

        # 解析檔案內容
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
        logger.debug("📥  讀入檔案 %s，共 %d 行資料 (含表頭)", filepath, len(lines))

        parsed_records = 0
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
                    parsed_records += 1
            except (ValueError, IndexError) as e:
                logger.warning("第%d行解析失敗: %s", line_num, e)
        skipped_lines = max(len(lines) - 1 - parsed_records, 0)
        logger.debug(
            "✅  完成解析，有效紀錄 %d 筆，略過 %d 行",
            parsed_records,
            skipped_lines,
        )

        # 如果啟用 unprocessed_only，過濾掉已處理的記錄
        if self.unprocessed_only:
            original_count = len(self.records)
            self.records = [r for r in self.records if r.processed != "已處理"]
            filtered_count = original_count - len(self.records)
            if filtered_count > 0:
                logger.info(
                    "🔍 僅分析未處理記錄：過濾掉 %d 筆已處理記錄，保留 %d 筆未處理記錄",
                    filtered_count,
                    len(self.records),
                )

    def _parse_attendance_line(self, line: str) -> AttendanceRecord | None:
        """解析單行考勤記錄（委派至 lib.parser）"""
        from lib import parser as p

        parsed = p.parse_line(line)
        if not parsed:
            return None
        (
            scheduled_time,
            actual_time,
            type_str,
            card_num,
            source,
            status,
            processed,
            operation,
            note,
        ) = parsed
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
                checkin_record=records["checkin"],
                checkout_record=records["checkout"],
                is_friday=(date.weekday() == 4),  # 週五是4
                is_holiday=(date in self.holidays),  # 檢查是否為國定假日
            )
            self.workdays.append(workday)

        self.workdays.sort(key=lambda x: x.date)
        logger.debug(
            "📅  完成分組，共 %d 個工作日，其中假日 %d 天",
            len(self.workdays),
            sum(1 for w in self.workdays if w.is_holiday),
        )

    def analyze_attendance(self) -> None:
        """分析考勤記錄（支援增量分析）"""
        self.issues = []

        workdays_to_analyze = self._get_workdays_to_analyze()

        from lib.policy import Rules

        rules = Rules(
            schedule_start=self.config.schedule_start,
            schedule_end=self.config.schedule_end,
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

        for workday in workdays_to_analyze:
            self._analyze_single_workday(workday, rules)

        # 補上涵蓋月份中所有週五的 WFH 建議（方便提前請假）
        if workdays_to_analyze:
            self._add_monthly_wfh_issues()

        if self.incremental_mode and self.current_user and workdays_to_analyze:
            self._update_processing_state()
        logger.debug("🧮  分析完成，產生 %d 筆待處理事項", len(self.issues))

    @staticmethod
    def _is_workday_processed(workday: WorkDay) -> bool:
        """檢查工作日是否有任何記錄已標記為「已處理」"""
        for rec in (workday.checkin_record, workday.checkout_record):
            if rec and rec.processed == "已處理":
                return True
        return False

    def _filter_processed_workdays(self, workdays: list[WorkDay]) -> list[WorkDay]:
        """過濾掉已處理的工作日，回傳未處理的工作日清單"""
        filtered = [wd for wd in workdays if not self._is_workday_processed(wd)]
        skipped = len(workdays) - len(filtered)
        if skipped > 0:
            logger.info("⏭️  跳過已處理工作日: %d 天", skipped)
        return filtered

    def _get_workdays_to_analyze(self) -> list[WorkDay]:
        if self.incremental_mode and self.current_user:
            complete_days = self._identify_complete_work_days()
            unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
            if unprocessed_dates:
                logger.info("🔄 增量分析: 發現 %d 個新的完整工作日需要處理", len(unprocessed_dates))
                logger.info(
                    "📊 跳過已處理的工作日: %d 個", len(complete_days) - len(unprocessed_dates)
                )
                formatted_dates = [d.strftime("%Y-%m-%d") for d in unprocessed_dates]
                logger.debug("📆  新增待處理日期: %s", formatted_dates)
                unprocessed_date_set = {d.date() for d in unprocessed_dates}
                candidates = [wd for wd in self.workdays if wd.date.date() in unprocessed_date_set]
                return self._filter_processed_workdays(candidates)
            logger.info("✅ 增量分析: 沒有新的工作日需要處理")
            return []
        logger.debug("🗂️  非增量模式，將處理 %d 個工作日", len(self.workdays))
        return self._filter_processed_workdays(self.workdays)

    def _get_covered_months(self) -> set[tuple[int, int]]:
        """取得出勤資料涵蓋的所有月份 (year, month)"""
        months: set[tuple[int, int]] = set()
        for wd in self.workdays:
            d = wd.date
            months.add((d.year, d.month))
        return months

    def _add_monthly_wfh_issues(self) -> None:
        """補上涵蓋月份中所有週五的 WFH 建議，方便提前一次請完"""
        import calendar

        existing_wfh_dates = {
            issue.date.date() for issue in self.issues if issue.type == IssueType.WFH
        }

        covered_months = self._get_covered_months()
        added = 0
        for year, month in sorted(covered_months):
            cal = calendar.Calendar()
            for day in cal.itermonthdays2(year, month):
                date_num, weekday = day
                if date_num == 0 or weekday != 4:  # 只看週五
                    continue
                from datetime import date

                friday = date(year, month, date_num)
                if friday in existing_wfh_dates:
                    continue
                if friday in {d.date() if hasattr(d, "date") else d for d in self.holidays}:
                    continue
                self.issues.append(
                    Issue(
                        date=datetime.combine(friday, datetime.min.time()),
                        type=IssueType.WFH,
                        duration_minutes=9 * 60,
                        description="建議申請整天WFH假 🏠💻",
                    )
                )
                added += 1

        if added > 0:
            logger.info("📅 自動補上 %d 個週五 WFH 建議", added)
            # 重新排序所有 issues，確保日期順序正確
            self.issues.sort(key=lambda x: x.date)

    def _handle_absent_day(self, workday: WorkDay) -> bool:
        from lib.policy import is_full_day_absent

        if is_full_day_absent(workday):
            if workday.is_friday and not workday.is_holiday:
                self.issues.append(
                    Issue(
                        date=workday.date,
                        type=IssueType.WFH,
                        duration_minutes=9 * 60,
                        description="建議申請整天WFH假 🏠💻",
                    )
                )
            elif not workday.is_holiday:
                self.issues.append(
                    Issue(
                        date=workday.date,
                        type=IssueType.WEEKDAY_LEAVE,
                        duration_minutes=8 * 60,
                        description="整天沒進公司，建議請假 📝🏠",
                    )
                )
            return True
        return False

    def _analyze_single_workday(self, workday: WorkDay, rules) -> None:

        from lib.policy import (
            calculate_early_leave,
            calculate_expected_checkout,
            calculate_late_minutes,
            calculate_leave_suggestion,
            calculate_overtime_minutes,
        )

        if self._handle_absent_day(workday):
            return

        # 星期五優先建議 WFH（無論是否有打卡），除非是國定假日
        if workday.is_friday and not workday.is_holiday:
            self.issues.append(
                Issue(
                    date=workday.date,
                    type=IssueType.WFH,
                    duration_minutes=9 * 60,
                    description="建議申請整天WFH假 🏠💻",
                )
            )
            return

        # 1. 計算遲到（超過遲到門檻，從班表起始算起）
        late_minutes, late_time_range, late_calculation = calculate_late_minutes(workday, rules)

        # 2. 確定工作起始時間
        ch = workday.checkin_record
        actual_checkin = ch.actual_time

        work_start_time = actual_checkin

        # 3. 處理遲到情況（全部走請假）
        if late_minutes > 0:
            leave_start, leave_end, leave_hours = calculate_leave_suggestion(
                workday, rules, late_minutes
            )

            self.issues.append(
                Issue(
                    date=workday.date,
                    type=IssueType.LATE,
                    duration_minutes=late_minutes,
                    description=f"遲到{late_minutes}分鐘 ⏱️",
                    time_range=f"{leave_start}~{leave_end}",
                    calculation=f"建議請假 {leave_hours} 小時: {leave_start}~{leave_end}",
                )
            )

        # 4. 計算預期下班時間（遲到→班表結束；正常→到班+9h）
        expected_checkout = calculate_expected_checkout(workday, rules, work_start_time)

        # 5. 檢查早退
        early_leave_minutes, early_leave_range, early_leave_calc = calculate_early_leave(
            workday, rules, expected_checkout
        )
        if early_leave_minutes > 0:
            self.issues.append(
                Issue(
                    date=workday.date,
                    type=IssueType.EARLY_LEAVE,
                    duration_minutes=early_leave_minutes,
                    description=f"早退{early_leave_minutes}分鐘 ⏰",
                    time_range=early_leave_range,
                    calculation=early_leave_calc,
                )
            )

        # 6. 檢查加班
        (
            _actual_overtime,
            applicable_overtime,
            overtime_time_range,
            overtime_calculation,
        ) = calculate_overtime_minutes(workday, rules, expected_checkout)

        if applicable_overtime >= self.config.min_overtime_minutes:
            overtime_hours = applicable_overtime // 60
            overtime_minutes = applicable_overtime % 60
            overtime_desc = f"加班{overtime_hours}小時{overtime_minutes}分鐘 💼"
            self.issues.append(
                Issue(
                    date=workday.date,
                    type=IssueType.OVERTIME,
                    duration_minutes=applicable_overtime,
                    description=overtime_desc,
                    time_range=overtime_time_range,
                    calculation=overtime_calculation,
                )
            )

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
            # 優先使用已知來源檔名；保持與 CLI 相容的後備行為
            "source_file": (
                self.source_file_name
                or (os.path.basename(sys.argv[1]) if len(sys.argv) > 1 else "unknown")
            ),
            "last_analysis_time": datetime.now().isoformat(),
        }

        # 更新狀態
        self.state_manager.update_user_state(self.current_user, range_info, self.forget_punch_usage)

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
                    [d.strftime("%Y/%m/%d") for d in unprocessed_dates],
                )
            )

        # 忘刷卡建議
        forget_punch_issues = [
            issue for issue in self.issues if issue.type == IssueType.FORGET_PUNCH
        ]
        from lib.report import build_issue_section, build_summary

        report.extend(
            build_issue_section("## 🔄 建議使用忘刷卡的日期：", "🔄", forget_punch_issues)
        )

        # 遲到統計
        late_issues = [issue for issue in self.issues if issue.type == IssueType.LATE]
        report.extend(build_issue_section("## 😰 需要請遲到的日期：", "😅", late_issues))

        # 加班統計
        overtime_issues = [issue for issue in self.issues if issue.type == IssueType.OVERTIME]
        report.extend(build_issue_section("## 💪 需要請加班的日期：", "🔥", overtime_issues))

        # 早退統計
        early_leave_issues = [issue for issue in self.issues if issue.type == IssueType.EARLY_LEAVE]
        report.extend(build_issue_section("## ⏰ 早退需要請假的日期：", "⏰", early_leave_issues))

        # 週一到週四請假建議
        weekday_leave_issues = [
            issue for issue in self.issues if issue.type == IssueType.WEEKDAY_LEAVE
        ]
        if weekday_leave_issues:
            report.append("## 📝 需要請假的日期：\n")
            for i, issue in enumerate(weekday_leave_issues, 1):
                weekday_name = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][
                    issue.date.weekday()
                ]
                report.append(
                    f"{i}. **{issue.date.strftime('%Y/%m/%d')} ({weekday_name})** - "
                    f"📝 {issue.description}"
                )
            report.append("")

        # WFH建議
        wfh_issues = [issue for issue in self.issues if issue.type == IssueType.WFH]
        if wfh_issues:
            report.append("## 🏠 建議申請WFH假的日期：\n")
            for i, issue in enumerate(wfh_issues, 1):
                report.append(
                    f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - 😊 {issue.description}"
                )
            report.append("")

        # 統計摘要
        report.extend(
            build_summary(
                len(forget_punch_issues),
                len(late_issues),
                len(overtime_issues),
                len(early_leave_issues),
                len(weekday_leave_issues),
                len(wfh_issues),
            )
        )

        return "\n".join(report)

    def export_csv(self, filepath: str, merge: bool = False) -> None:
        """匯出CSV格式報告（委派至 lib.csv_exporter）"""
        from lib import csv_exporter

        status_tuple = None
        if self.incremental_mode and not self.issues and self.current_user:
            status_tuple = self._compute_incremental_status_row()

        csv_exporter.save_csv(
            filepath,
            self.issues,
            self.incremental_mode,
            status_tuple,
            merge=merge,
        )

    def export_excel(self, filepath: str) -> None:
        """匯出Excel格式報告（直接使用 openpyxl，避免循環導入）"""
        # Probe legacy exporter availability to keep warning behavior for tests
        try:
            from lib import excel_exporter  # noqa: F401
        except Exception:
            logger.warning("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            logger.info("💡 安裝指令: pip install openpyxl")
            csv_filepath = filepath.replace(".xlsx", ".csv")
            self.export_csv(csv_filepath)
            logger.info("✅ CSV報告已匯出: %s", csv_filepath)
            return
        try:
            from openpyxl import Workbook  # type: ignore
        except Exception:
            logger.warning("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            logger.info("💡 安裝指令: pip install openpyxl")
            csv_filepath = filepath.replace(".xlsx", ".csv")
            self.export_csv(csv_filepath)
            logger.info("✅ CSV報告已匯出: %s", csv_filepath)
            return

        wb = Workbook()
        ws = wb.active
        ws.title = "考勤分析"
        headers = ["日期", "類型", "時長(分鐘)", "說明", "時段", "計算式"]
        if self.incremental_mode:
            headers.append("狀態")
        ws.append(headers)

        # data_start_appended = False  # Variable assigned but never used
        if self.incremental_mode and not self.issues and self.current_user:
            status_tuple = self._compute_incremental_status_row()
            if status_tuple:
                last_date, total, last_time = status_tuple
                ws.append(
                    [
                        last_date,
                        "狀態資訊",
                        0,
                        (
                            f"📊 增量分析完成，已處理至 {last_date}，共 {total} 個完整工作日 | "
                            f"上次分析時間: {last_time}"
                        ),
                        "",
                        "",
                        "系統狀態",
                    ]
                )
                # data_start_appended = True  # Variable assigned but never used

        for issue in self.issues:
            row = [
                issue.date.strftime("%Y/%m/%d"),
                issue.type.value,
                issue.duration_minutes,
                issue.description,
                issue.time_range,
                issue.calculation,
            ]
            if self.incremental_mode:
                row.append("[NEW] 本次新發現" if issue.is_new else "已存在")
            ws.append(row)

        # Atomic write
        tmp_path = filepath + ".tmp"
        wb.save(tmp_path)
        import os as _os

        _os.replace(tmp_path, filepath)
        return

    def _compute_incremental_status_row(self) -> tuple[str, int, str] | None:
        complete_days = self._identify_complete_work_days()
        if not complete_days:
            return None
        unprocessed_dates = (
            self._get_unprocessed_dates(self.current_user, complete_days)
            if self.current_user
            else []
        )
        if unprocessed_dates:
            return None
        last_date = max(complete_days).strftime("%Y/%m/%d")
        last_time = ""
        if self.state_manager and self.current_user:
            last_time = self.state_manager.get_last_analysis_time(self.current_user)
        return (last_date, len(complete_days), last_time)

    def export_report(
        self,
        filepath: str,
        format_type: str = "excel",
        export_policy: str = "merge",
    ) -> str | None:
        """統一匯出介面
        Args:
            filepath: 檔案路徑
            format_type: 'excel' 或 'csv'
        """
        backup_path = None

        if export_policy == "archive":
            from lib.backup import backup_with_timestamp

            backup_path = backup_with_timestamp(filepath)
            if backup_path:
                logger.info("📦 備份現有檔案: %s", os.path.basename(backup_path))
        elif export_policy != "merge":
            raise ValueError(f"Unknown export policy: {export_policy}")

        if format_type.lower() == "csv":
            self.export_csv(filepath, merge=(export_policy == "merge"))
        else:
            self.export_excel(filepath)

        return backup_path


def main():
    """主程式（委派至 lib.cli.run）"""
    from lib.cli import run

    run()


if __name__ == "__main__":
    main()

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
import time
import ssl
import random
import socket
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


class AttendanceStateManager:
    """考勤狀態管理器 - 負責讀寫增量分析狀態"""
    
    def __init__(self, state_file: str = "attendance_state.json"):
        self.state_file = state_file
        self.state_data = self._load_state()
    
    def _load_state(self) -> dict:
        """載入狀態檔案"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("無法讀取狀態檔案 %s: %s", self.state_file, e)
                logger.warning("將使用空白狀態")
        
        # 回傳預設空狀態
        return {"users": {}}
    
    def save_state(self) -> None:
        """儲存狀態到檔案"""
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("無法儲存狀態檔案 %s: %s", self.state_file, e)
    
    def get_user_processed_ranges(self, user_name: str) -> List[Dict]:
        """取得使用者已處理的日期範圍"""
        if user_name not in self.state_data["users"]:
            return []
        return self.state_data["users"][user_name].get("processed_date_ranges", [])
    
    def get_forget_punch_usage(self, user_name: str, year_month: str) -> int:
        """取得使用者在特定月份的忘刷卡使用次數"""
        if user_name not in self.state_data["users"]:
            return 0
        return self.state_data["users"][user_name].get("forget_punch_usage", {}).get(year_month, 0)
    
    def update_user_state(self, user_name: str, new_range: Dict[str, str], 
                         forget_punch_usage: Dict[str, int] = None) -> None:
        """更新使用者狀態
        Args:
            user_name: 使用者姓名
            new_range: 新的日期範圍資訊 {'start_date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD', 'source_file': 'filename', 'last_analysis_time': 'ISO格式時間'}
            forget_punch_usage: 忘刷卡使用統計 {'YYYY-MM': count}
        """
        if user_name not in self.state_data["users"]:
            self.state_data["users"][user_name] = {
                "processed_date_ranges": [],
                "forget_punch_usage": {}
            }
        
        user_data = self.state_data["users"][user_name]
        
        # 檢查是否有重疊的範圍需要合併或更新
        existing_ranges = user_data["processed_date_ranges"]
        updated = False
        
        for i, existing_range in enumerate(existing_ranges):
            if existing_range["source_file"] == new_range["source_file"]:
                # 相同來源檔案，更新資訊
                existing_ranges[i] = new_range
                updated = True
                break
        
        if not updated:
            # 新的來源檔案，加入清單
            existing_ranges.append(new_range)
        
        # 更新忘刷卡使用統計
        if forget_punch_usage:
            user_data["forget_punch_usage"].update(forget_punch_usage)
    
    def detect_date_overlap(self, user_name: str, new_start_date: str, new_end_date: str) -> List[Tuple[str, str]]:
        """檢測新日期範圍與現有範圍的重疊部分
        Args:
            user_name: 使用者姓名
            new_start_date: 新範圍開始日期 'YYYY-MM-DD'
            new_end_date: 新範圍結束日期 'YYYY-MM-DD'
        Returns:
            重疊的日期範圍清單 [(start_date, end_date), ...]
        """
        overlaps = []
        existing_ranges = self.get_user_processed_ranges(user_name)
        
        new_start = datetime.strptime(new_start_date, "%Y-%m-%d").date()
        new_end = datetime.strptime(new_end_date, "%Y-%m-%d").date()
        
        for range_info in existing_ranges:
            existing_start = datetime.strptime(range_info["start_date"], "%Y-%m-%d").date()
            existing_end = datetime.strptime(range_info["end_date"], "%Y-%m-%d").date()
            
            # 檢查是否有重疊
            if new_start <= existing_end and new_end >= existing_start:
                # 計算重疊範圍
                overlap_start = max(new_start, existing_start)
                overlap_end = min(new_end, existing_end)
                overlaps.append((overlap_start.strftime("%Y-%m-%d"), overlap_end.strftime("%Y-%m-%d")))
        
        return overlaps


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
    
    def _extract_user_and_date_range_from_filename(self, filepath: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """從檔案名稱解析使用者姓名和日期範圍
        支援格式: {YYYYMM}[-{YYYYMM}]-{NAME}-出勤資料.txt
        
        Args:
            filepath: 檔案路徑
        
        Returns:
            Tuple[使用者姓名, 開始日期YYYY-MM-DD, 結束日期YYYY-MM-DD]
        """
        filename = os.path.basename(filepath)
        
        # 匹配模式: YYYYMM[-YYYYMM]-NAME-出勤資料.txt
        pattern = r'(\d{6})(?:-(\d{6}))?-(.+?)-出勤資料\.txt$'
        match = re.match(pattern, filename)
        
        if not match:
            logger.warning("檔案名稱格式不符合規範: %s", filename)
            logger.warning("預期格式: YYYYMM[-YYYYMM]-姓名-出勤資料.txt")
            return None, None, None
        
        start_month_str = match.group(1)  # YYYYMM
        end_month_str = match.group(2)    # YYYYMM 或 None
        user_name = match.group(3)        # 姓名
        
        # 解析開始日期
        try:
            start_year = int(start_month_str[:4])
            start_month = int(start_month_str[4:6])
            start_date = datetime(start_year, start_month, 1).strftime("%Y-%m-%d")
        except ValueError:
            logger.warning("無法解析開始月份: %s", start_month_str)
            return None, None, None
        
        # 解析結束日期
        if end_month_str:
            # 跨月檔案
            try:
                end_year = int(end_month_str[:4])
                end_month = int(end_month_str[4:6])
                # 取該月最後一天
                if end_month == 12:
                    next_month = datetime(end_year + 1, 1, 1)
                else:
                    next_month = datetime(end_year, end_month + 1, 1)
                end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                logger.warning("無法解析結束月份: %s", end_month_str)
                return None, None, None
        else:
            # 單月檔案
            try:
                # 取該月最後一天
                if start_month == 12:
                    next_month = datetime(start_year + 1, 1, 1)
                else:
                    next_month = datetime(start_year, start_month + 1, 1)
                end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
            except ValueError:
                logger.warning("無法計算月份結束日期")
                return None, None, None
        
        return user_name, start_date, end_date
    
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
                if year == 2025:
                    self._load_hardcoded_2025_holidays()
                else:
                    self._load_dynamic_holidays(year)
                self.loaded_holiday_years.add(year)
    
    def _load_hardcoded_2025_holidays(self) -> None:
        """載入硬編碼的2025年國定假日（高效能）"""
        # 2025年(民國114年)國定假日清單
        taiwan_holidays_2025 = [
            # 元旦連假
            "2025/01/01",
            # 農曆春節
            "2025/01/25", "2025/01/26", "2025/01/27", "2025/01/28", "2025/01/29", "2025/01/30", "2025/01/31", "2025/02/01", "2025/02/02",
            # 和平紀念日
            "2025/02/28", "2025/03/01", "2025/03/02",
            # 兒童節/清明節
            "2025/04/03", "2025/04/04", "2025/04/05", "2025/04/06",
            # 端午節
            "2025/05/30", "2025/05/31", "2025/06/01",
            # 中秋節
            "2025/10/04", "2025/10/05", "2025/10/06",
            # 國慶日
            "2025/10/10", "2025/10/11", "2025/10/12",
        ]
        
        for holiday_str in taiwan_holidays_2025:
            try:
                holiday_date = datetime.strptime(holiday_str, "%Y/%m/%d").date()
                self.holidays.add(holiday_date)
            except ValueError:
                logger.warning("無法解析國定假日日期: %s", holiday_str)
    
    def _load_dynamic_holidays(self, year: int) -> None:
        """動態載入指定年份的國定假日
        Args:
            year: 要載入的年份
        """
        logger.info("資訊: 動態載入 %d 年國定假日...", year)
        
        # 方案1: 使用政府開放資料API
        success = self._try_load_from_gov_api(year)
        
        if not success:
            # 方案2: 使用基本假日規則（元旦、國慶日等固定日期）
            self._load_basic_holidays(year)
            logger.warning("無法取得 %d 年完整假日資料，僅載入基本固定假日", year)
    
    def _try_load_from_gov_api(self, year: int) -> bool:
        """嘗試從政府開放資料API載入假日
        Args:
            year: 要載入的年份
        Returns:
            bool: 是否成功載入
        """
        import urllib.request
        import urllib.error
        import json as _json
        from urllib.error import URLError, HTTPError

        # API設定
        url = "https://data.gov.tw/api/v1/rest/datastore_search?resource_id=W2&filters={\"date\":\"%s\"}" % year
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            logger.warning("不支援的 URL scheme: %s", parsed.scheme)
            return False
        context = ssl.create_default_context()

        # 重試與退避參數
        try:
            max_retries = int(os.getenv("HOLIDAY_API_MAX_RETRIES", "3"))
        except ValueError:
            max_retries = 3
        try:
            base_backoff = float(os.getenv("HOLIDAY_API_BACKOFF_BASE", "0.5"))
        except ValueError:
            base_backoff = 0.5
        try:
            max_backoff = float(os.getenv("HOLIDAY_API_MAX_BACKOFF", "8"))
        except ValueError:
            max_backoff = 8.0

        attempt = 0
        while attempt <= max_retries:
            attempt += 1
            try:
                logger.info("資訊: 嘗試載入 %d 年假日 (第 %d/%d 次)...", year, attempt, max_retries)
                with urllib.request.urlopen(url, timeout=10, context=context) as response:  # nosec B310
                    data = _json.loads(response.read().decode('utf-8'))
                    if 'result' in data and 'records' in data['result']:
                        added = 0
                        for record in data['result']['records']:
                            if record.get('isHoliday', 0) == 1:
                                date_str = record.get('date', '')
                                if date_str:
                                    try:
                                        holiday_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                                        self.holidays.add(holiday_date)
                                        added += 1
                                    except ValueError as e:
                                        logger.warning("跳過無效的日期格式 %r: %s", date_str, e)
                        if added > 0:
                            return True
                        logger.warning("API 回傳資料但沒有有效的假日記錄")
                        # 視為可重試
                        raise RuntimeError("empty holiday records")
            except HTTPError as e:
                status = getattr(e, 'code', None)
                if status in (429, 500, 502, 503, 504):
                    err_desc = f"HTTP {status}"
                else:
                    logger.warning("無法從API載入 %d 年假日資料: HTTP %s — 不重試。", year, status)
                    return False
            except (URLError, socket.timeout, TimeoutError, _json.JSONDecodeError, ValueError) as e:
                err_desc = f"連線/解析錯誤: {e}"
            except Exception as e:
                err_desc = f"一般錯誤: {e}"

            if attempt > max_retries:
                logger.error("錯誤: 嘗試 %d 次後仍無法載入 %d 年假日資料。回退到基本假日。", max_retries, year)
                break

            sleep_s = min(max_backoff, base_backoff * (2 ** (attempt - 1)))
            jitter = sleep_s * random.uniform(-0.1, 0.1)
            wait_s = max(0.0, sleep_s + jitter)
            logger.warning("%s，%.2f 秒後重試...", err_desc, wait_s)
            time.sleep(wait_s)

        return False

    def _load_basic_holidays(self, year: int) -> None:
        """載入基本固定假日（當API不可用時的備案）
        Args:
            year: 要載入的年份
        """
        basic_holidays = [
            f"{year}/01/01",  # 元旦
            f"{year}/10/10",  # 國慶日
        ]
        
        for holiday_str in basic_holidays:
            try:
                holiday_date = datetime.strptime(holiday_str, "%Y/%m/%d").date()
                self.holidays.add(holiday_date)
            except ValueError:
                logger.warning("無法解析基本假日日期: %s", holiday_str)
    
    def parse_attendance_file(self, filepath: str, incremental: bool = True) -> None:
        """解析考勤資料檔案並初始化增量處理
        Args:
            filepath: 檔案路徑
            incremental: 是否啟用增量分析
        """
        self.incremental_mode = incremental
        
        # 初始化狀態管理器
        if self.incremental_mode:
            self.state_manager = AttendanceStateManager()
            
            # 解析檔名取得使用者資訊
            user_name, start_date, end_date = self._extract_user_and_date_range_from_filename(filepath)
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
        """解析單行考勤記錄"""
        # 移除行號前綴
        line = re.sub(r'^\s*\d+→', '', line)
        
        # 分割欄位
        fields = line.split('\t')
        if len(fields) < 3:
            return None
        
        # 補齊欄位到9個
        while len(fields) < 9:
            fields.append('')
        
        scheduled_str, actual_str, type_str = fields[0], fields[1], fields[2]
        card_num, source, status = fields[3], fields[4], fields[5]
        processed, operation, note = fields[6], fields[7], fields[8]
        
        # 解析日期時間
        scheduled_time = self._parse_datetime(scheduled_str) if scheduled_str else None
        actual_time = self._parse_datetime(actual_str) if actual_str else None
        
        # 跳過無效記錄
        if not scheduled_time or type_str not in ["上班", "下班"]:
            return None
        
        # 解析考勤類型
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
            note=note
        )
    
    def _parse_datetime(self, datetime_str: str) -> Optional[datetime]:
        """解析日期時間字串"""
        try:
            return datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
        except ValueError:
            return None
    
    def group_records_by_day(self) -> None:
        """將記錄按日期分組"""
        # 在分組前，先載入出勤資料中涉及的年份假日
        years_in_data = self._get_years_from_records()
        if years_in_data:
            self._load_taiwan_holidays(years_in_data)
        
        daily_records = defaultdict(lambda: {'checkin': None, 'checkout': None})

        for record in self.records:
            if not record.date:
                continue

            if record.type == AttendanceType.CHECKIN:
                daily_records[record.date]['checkin'] = record
            else:
                daily_records[record.date]['checkout'] = record
        
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
        
        for workday in workdays_to_analyze:
            # 檢查是否整天沒有打卡記錄（曠職）
            if self._is_full_day_absent(workday):
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
            late_minutes, late_time_range, late_calculation = self._calculate_late_minutes(workday)
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
            actual_overtime, applicable_overtime, overtime_time_range, overtime_calculation = self._calculate_overtime_minutes(workday)
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
    
    def _calculate_late_minutes(self, workday: WorkDay) -> tuple:
        """計算遲到分鐘數，返回 (分鐘數, 時段, 計算式)"""
        if not workday.checkin_record or not workday.checkin_record.actual_time:
            return 0, "", ""
        
        latest_checkin = datetime.strptime(f"{workday.date.strftime('%Y/%m/%d')} {self.LATEST_CHECKIN}", "%Y/%m/%d %H:%M")
        actual_checkin = workday.checkin_record.actual_time
        
        if actual_checkin > latest_checkin:
            delta = actual_checkin - latest_checkin
            late_minutes = int(delta.total_seconds() // 60)
            
            # 如果遲到超過2小時，需要扣除午休時間
            if late_minutes > 120:  # 超過2小時
                lunch_start = datetime.strptime(f"{workday.date.strftime('%Y/%m/%d')} {self.LUNCH_START}", "%Y/%m/%d %H:%M")
                lunch_end = datetime.strptime(f"{workday.date.strftime('%Y/%m/%d')} {self.LUNCH_END}", "%Y/%m/%d %H:%M")
                
                # 如果上班時間跨越午休時段，扣除午休時間
                if actual_checkin > lunch_start:
                    late_minutes -= 60  # 扣除1小時午休
                    calculation = f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {self.LATEST_CHECKIN}, 遲到: {int(delta.total_seconds() // 60)}分鐘 - 60分鐘午休 = {late_minutes}分鐘"
                else:
                    calculation = f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {self.LATEST_CHECKIN}, 遲到: {late_minutes}分鐘"
            else:
                calculation = f"實際上班: {actual_checkin.strftime('%H:%M')}, 最晚上班: {self.LATEST_CHECKIN}, 遲到: {late_minutes}分鐘"
            
            time_range = f"{self.LATEST_CHECKIN}~{actual_checkin.strftime('%H:%M')}"
            return late_minutes, time_range, calculation
        
        return 0, "", ""
    
    def _calculate_overtime_minutes(self, workday: WorkDay) -> tuple:
        """計算加班分鐘數，返回 (實際分鐘數, 可申請分鐘數, 時段, 計算式)"""
        if (not workday.checkin_record or not workday.checkin_record.actual_time or
            not workday.checkout_record or not workday.checkout_record.actual_time):
            return 0, 0, "", ""
        
        checkin_time = workday.checkin_record.actual_time
        checkout_time = workday.checkout_record.actual_time
        
        # 計算應下班時間 = 上班時間 + 8小時工作 + 1小時午休
        expected_checkout = checkin_time + timedelta(hours=self.WORK_HOURS + self.LUNCH_HOURS)
        
        if checkout_time > expected_checkout:
            delta = checkout_time - expected_checkout
            actual_overtime_minutes = int(delta.total_seconds() // 60)
            
            # 按半小時間隔計算可申請時數
            if actual_overtime_minutes >= self.MIN_OVERTIME_MINUTES:
                # 計算可申請的半小時間隔數
                intervals = (actual_overtime_minutes - self.MIN_OVERTIME_MINUTES) // self.OVERTIME_INCREMENT_MINUTES
                applicable_minutes = self.MIN_OVERTIME_MINUTES + (intervals * self.OVERTIME_INCREMENT_MINUTES)
                
                time_range = f"{expected_checkout.strftime('%H:%M')}~{checkout_time.strftime('%H:%M')}"
                calculation = f"預期下班: {expected_checkout.strftime('%H:%M')}, 實際下班: {checkout_time.strftime('%H:%M')}, 實際加班: {actual_overtime_minutes}分鐘, 可申請: {applicable_minutes}分鐘"
                
                return actual_overtime_minutes, applicable_minutes, time_range, calculation
        
        return 0, 0, "", ""
    
    def _is_full_day_absent(self, workday: WorkDay) -> bool:
        """檢查是否整天沒有打卡記錄"""
        # 如果沒有上班記錄或上班記錄沒有實際打卡時間，視為整天曠職
        if (not workday.checkin_record or 
            not workday.checkin_record.actual_time):
            return True
        
        # 如果沒有下班記錄或下班記錄沒有實際打卡時間，也視為曠職
        if (not workday.checkout_record or 
            not workday.checkout_record.actual_time):
            return True
            
        return False
    
    def generate_report(self) -> str:
        """生成報告（支援增量分析資訊顯示）"""
        report = []
        report.append("# 🎯 考勤分析報告 ✨\n")
        
        # 顯示增量分析資訊
        if self.incremental_mode and self.current_user:
            complete_days = self._identify_complete_work_days()
            unprocessed_dates = self._get_unprocessed_dates(self.current_user, complete_days)
            
            report.append("## 📈 增量分析資訊：\n")
            report.append(f"- 👤 使用者：{self.current_user}")
            report.append(f"- 📊 總完整工作日：{len(complete_days)} 天")
            report.append(f"- 🔄 新處理工作日：{len(unprocessed_dates)} 天")
            report.append(f"- ⏭️  跳過已處理：{len(complete_days) - len(unprocessed_dates)} 天")
            
            if unprocessed_dates:
                new_dates_str = ", ".join([d.strftime('%Y/%m/%d') for d in unprocessed_dates[:5]])
                if len(unprocessed_dates) > 5:
                    new_dates_str += f" 等 {len(unprocessed_dates)} 天"
                report.append(f"- 📅 新處理日期：{new_dates_str}")
            report.append("")
        
        # 忘刷卡建議
        forget_punch_issues = [issue for issue in self.issues if issue.type == IssueType.FORGET_PUNCH]
        if forget_punch_issues:
            report.append("## 🔄 建議使用忘刷卡的日期：\n")
            for i, issue in enumerate(forget_punch_issues, 1):
                report.append(f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - 🔄 {issue.description}")
                report.append(f"   ⏰ 時段: {issue.time_range}")
                report.append(f"   🧮 計算: {issue.calculation}")
                report.append("")
        
        # 遲到統計
        late_issues = [issue for issue in self.issues if issue.type == IssueType.LATE]
        if late_issues:
            report.append("## 😰 需要請遲到的日期：\n")
            for i, issue in enumerate(late_issues, 1):
                report.append(f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - 😅 {issue.description}")
                report.append(f"   ⏰ 時段: {issue.time_range}")
                report.append(f"   🧮 計算: {issue.calculation}")
                report.append("")
        
        # 加班統計
        overtime_issues = [issue for issue in self.issues if issue.type == IssueType.OVERTIME]
        if overtime_issues:
            report.append("## 💪 需要請加班的日期：\n")
            for i, issue in enumerate(overtime_issues, 1):
                report.append(f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - 🔥 {issue.description}")
                report.append(f"   ⏰ 時段: {issue.time_range}")
                report.append(f"   🧮 計算: {issue.calculation}")
                report.append("")
        
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
        report.append("## 📊 統計摘要：\n")
        report.append(f"- 🔄 建議忘刷卡天數：{len(forget_punch_issues)} 天")
        report.append(f"- 😰 需要請遲到天數：{len(late_issues)} 天")
        report.append(f"- 💪 加班天數：{len(overtime_issues)} 天")
        report.append(f"- 📝 需要請假天數：{len(weekday_leave_issues)} 天")
        report.append(f"- 🏠 建議WFH天數：{len(wfh_issues)} 天")
        
        return "\n".join(report)
    
    def export_csv(self, filepath: str) -> None:
        """匯出CSV格式報告"""
        import csv
        
        # 使用UTF-8-BOM編碼和分號分隔符以確保Mac Excel能正確顯示
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
            
            # 增量模式下添加狀態欄位
            if self.incremental_mode:
                headers.append('狀態')
            
            writer.writerow(headers)
            
            # 如果是增量模式且沒有問題，至少提供一行狀態資訊
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
                    if not unprocessed_dates:  # 沒有新資料需要處理
                        status_row = [
                            last_date,
                            "狀態資訊",
                            0,
                            f"📊 增量分析完成，已處理至 {last_date}，共 {len(complete_days)} 個完整工作日 | 上次分析時間: {last_analysis_time}",
                            "",
                            "上次處理範圍內無新問題需要申請",
                            "系統狀態"
                        ]
                        writer.writerow(status_row)
            
            # 寫入實際問題記錄
            for issue in self.issues:
                row = [
                    issue.date.strftime('%Y/%m/%d'),
                    issue.type.value,
                    issue.duration_minutes,
                    issue.description,
                    issue.time_range,
                    issue.calculation
                ]
                
                # 增量模式下添加狀態資訊
                if self.incremental_mode:
                    status = "[NEW] 本次新發現" if issue.is_new else "已存在"
                    row.append(status)
                
                writer.writerow(row)
    
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

    def _backup_existing_file(self, filepath: str) -> None:
        """備份現有檔案（如果存在），使用時間戳記作為後綴
        Args:
            filepath: 要檢查並備份的檔案路徑
        """
        import os
        from datetime import datetime
        
        if os.path.exists(filepath):
            # 產生時間戳記後綴 (格式: YYYYMMDD_HHMMSS)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 分離檔名和副檔名
            base_name, ext = os.path.splitext(filepath)
            backup_filepath = f"{base_name}_{timestamp}{ext}"
            
            # 備份檔案
            os.rename(filepath, backup_filepath)
            logger.info("📦 備份現有檔案: %s", os.path.basename(backup_filepath))
    
    def export_report(self, filepath: str, format_type: str = 'excel') -> None:
        """統一匯出介面
        Args:
            filepath: 檔案路徑
            format_type: 'excel' 或 'csv'
        """
        # 匯出前先備份現有檔案
        self._backup_existing_file(filepath)
        
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
        user_name, _, _ = analyzer_temp._extract_user_and_date_range_from_filename(filepath)
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

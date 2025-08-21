#!/usr/bin/env python3
"""
考勤分析系統
用於分析考勤記錄並計算遲到/加班時數
"""

import re
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


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


class AttendanceAnalyzer:
    """考勤分析器"""
    
    # 公司規則常數
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
    
    def __init__(self):
        self.records: List[AttendanceRecord] = []
        self.workdays: List[WorkDay] = []
        self.issues: List[Issue] = []
        self.holidays: set = set()  # 存放國定假日日期
        self.forget_punch_usage: Dict[str, int] = {}  # 追蹤每月忘刷卡使用次數 {年月: 次數}
        self.loaded_holiday_years: set = set()  # 追蹤已載入假日的年份
    
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
                print(f"警告: 無法解析國定假日日期: {holiday_str}")
    
    def _load_dynamic_holidays(self, year: int) -> None:
        """動態載入指定年份的國定假日
        Args:
            year: 要載入的年份
        """
        print(f"資訊: 動態載入 {year} 年國定假日...")
        
        # 方案1: 使用政府開放資料API
        success = self._try_load_from_gov_api(year)
        
        if not success:
            # 方案2: 使用基本假日規則（元旦、國慶日等固定日期）
            self._load_basic_holidays(year)
            print(f"警告: 無法取得 {year} 年完整假日資料，僅載入基本固定假日")
    
    def _try_load_from_gov_api(self, year: int) -> bool:
        """嘗試從政府開放資料API載入假日
        Args:
            year: 要載入的年份
        Returns:
            bool: 是否成功載入
        """
        try:
            import urllib.request
            import json
            
            # 政府資料開放平臺 - 政府行政機關辦公日曆表
            # 注意: 實際API可能需要調整URL格式
            url = f"https://data.gov.tw/api/v1/rest/datastore_search?resource_id=W2&filters={{\"date\":\"{year}\"}}"
            
            # 設定逾時以避免長時間等待
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # 解析API回應（需根據實際API格式調整）
                if 'result' in data and 'records' in data['result']:
                    for record in data['result']['records']:
                        if record.get('isHoliday', 0) == 1:  # 假設API用isHoliday標示假日
                            date_str = record.get('date', '')
                            if date_str:
                                holiday_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                                self.holidays.add(holiday_date)
                    return True
                    
        except Exception as e:
            print(f"無法從API載入 {year} 年假日資料: {e}")
            
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
                print(f"警告: 無法解析基本假日日期: {holiday_str}")
    
    def parse_attendance_file(self, filepath: str) -> None:
        """解析考勤資料檔案"""
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
            except Exception as e:
                print(f"警告: 第{line_num}行解析失敗: {e}")
    
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
        except:
            return None
    
    def group_records_by_day(self) -> None:
        """將記錄按日期分組"""
        # 在分組前，先載入出勤資料中涉及的年份假日
        years_in_data = self._get_years_from_records()
        if years_in_data:
            self._load_taiwan_holidays(years_in_data)
        
        daily_records = {}
        
        for record in self.records:
            if not record.date:
                continue
                
            if record.date not in daily_records:
                daily_records[record.date] = {'checkin': None, 'checkout': None}
            
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
        """分析考勤記錄"""
        self.issues = []
        
        for workday in self.workdays:
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
                    self.forget_punch_usage.get(month_key, 0) < self.FORGET_PUNCH_ALLOWANCE_PER_MONTH
                )
                
                if can_use_forget_punch:
                    # 使用忘刷卡
                    self.forget_punch_usage[month_key] = self.forget_punch_usage.get(month_key, 0) + 1
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
        """生成報告"""
        report = []
        report.append("# 🎯 考勤分析報告 ✨\n")
        
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
            writer.writerow(['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式'])
            
            for issue in self.issues:
                writer.writerow([
                    issue.date.strftime('%Y/%m/%d'),
                    issue.type.value,
                    issue.duration_minutes,
                    issue.description,
                    issue.time_range,
                    issue.calculation
                ])
    
    def export_excel(self, filepath: str) -> None:
        """匯出Excel格式報告"""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        except ImportError:
            print("⚠️  警告: 未安裝 openpyxl，回退使用CSV格式")
            print("💡 安裝指令: pip install openpyxl")
            # 回退到CSV格式
            csv_filepath = filepath.replace('.xlsx', '.csv')
            self.export_csv(csv_filepath)
            print(f"✅ CSV報告已匯出: {csv_filepath}")
            return
        
        # 建立工作簿
        wb = Workbook()
        ws = wb.active
        ws.title = "考勤分析"
        
        # 設定樣式
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        center_alignment = Alignment(horizontal='center', vertical='center')
        
        # 標題列
        headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center_alignment
            cell.border = border
        
        # 資料列
        for row, issue in enumerate(self.issues, 2):
            # 日期
            date_cell = ws.cell(row=row, column=1)
            date_cell.value = issue.date.strftime('%Y/%m/%d')
            date_cell.alignment = center_alignment
            date_cell.border = border
            
            # 類型（加上顏色標示）
            type_cell = ws.cell(row=row, column=2)
            type_cell.value = issue.type.value
            type_cell.alignment = center_alignment
            type_cell.border = border
            
            # 根據類型設定背景色
            if issue.type == IssueType.LATE:
                type_cell.fill = PatternFill(start_color="FFE6E6", end_color="FFE6E6", fill_type="solid")
            elif issue.type == IssueType.OVERTIME:
                type_cell.fill = PatternFill(start_color="E6F3FF", end_color="E6F3FF", fill_type="solid")
            elif issue.type == IssueType.WFH:
                type_cell.fill = PatternFill(start_color="E6FFE6", end_color="E6FFE6", fill_type="solid")
            elif issue.type == IssueType.FORGET_PUNCH:
                type_cell.fill = PatternFill(start_color="FFF0E6", end_color="FFF0E6", fill_type="solid")
            
            # 時長
            duration_cell = ws.cell(row=row, column=3)
            duration_cell.value = issue.duration_minutes
            duration_cell.alignment = center_alignment
            duration_cell.border = border
            
            # 說明
            desc_cell = ws.cell(row=row, column=4)
            desc_cell.value = issue.description
            desc_cell.border = border
            
            # 時段
            range_cell = ws.cell(row=row, column=5)
            range_cell.value = issue.time_range
            range_cell.alignment = center_alignment
            range_cell.border = border
            
            # 計算式
            calc_cell = ws.cell(row=row, column=6)
            calc_cell.value = issue.calculation
            calc_cell.border = border
        
        # 自動調整欄位寬度
        for col in range(1, 7):
            ws.column_dimensions[chr(64 + col)].width = 15
        
        # 說明欄位設定較寬
        ws.column_dimensions['D'].width = 30
        ws.column_dimensions['F'].width = 35
        
        # 儲存檔案
        wb.save(filepath)
    
    def export_report(self, filepath: str, format_type: str = 'excel') -> None:
        """統一匯出介面
        Args:
            filepath: 檔案路徑
            format_type: 'excel' 或 'csv'
        """
        if format_type.lower() == 'csv':
            self.export_csv(filepath)
        else:
            self.export_excel(filepath)


def main():
    """主程式"""
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("📖 使用方法: python attendance_analyzer.py <考勤檔案路徑> [格式]")
        print("   格式選項: excel (預設) | csv")
        print("   範例: python attendance_analyzer.py data.txt")
        print("   範例: python attendance_analyzer.py data.txt csv")
        sys.exit(1)
    
    filepath = sys.argv[1]
    format_type = sys.argv[2] if len(sys.argv) == 3 else 'excel'
    
    # 驗證格式參數
    if format_type.lower() not in ['excel', 'csv']:
        print("❌ 錯誤: 格式只能是 'excel' 或 'csv'")
        sys.exit(1)
    
    try:
        analyzer = AttendanceAnalyzer()
        print("📂 正在解析考勤檔案...")
        analyzer.parse_attendance_file(filepath)
        
        print("📝 正在分組記錄...")
        analyzer.group_records_by_day()
        
        print("🔍 正在分析考勤...")
        analyzer.analyze_attendance()
        
        print("📊 正在生成報告...")
        report = analyzer.generate_report()
        
        # 強制顯示完整報告，每行單獨輸出
        print("\n")
        for line in report.split('\n'):
            print(line, flush=True)
        
        # 根據指定格式匯出
        if format_type.lower() == 'csv':
            output_filepath = filepath.replace('.txt', '_analysis.csv')
            analyzer.export_csv(output_filepath)
            print(f"✅ CSV報告已匯出: {output_filepath}")
        else:
            output_filepath = filepath.replace('.txt', '_analysis.xlsx')
            analyzer.export_excel(output_filepath)
            print(f"✅ Excel報告已匯出: {output_filepath}")
        
        # 同時保留CSV格式（向後相容）
        if format_type.lower() == 'excel':
            csv_filepath = filepath.replace('.txt', '_analysis.csv')
            analyzer.export_csv(csv_filepath)
            print(f"📝 同時匯出CSV格式: {csv_filepath}")
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
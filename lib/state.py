import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Iterable


logger = logging.getLogger(__name__)


class AttendanceStateManager:
    """考勤狀態管理器 - 負責讀寫增量分析狀態"""

    def __init__(self, state_file: str = "attendance_state.json"):
        self.state_file = state_file
        self.state_data = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("無法讀取狀態檔案 %s: %s", self.state_file, e)
                logger.warning("將使用空白狀態")
        return {"users": {}}

    def save_state(self) -> None:
        try:
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("無法儲存狀態檔案 %s: %s", self.state_file, e)

    def get_user_processed_ranges(self, user_name: str) -> List[Dict]:
        if user_name not in self.state_data["users"]:
            return []
        return self.state_data["users"][user_name].get("processed_date_ranges", [])

    def get_forget_punch_usage(self, user_name: str, year_month: str) -> int:
        if user_name not in self.state_data["users"]:
            return 0
        return self.state_data["users"][user_name].get("forget_punch_usage", {}).get(year_month, 0)

    def update_user_state(self, user_name: str, new_range: Dict[str, str],
                          forget_punch_usage: Dict[str, int] = None) -> None:
        if user_name not in self.state_data["users"]:
            self.state_data["users"][user_name] = {
                "processed_date_ranges": [],
                "forget_punch_usage": {}
            }
        user_data = self.state_data["users"][user_name]
        existing_ranges = user_data["processed_date_ranges"]
        updated = False
        for i, existing_range in enumerate(existing_ranges):
            if existing_range["source_file"] == new_range["source_file"]:
                existing_ranges[i] = new_range
                updated = True
                break
        if not updated:
            existing_ranges.append(new_range)
        if forget_punch_usage:
            user_data["forget_punch_usage"].update(forget_punch_usage)

    def detect_date_overlap(self, user_name: str, new_start_date: str, new_end_date: str) -> List[Tuple[str, str]]:
        overlaps = []
        existing_ranges = self.get_user_processed_ranges(user_name)
        new_start = datetime.strptime(new_start_date, "%Y-%m-%d").date()
        new_end = datetime.strptime(new_end_date, "%Y-%m-%d").date()
        for range_info in existing_ranges:
            existing_start = datetime.strptime(range_info["start_date"], "%Y-%m-%d").date()
            existing_end = datetime.strptime(range_info["end_date"], "%Y-%m-%d").date()
            if new_start <= existing_end and new_end >= existing_start:
                overlap_start = max(new_start, existing_start)
                overlap_end = min(new_end, existing_end)
                overlaps.append((overlap_start.strftime("%Y-%m-%d"), overlap_end.strftime("%Y-%m-%d")))
        return overlaps


def filter_unprocessed_dates(processed_ranges: List[Dict[str, str]],
                             complete_days: Iterable[datetime]) -> List[datetime]:
    """Return dates in complete_days not covered by any processed range.

    processed_ranges: List of dicts with 'start_date'/'end_date' in YYYY-MM-DD.
    complete_days: Iterable of datetime (date at 00:00).
    Inclusive range check: start <= day <= end.
    """
    out: List[datetime] = []
    norm_ranges: List[Tuple[datetime, datetime]] = []
    for r in processed_ranges or []:
        try:
            s = datetime.strptime(r["start_date"], "%Y-%m-%d").date()
            e = datetime.strptime(r["end_date"], "%Y-%m-%d").date()
            norm_ranges.append((s, e))
        except Exception:
            # skip malformed range
            continue

    for day_dt in complete_days:
        day = day_dt.date()
        if any(s <= day <= e for s, e in norm_ranges):
            continue
        out.append(day_dt)
    return out

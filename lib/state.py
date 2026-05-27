import json
import logging
import os
from collections.abc import Iterable
from datetime import datetime

logger = logging.getLogger(__name__)


class AttendanceStateManager:
    """考勤狀態管理器 - 負責讀寫增量分析狀態"""

    def __init__(self, state_file: str = None, read_only: bool = False):
        # Allow override via env var so containers can persist state under a volume
        # Default path remains 'attendance_state.json' if no override provided
        if state_file is None:
            state_file = os.getenv("FHR_STATE_FILE", "attendance_state.json")
        self.state_file = state_file
        self.read_only = read_only
        if self.read_only:
            logger.debug("🛡️  狀態管理器以唯讀模式載入：%s", self.state_file)
        self.state_data = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("無法讀取狀態檔案 %s: %s", self.state_file, e)
                logger.warning("將使用空白狀態")
        return {"users": {}}

    def save_state(self) -> None:
        if self.read_only:
            logger.debug("🛡️  Debug/唯讀模式：略過狀態寫入 %s", self.state_file)
            return
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning("無法儲存狀態檔案 %s: %s", self.state_file, e)

    def get_user_processed_ranges(self, user_name: str) -> list[dict]:
        if user_name not in self.state_data["users"]:
            return []
        return self.state_data["users"][user_name].get("processed_date_ranges", [])

    def get_forget_punch_usage(self, user_name: str, year_month: str) -> int:
        if user_name not in self.state_data["users"]:
            return 0
        return self.state_data["users"][user_name].get("forget_punch_usage", {}).get(year_month, 0)

    def get_last_analysis_time(self, user_name: str) -> str:
        if user_name not in self.state_data.get("users", {}):
            return ""
        ranges = self.state_data["users"][user_name].get("processed_date_ranges", [])
        return max((r.get("last_analysis_time", "") for r in ranges), default="")

    def update_user_state(
        self, user_name: str, new_range: dict[str, str], forget_punch_usage: dict[str, int] = None
    ) -> None:
        if user_name not in self.state_data["users"]:
            self.state_data["users"][user_name] = {
                "processed_date_ranges": [],
                "forget_punch_usage": {},
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

    # ---------- applied_forms (Portal-mirrored dedup cache) ----------
    #
    # `applied_forms` is the Portal's truth, mirrored locally. Populated by
    # `fhr portal-sync` (queries eWorkFlow Search) and consumed by
    # `fhr portal-apply` to skip dates that already have a submitted form.
    #
    # Schema (per user):
    #   "applied_forms": {
    #     "overtime": [
    #       {"date": "YYYY/MM/DD", "start_time": "HHMM", "end_time": "HHMM",
    #        "hours": int, "location": "...", "reason": "...",
    #        "status": "已核准|...", "synced_at": "ISO8601"}
    #     ],
    #     "leave": [
    #       {"date", "start_time", "end_time", "hours", "leave_type",
    #        "reason", "status", "synced_at"}
    #     ],
    #     "last_full_sync": "ISO8601"
    #   }

    @staticmethod
    def _applied_form_key(entry: dict) -> tuple:
        return (entry.get("date", ""), entry.get("start_time", ""), entry.get("end_time", ""))

    def get_applied_forms(self, user_name: str, kind: str | None = None) -> dict | list:
        user = self.state_data["users"].get(user_name, {})
        applied = user.get("applied_forms", {})
        if kind is None:
            return applied
        return applied.get(kind, [])

    def replace_applied_forms(
        self, user_name: str, entries_by_kind: dict[str, list[dict]], synced_at: str
    ) -> None:
        """Replace the user's mirrored applied-form lists with fresh data.

        Each entry is augmented with `synced_at` if it isn't already set."""
        if user_name not in self.state_data["users"]:
            self.state_data["users"][user_name] = {
                "processed_date_ranges": [],
                "forget_punch_usage": {},
            }
        user = self.state_data["users"][user_name]
        applied = user.setdefault("applied_forms", {})
        for kind, entries in entries_by_kind.items():
            cleaned = []
            for e in entries:
                rec = dict(e)
                rec.setdefault("synced_at", synced_at)
                cleaned.append(rec)
            applied[kind] = cleaned
        applied["last_full_sync"] = synced_at

    def record_applied_form(self, user_name: str, kind: str, entry: dict, recorded_at: str) -> None:
        """Record a locally submitted form without changing last_full_sync."""
        if user_name not in self.state_data["users"]:
            self.state_data["users"][user_name] = {
                "processed_date_ranges": [],
                "forget_punch_usage": {},
            }
        user = self.state_data["users"][user_name]
        applied = user.setdefault("applied_forms", {})
        entries = applied.setdefault(kind, [])
        rec = dict(entry)
        rec.setdefault("synced_at", recorded_at)
        target = self._applied_form_key(rec)
        for idx, existing in enumerate(entries):
            if self._applied_form_key(existing) == target:
                entries[idx] = {**existing, **rec}
                return
        entries.append(rec)

    def is_form_already_applied(self, user_name: str, kind: str, candidate: dict) -> bool:
        """True if the candidate (date/start/end) is already submitted."""
        target = self._applied_form_key(candidate)
        for existing in self.get_applied_forms(user_name, kind):
            if self._applied_form_key(existing) == target:
                return True
        return False

    def last_full_sync(self, user_name: str) -> str:
        return (
            self.get_applied_forms(user_name).get("last_full_sync", "")
            if isinstance(self.get_applied_forms(user_name), dict)
            else ""
        )

    # ---------- legacy ----------

    def detect_date_overlap(
        self, user_name: str, new_start_date: str, new_end_date: str
    ) -> list[tuple[str, str]]:
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
                overlaps.append(
                    (overlap_start.strftime("%Y-%m-%d"), overlap_end.strftime("%Y-%m-%d"))
                )
        return overlaps


def filter_unprocessed_dates(
    processed_ranges: list[dict[str, str]], complete_days: Iterable[datetime]
) -> list[datetime]:
    """Return dates in complete_days not covered by any processed range.

    processed_ranges: List of dicts with 'start_date'/'end_date' in YYYY-MM-DD.
    complete_days: Iterable of datetime (date at 00:00).
    Inclusive range check: start <= day <= end.
    """
    out: list[datetime] = []
    norm_ranges: list[tuple[datetime, datetime]] = []
    for r in processed_ranges or []:
        try:
            s = datetime.strptime(r["start_date"], "%Y-%m-%d").date()
            e = datetime.strptime(r["end_date"], "%Y-%m-%d").date()
            norm_ranges.append((s, e))
        except Exception:
            # skip malformed range
            continue

    # Merge ranges for faster membership checks
    norm_ranges.sort(key=lambda t: t[0])
    merged: list[tuple[datetime, datetime]] = []
    for s, e in norm_ranges:
        if not merged or s > merged[-1][1]:
            merged.append((s, e))
        else:
            prev_s, prev_e = merged[-1]
            merged[-1] = (prev_s, max(prev_e, e))

    # Binary search membership over merged ranges
    import bisect

    starts = [s for s, _ in merged]
    for day_dt in complete_days:
        day = day_dt.date()
        i = bisect.bisect_right(starts, day) - 1
        if i >= 0 and merged[i][0] <= day <= merged[i][1]:
            continue
        out.append(day_dt)
    return out

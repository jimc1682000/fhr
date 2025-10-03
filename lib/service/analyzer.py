from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from attendance_analyzer import AttendanceAnalyzer, Issue
from lib.filename import parse_range_and_user
from lib.state import AttendanceStateManager

try:  # Optional helper; falls back to no-op if module absent
    from lib import recent as recent_files
except Exception:  # pragma: no cover - recent helper unavailable
    recent_files = None  # type: ignore


logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int | None, int | None], None]


class AnalysisError(Exception):
    """Generic exception raised when analysis fails."""


class ResetStateError(AnalysisError):
    """Raised when reset-state is requested but cannot be fulfilled."""


class AnalysisCancelled(AnalysisError):
    """Raised when a cancel event is triggered during analysis."""


@dataclass(slots=True)
class OutputRequest:
    path: str
    format: Literal["excel", "csv"] = "excel"
    backup: bool = True


@dataclass(slots=True)
class ExportedFile:
    requested_path: str
    actual_path: str
    requested_format: Literal["excel", "csv"]
    actual_format: Literal["excel", "csv"]

    @property
    def fallback_applied(self) -> bool:
        return self.requested_format == "excel" and self.actual_format == "csv"


@dataclass(slots=True)
class IncrementalStatus:
    last_date: str
    complete_days: int
    last_analysis_time: str


@dataclass(slots=True)
class IssuePreview:
    date: str
    type: str
    duration_minutes: int
    description: str
    time_range: str = ""
    calculation: str = ""
    status: str | None = None


@dataclass(slots=True)
class AnalysisOptions:
    source_path: str
    requested_format: Literal["excel", "csv"] = "excel"
    mode: Literal["incremental", "full"] = "incremental"
    reset_state: bool = False
    debug: bool = False
    output: OutputRequest | None = None
    extra_outputs: Sequence[OutputRequest] = field(default_factory=tuple)
    add_recent: bool = True
    preview_limit: int = 100

    def normalized_mode(self) -> Literal["incremental", "full"]:
        if self.mode not in ("incremental", "full"):
            raise AnalysisError(f"Unsupported mode: {self.mode}")
        return self.mode

    def normalized_format(self) -> Literal["excel", "csv"]:
        if self.requested_format not in ("excel", "csv"):
            raise AnalysisError(f"Unsupported format: {self.requested_format}")
        return self.requested_format


@dataclass(slots=True)
class AnalysisResult:
    requested_mode: Literal["incremental", "full"]
    effective_mode: Literal["incremental", "full"]
    requested_format: Literal["excel", "csv"]
    actual_format: Literal["excel", "csv"]
    user_name: str | None
    start_date: str | None
    end_date: str | None
    reset_applied: bool
    first_time_user: bool
    outputs: list[ExportedFile]
    issues: list[Issue]
    issues_preview: list[IssuePreview]
    report_text: str
    totals: dict[str, int]
    status: IncrementalStatus | None
    debug_mode: bool


class AnalyzerService:
    """High-level orchestrator that coordinates AttendanceAnalyzer runs."""

    _PROGRESS_STEPS = (
        ("parse", 1),
        ("group", 2),
        ("analyze", 3),
        ("export", 4),
    )

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"{__name__}.service")

    def run(
        self,
        options: AnalysisOptions,
        *,
        progress_cb: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> AnalysisResult:
        request_mode = options.normalized_mode()
        request_format = options.normalized_format()
        source_path = options.source_path
        if not os.path.exists(source_path):
            raise AnalysisError(f"Source file not found: {source_path}")

        user_name, start_date, end_date = parse_range_and_user(source_path)
        state_manager = AttendanceStateManager(read_only=options.debug)

        reset_applied = False
        if options.reset_state:
            if not user_name:
                raise ResetStateError("無法從檔名識別使用者，無法執行狀態重設")
            reset_applied = self._reset_user_state(state_manager, user_name, options.debug)

        first_time_user = bool(user_name) and not state_manager.get_user_processed_ranges(user_name)
        incremental = (request_mode == "incremental") or first_time_user
        effective_mode: Literal["incremental", "full"] = (
            "full" if request_mode == "full" or first_time_user else "incremental"
        )

        analyzer = AttendanceAnalyzer(debug=options.debug)
        analyzer.state_manager = state_manager

        outputs: list[ExportedFile] = []
        actual_primary_format = request_format
        report_text = ""
        issues: list[Issue] = []
        totals: dict[str, int] = {}
        status: IncrementalStatus | None = None
        issues_preview: list[IssuePreview] = []

        try:
            self._emit_progress(progress_cb, "parse", 1, cancel_event)
            analyzer.parse_attendance_file(source_path, incremental=incremental)
            self._check_cancel(cancel_event)

            self._emit_progress(progress_cb, "group", 2, cancel_event)
            analyzer.group_records_by_day()
            self._check_cancel(cancel_event)

            self._emit_progress(progress_cb, "analyze", 3, cancel_event)
            analyzer.analyze_attendance()
            self._check_cancel(cancel_event)

            export_requests: list[OutputRequest] = []
            if options.output:
                export_requests.append(options.output)
            export_requests.extend(list(options.extra_outputs))

            if export_requests:
                self._emit_progress(progress_cb, "export", 4, cancel_event)
                for req in export_requests:
                    exported = self._export(analyzer, req)
                    outputs.append(exported)
                if outputs:
                    actual_primary_format = outputs[0].actual_format
            else:
                self._emit_progress(progress_cb, "export", 4, cancel_event)

            report_text = analyzer.generate_report()
            issues = list(analyzer.issues)
            totals = self._totals(issues)
            status = self._status(analyzer)
            issues_preview = self._preview(issues, options.preview_limit, analyzer.incremental_mode)
        except AnalysisCancelled:
            raise
        except AnalysisError:
            raise
        except Exception as exc:  # pragma: no cover - rewrap unexpected errors
            raise AnalysisError(str(exc)) from exc

        if options.add_recent and recent_files is not None:
            try:
                recent_files.add_recent_file(source_path)
            except Exception:  # pragma: no cover - not critical
                logger.debug("Failed to record recent file", exc_info=True)

        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise AnalysisCancelled("Analysis cancelled after completion")

        return AnalysisResult(
            requested_mode=request_mode,
            effective_mode=effective_mode,
            requested_format=request_format,
            actual_format=actual_primary_format,
            user_name=user_name,
            start_date=start_date,
            end_date=end_date,
            reset_applied=reset_applied,
            first_time_user=first_time_user,
            outputs=outputs,
            issues=issues,
            issues_preview=issues_preview,
            report_text=report_text,
            totals=totals,
            status=status,
            debug_mode=options.debug,
        )

    def _export(self, analyzer: AttendanceAnalyzer, request: OutputRequest) -> ExportedFile:
        requested_path = request.path
        requested_format = request.format
        actual_path = requested_path
        actual_format = requested_format

        directory = os.path.dirname(requested_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        analyzer.export_report(requested_path, requested_format)

        if requested_format == "excel" and not os.path.exists(requested_path):
            fallback_csv = requested_path.replace(".xlsx", ".csv")
            if os.path.exists(fallback_csv):
                actual_path = fallback_csv
                actual_format = "csv"
            else:
                raise AnalysisError(
                    f"Excel export expected at {requested_path}, but no file was created"
                )

        return ExportedFile(
            requested_path=requested_path,
            actual_path=actual_path,
            requested_format=requested_format,
            actual_format=actual_format,
        )

    @staticmethod
    def _totals(issues: Iterable[Issue]) -> dict[str, int]:
        from collections import Counter

        counter = Counter(issue.type.value for issue in issues)
        total = sum(counter.values())
        return {
            "FORGET_PUNCH": counter.get("忘刷卡", 0),
            "LATE": counter.get("遲到", 0),
            "OVERTIME": counter.get("加班", 0),
            "WFH": counter.get("WFH假", 0),
            "WEEKDAY_LEAVE": counter.get("請假", 0),
            "TOTAL": total,
        }

    @staticmethod
    def _status(analyzer: AttendanceAnalyzer) -> IncrementalStatus | None:
        status_tuple = analyzer._compute_incremental_status_row()
        if not status_tuple:
            return None
        last_date, complete_days, last_time = status_tuple
        return IncrementalStatus(
            last_date=last_date,
            complete_days=complete_days,
            last_analysis_time=last_time,
        )

    @staticmethod
    def _preview(
        issues: list[Issue], limit: int, incremental_mode: bool
    ) -> list[IssuePreview]:
        preview: list[IssuePreview] = []
        for issue in issues[: max(limit, 0)]:
            status = None
            if incremental_mode:
                status = "[NEW] 本次新發現" if getattr(issue, "is_new", False) else "已存在"
            preview.append(
                IssuePreview(
                    date=issue.date.strftime("%Y/%m/%d"),
                    type=issue.type.value,
                    duration_minutes=issue.duration_minutes,
                    description=issue.description,
                    time_range=getattr(issue, "time_range", ""),
                    calculation=getattr(issue, "calculation", ""),
                    status=status,
                )
            )
        return preview

    @staticmethod
    def _reset_user_state(
        state_manager: AttendanceStateManager, user_name: str, debug_mode: bool
    ) -> bool:
        users = state_manager.state_data.get("users", {})
        if user_name not in users:
            logger.info("ℹ️  使用者 %s 沒有現有狀態需要清除", user_name)
            return False
        if debug_mode:
            logger.debug("🛡️  Debug 模式：略過清除使用者 %s 的狀態", user_name)
            return False
        del users[user_name]
        state_manager.save_state()
        logger.info(
            "🗑️  狀態檔 '%s' 已清除使用者 %s 的記錄 @ %s",
            os.path.basename(state_manager.state_file),
            user_name,
            datetime.now().isoformat(),
        )
        return True

    @staticmethod
    def _emit_progress(
        cb: ProgressCallback | None,
        stage: str,
        index: int,
        cancel_event: threading.Event | None,
    ) -> None:
        if cb:
            try:
                cb(stage, index, len(AnalyzerService._PROGRESS_STEPS))
            except Exception:  # pragma: no cover - progress callback failures ignored
                logger.debug("Progress callback failed", exc_info=True)
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise AnalysisCancelled(f"Analysis cancelled during {stage}")

    @staticmethod
    def _check_cancel(cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise AnalysisCancelled("Analysis cancelled")

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from attendance_analyzer import AttendanceAnalyzer, IssueType, logger as analyzer_logger
from lib.filename import parse_range_and_user
from lib.state import AttendanceStateManager

APP_ROOT = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(APP_ROOT, "build", "uploads")
OUTPUT_ROOT = os.path.join(APP_ROOT, "build", "api-outputs")
WEB_DIR = os.path.join(APP_ROOT, "web")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_ROOT, exist_ok=True)


class IssueDTO(BaseModel):
    date: str
    type: str
    duration_minutes: int
    description: str
    time_range: str = ""
    calculation: str = ""
    status: str | None = None


class StatusDTO(BaseModel):
    last_date: str
    complete_days: int
    last_analysis_time: str


class AnalyzeResponse(BaseModel):
    analysis_id: str
    user: str | None = None
    # Effective mode actually used for analysis
    mode: Literal["incremental", "full"]
    requested_mode: Literal["incremental", "full"]
    requested_format: Literal["csv", "excel"]
    actual_format: Literal["csv", "excel"]
    source_filename: str
    reset_requested: bool = False
    reset_applied: bool = False
    first_time_user: bool = False
    output_filename: str
    download_url: str
    status: StatusDTO | None = None
    issues_preview: list[IssueDTO] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)
    debug_mode: bool = False


def _save_upload(upload: UploadFile, session_dir: str) -> str:
    base_name = os.path.basename(upload.filename or f"upload_{uuid.uuid4().hex}.txt")
    # sanitize to avoid path traversal
    base_name = base_name.replace("/", "_").replace("\\", "_")
    upload_path = os.path.join(session_dir, base_name)
    with open(upload_path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return upload_path


def _issues_to_dtos(analyzer: AttendanceAnalyzer, limit: int = 50) -> list[IssueDTO]:
    items: list[IssueDTO] = []
    for issue in analyzer.issues[:limit]:
        items.append(
            IssueDTO(
                date=issue.date.strftime("%Y/%m/%d"),
                type=issue.type.value,
                duration_minutes=issue.duration_minutes,
                description=issue.description,
                time_range=getattr(issue, "time_range", ""),
                calculation=getattr(issue, "calculation", ""),
                status=("[NEW] 本次新發現" if getattr(issue, "is_new", False) else "已存在")
                if analyzer.incremental_mode
                else None,
            )
        )
    return items


def _totals(analyzer: AttendanceAnalyzer) -> dict:
    from collections import Counter
    c = Counter([i.type.value for i in analyzer.issues])
    return {
        "FORGET_PUNCH": c.get(IssueType.FORGET_PUNCH.value, 0),
        "LATE": c.get(IssueType.LATE.value, 0),
        "OVERTIME": c.get(IssueType.OVERTIME.value, 0),
        "WFH": c.get(IssueType.WFH.value, 0),
        "WEEKDAY_LEAVE": c.get(IssueType.WEEKDAY_LEAVE.value, 0),
        "TOTAL": len(analyzer.issues),
    }


logger = logging.getLogger("fhr.service")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


GLOBAL_DEBUG_MODE = _env_flag("FHR_DEBUG", False)
if GLOBAL_DEBUG_MODE:
    logger.setLevel(logging.DEBUG)
    analyzer_logger.setLevel(logging.DEBUG)
    logger.debug("🐞 FHR Debug 模式啟用：服務將跳過狀態寫入並輸出詳細日誌。")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Starting fhr service...")
    try:
        yield
    except (asyncio.CancelledError, KeyboardInterrupt):
        # Swallow noisy tracebacks on double Ctrl-C and log a friendly message
        logger.info("Shutdown interrupted by signal; exiting gracefully.")
    finally:
        logger.info("fhr service stopped.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="fhr Service",
        version="0.1.0",
        description="Attendance analyzer web service",
        lifespan=_lifespan
    )

    # Allow local dev tools by default
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Ensure state file persists inside build/ volume unless explicitly overridden
    os.environ.setdefault(
        "FHR_STATE_FILE", os.path.join(APP_ROOT, "build", "attendance_state.json")
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "time": datetime.now().isoformat()}

    @app.post("/api/analyze", response_model=AnalyzeResponse)
    async def analyze(
        file: UploadFile,
        mode: Literal["incremental", "full"] = Form("full"),
        output: Literal["csv", "excel"] = Form("excel"),
        reset_state: bool = Form(False),
        debug: bool = Form(False),
    ):
        # Contain network backoff for holiday API when network is restricted
        os.environ.setdefault("HOLIDAY_API_MAX_RETRIES", "0")
        os.environ.setdefault("HOLIDAY_API_BACKOFF_BASE", "0.1")

        debug_mode = GLOBAL_DEBUG_MODE or debug
        prev_logger_level = logger.level
        prev_analyzer_level = analyzer_logger.level
        if debug_mode and not GLOBAL_DEBUG_MODE:
            logger.setLevel(logging.DEBUG)
            analyzer_logger.setLevel(logging.DEBUG)
            logger.debug("🐞 FHR Debug 模式（請求層級）啟用：服務將跳過狀態寫入並輸出詳細日誌。")

        session_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8]
        session_dir = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_dir, exist_ok=True)
        upload_path = _save_upload(file, session_dir)

        try:
            # Optional reset of user state and detect first-time user
            user_name, _, _ = parse_range_and_user(upload_path)
            reset_applied = False
            sm = AttendanceStateManager(read_only=debug_mode)
            if reset_state and user_name:
                if debug_mode:
                    logger.debug("🛡️  Debug 模式：略過清除使用者 %s 的狀態", user_name)
                elif user_name in sm.state_data.get("users", {}):
                    del sm.state_data["users"][user_name]
                    sm.save_state()
                    reset_applied = True

            # Determine if first-time user (post-reset state)
            first_time_user = False
            if user_name:
                ranges = sm.get_user_processed_ranges(user_name)
                first_time_user = (not ranges)

            requested_mode = mode
            # If first-time user is recognized, we still run analyzer in incremental mode
            # to persist state (ranges empty -> analyze all days),
            # but expose effective mode as 'full' in the response.
            incremental = (mode == "incremental") or first_time_user
            analyzer = AttendanceAnalyzer(debug=debug_mode)
            analyzer.parse_attendance_file(upload_path, incremental=incremental)
            analyzer.group_records_by_day()
            analyzer.analyze_attendance()

            # Prepare output placement
            out_session = os.path.join(OUTPUT_ROOT, session_id)
            os.makedirs(out_session, exist_ok=True)
            base = os.path.basename(upload_path)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            stem = base[:-4] if base.lower().endswith('.txt') else base
            if output == "csv":
                out_path = os.path.join(out_session, f"{stem}_analysis_{ts}.csv")
                analyzer.export_report(out_path, "csv")
                actual_format: Literal["csv", "excel"] = "csv"
            else:
                out_path = os.path.join(out_session, f"{stem}_analysis_{ts}.xlsx")
                analyzer.export_report(out_path, "excel")
                # If Excel export fell back to CSV (when openpyxl unavailable)
                if not os.path.exists(out_path):
                    csv_fallback = out_path.replace(".xlsx", ".csv")
                    if os.path.exists(csv_fallback):
                        out_path = csv_fallback
                        actual_format = "csv"
                    else:
                        raise HTTPException(
                            status_code=500,
                            detail="Failed to generate output file"
                        )
                else:
                    actual_format = "excel"

            # Build preview/status
            status_info = None
            status_tuple = analyzer._compute_incremental_status_row()
            if incremental and not analyzer.issues and status_tuple:
                last_date, complete_days, last_time = status_tuple
                status_info = StatusDTO(
                    last_date=last_date, complete_days=complete_days, last_analysis_time=last_time
                )

            download_rel = os.path.relpath(out_path, APP_ROOT)
            download_url = f"/api/download/{session_id}/{os.path.basename(out_path)}"

            return AnalyzeResponse(
                analysis_id=session_id,
                user=user_name,
                mode=("full" if first_time_user or requested_mode == "full" else "incremental"),
                requested_mode=requested_mode,
                requested_format=output,
                actual_format=actual_format,
                source_filename=os.path.basename(file.filename or base),
                reset_requested=bool(reset_state),
                reset_applied=reset_applied,
                first_time_user=first_time_user,
                output_filename=download_rel,
                download_url=download_url,
                status=status_info,
                issues_preview=_issues_to_dtos(analyzer, limit=100),
                totals=_totals(analyzer),
                debug_mode=debug_mode,
            )
        finally:
            if debug_mode and not GLOBAL_DEBUG_MODE:
                logger.setLevel(prev_logger_level)
                analyzer_logger.setLevel(prev_analyzer_level)

    @app.get("/api/download/{session_id}/{filename}")
    def download(session_id: str, filename: str):
        # Validate both session_id and filename to prevent path traversal
        if "/" in session_id or ".." in session_id or "/" in filename or ".." in filename:
            raise HTTPException(status_code=400, detail="Invalid session_id or filename")
        
        # Use Path.resolve() to ensure the final path is within OUTPUT_ROOT
        file_path = Path(OUTPUT_ROOT) / session_id / filename
        resolved_path = file_path.resolve()
        output_root_resolved = Path(OUTPUT_ROOT).resolve()
        
        # Check that the resolved path is within OUTPUT_ROOT
        if not str(resolved_path).startswith(str(output_root_resolved)):
            raise HTTPException(status_code=400, detail="Access denied")
        
        if not resolved_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(str(resolved_path), filename=filename)

    # Serve static frontend (registered last so /api takes precedence)
    if os.path.isdir(WEB_DIR):
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")

    return app


app = create_app()

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

from attendance_analyzer import logger as analyzer_logger
from lib.service import (
    AnalysisError,
    AnalysisOptions,
    AnalyzerService,
    OutputRequest,
    ResetStateError,
)

APP_ROOT = os.path.dirname(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(APP_ROOT, "build", "uploads")
OUTPUT_ROOT = os.path.join(APP_ROOT, "build", "api-outputs")
WEB_DIR = os.path.join(APP_ROOT, "web")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_ROOT, exist_ok=True)

SERVICE = AnalyzerService()


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


def _issues_to_dtos(issues: list, limit: int = 50) -> list[IssueDTO]:
    items: list[IssueDTO] = []
    for preview in issues[:limit]:
        items.append(
            IssueDTO(
                date=preview.date,
                type=preview.type,
                duration_minutes=preview.duration_minutes,
                description=preview.description,
                time_range=preview.time_range,
                calculation=preview.calculation,
                status=preview.status,
            )
        )
    return items


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
            requested_mode = mode
            out_session = os.path.join(OUTPUT_ROOT, session_id)
            os.makedirs(out_session, exist_ok=True)
            base = os.path.basename(upload_path)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            stem = base[:-4] if base.lower().endswith('.txt') else base
            primary_ext = '.csv' if output == 'csv' else '.xlsx'
            primary_output_path = os.path.join(
                out_session, f"{stem}_analysis_{ts}{primary_ext}"
            )

            options = AnalysisOptions(
                source_path=upload_path,
                requested_format=output,
                mode=requested_mode,
                reset_state=bool(reset_state),
                debug=debug_mode,
                output=OutputRequest(path=primary_output_path, format=output),
                extra_outputs=tuple(),
                add_recent=False,
            )

            result = SERVICE.run(options)

            if not result.outputs:
                raise HTTPException(status_code=500, detail="Failed to generate output file")

            primary_output = result.outputs[0]
            download_path = primary_output.actual_path
            download_rel = os.path.relpath(download_path, APP_ROOT)
            download_url = f"/api/download/{session_id}/{os.path.basename(download_path)}"

            status_info = None
            if result.status and result.effective_mode == "incremental" and not result.issues:
                status = result.status
                status_info = StatusDTO(
                    last_date=status.last_date,
                    complete_days=status.complete_days,
                    last_analysis_time=status.last_analysis_time,
                )

            return AnalyzeResponse(
                analysis_id=session_id,
                user=result.user_name,
                mode=result.effective_mode,
                requested_mode=requested_mode,
                requested_format=output,
                actual_format=primary_output.actual_format,
                source_filename=os.path.basename(file.filename or base),
                reset_requested=bool(reset_state),
                reset_applied=result.reset_applied,
                first_time_user=result.first_time_user,
                output_filename=download_rel,
                download_url=download_url,
                status=status_info,
                issues_preview=_issues_to_dtos(result.issues_preview, limit=100),
                totals=result.totals,
                debug_mode=debug_mode,
            )
        except ResetStateError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AnalysisError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
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

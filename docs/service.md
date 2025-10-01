fhr Service (Backend + Frontend)

Overview
- FastAPI backend exposing analysis endpoints with auto-generated OpenAPI docs.
- Static web UI (vanilla + i18next) to upload TXT, choose mode/output, toggle reset/debug options, preview result, and download.
- Reuses existing analyzer logic without renaming core files.

Run
- Install: `pip install fastapi uvicorn pydantic python-multipart` (optional: `openpyxl` for Excel)
- Start: `uvicorn server.main:app --reload`
- Open: http://localhost:8000/
- API docs: http://localhost:8000/docs (OpenAPI) · http://localhost:8000/openapi.json

Docker
- Build: `docker build -t fhr:latest .`
- Run: `docker run --rm -p 8000:8000 -v "$PWD/build:/app/build" fhr:latest`
  - Persists uploads/outputs to local `build/`
  - Open http://localhost:8000/ (UI) · http://localhost:8000/docs (API docs)

Persistence
- The incremental state file defaults to `/app/build/attendance_state.json` in Docker (env `FHR_STATE_FILE`).
- Mount `-v "$PWD/build:/app/build"` to persist user state across restarts.

Compose
- Quick start with Docker Compose:
  ```bash
  docker compose up --build -d
  # Stop: docker compose down
  ```
- Compose uses `./build` as a mounted volume for outputs and `attendance_state.json`.

Dev Lint/Test Hooks
- Optional developer tools: `pip install -r requirements-dev.txt`
- Install git hooks to lint (black/ruff) and run tests before commit:
  ```bash
  make install-hooks
  # Skip tests temporarily: SKIP_TESTS=1 git commit -m "..."
  ```

API
- POST `/api/analyze` (multipart/form-data)
  - file: TXT upload
  - mode: `incremental|full` (default `full`)
  - output: `csv|excel` (default `excel`)
  - reset_state: `true|false` (default `false`)
  - debug: `true|false` (default `false`, read-only with verbose logs)
  - 200 OK → JSON body:
    - analysis_id, user, mode (effective), requested_mode, requested_format, actual_format
    - source_filename, reset_requested (bool), reset_applied (bool)
    - first_time_user (bool)
    - debug_mode (bool)
    - output_filename (relative path), download_url
    - status: { last_date, complete_days, last_analysis_time } | null
    - issues_preview: first 100 items with fields {date, type, duration_minutes, description, time_range, calculation, status?}
    - totals: counts per category
- GET `/api/download/{analysis_id}/{filename}` → file download
- GET `/api/health` → uptime ping

Notes
- If `openpyxl` is missing and `output=excel`, the backend falls back to CSV and returns `actual_format = csv`.
- Holiday API retries are minimized in service mode via `HOLIDAY_API_MAX_RETRIES=0` to keep requests fast when network is restricted.
- Uploaded files and outputs are placed under `build/uploads/` and `build/api-outputs/`.
- Download filenames include a UTC timestamp suffix (e.g., `_analysis_YYYYMMDD_HHMMSS.ext`) to avoid overwriting repeated downloads.

Example (curl)
```bash
curl -F "file=@sample-attendance-data.txt" \
     -F mode=incremental -F output=csv -F reset_state=false \
     -F debug=false \
     http://localhost:8000/api/analyze | jq
```

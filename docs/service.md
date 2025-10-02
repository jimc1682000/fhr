fhr Service (Backend + Frontend)

Overview
- FastAPI backend exposing analysis endpoints with auto-generated OpenAPI docs.
- 靜態 Web UI（vanilla + i18next）支援上傳 TXT、切換模式/輸出、重置/除錯開關，並在勾選「分析後清理備份」時彈出預覽 Modal，列出將刪除的時間戳備份/主檔案後再確認。
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
  - export_policy: `merge|archive`（default `merge`）
  - cleanup_exports: `true|false`（default `false`，啟用時需附上預覽 token）
  - cleanup_token: 哈希字串（僅在 `cleanup_exports=true` 時必填）
  - cleanup_snapshot: JSON（`cleanup_preview` 回傳的 snapshot，僅在 `cleanup_exports=true` 時必填）
  - 200 OK → JSON body:
    - analysis_id, user, mode (effective), requested_mode, requested_format, actual_format
    - source_filename, reset_requested (bool), reset_applied (bool)
    - first_time_user (bool)
    - debug_mode (bool)
    - output_filename (relative path), download_url
    - status: { last_date, complete_days, last_analysis_time } | null
    - issues_preview: first 100 items with fields {date, type, duration_minutes, description, time_range, calculation, status?}
    - totals: counts per category
     - cleanup: { status: `performed|skipped|stale`, deleted: [...], preview?: {...} }
- 409 → 預覽失效或狀態變動（response.detail.preview 提供最新清單，需要重新確認）
- POST `/api/exports/cleanup-preview`
  - JSON body: { filename, output, debug, export_policy }
  - 200 OK → { items: [{name, kind, size, mtime, delete}], token, snapshot }
  - snapshot + token 需回傳給 `/api/analyze` 才會執行清理
- GET `/api/download/{analysis_id}/{filename}` → file download
- GET `/api/health` → uptime ping

Web UI Flow
- 勾選「分析後清理備份」後，需先點選「預覽要刪除的檔案」開啟 Modal，確認備份清單與除錯模式下的主檔案。
- Modal 按下「確認清理並分析」才會夾帶 `cleanup_token` + `cleanup_snapshot` 送出 `/api/analyze`；取消則保留原檔、需重新預覽。
- 若預覽與實際狀態不符（例：期間新增備份），後端會回傳最新清單並要求再次確認。

Notes
- If `openpyxl` is missing and `output=excel`, the backend falls back to CSV and returns `actual_format = csv`.
- Holiday API retries are minimized in service mode via `HOLIDAY_API_MAX_RETRIES=0` to keep requests fast when network is restricted.
- Uploaded files and outputs are placed under `build/uploads/` and `build/api-outputs/`.
- Download 欄位仍提供每次分析的唯一路徑；同時在 canonical 目錄保留（或覆寫）`<stem>_analysis.(csv|xlsx)` 以支援 CLI/服務共用清理流程。

Example (curl)
```bash
curl -F "file=@sample-attendance-data.txt" \
     -F mode=incremental -F output=csv -F reset_state=false \
     -F debug=false \
     http://localhost:8000/api/analyze | jq
```

# Repository Guidelines

This guide sets expectations for contributing to fhr, a small Python attendance analyzer with Taiwan holiday support. Keep changes focused, tested, and consistent with the current single‑file design. The content below preserves the original structure with targeted updates to reflect recent capabilities.

## Project Structure & Module Organization
- `attendance_analyzer.py` — main CLI and core logic (parsing, analysis, export).
- `lib/excel_exporter.py` — Excel helpers (headers, styles, widths, status row).
- `test/` — unittest suite (multiple `test_*.py` files, e.g. parsing/logic/exports/holiday resilience).
- `sample-attendance-data.txt` — example input.
- Generated (ignored): `*_analysis.(xlsx|csv)`, timestamped backups, `attendance_state.json`.
- `server/` — FastAPI 後端服務（REST API、靜態檔掛載）。
- `web/` — 前端靜態頁面（vanilla + i18next）。
- `docs/` — 完整文檔系統（23個文件，分層架構：使用者→運維→開發者→企業級）。
- `todos/` — 改進項目管理（立即可執行任務 + 需要開發支援的功能）。
- `Dockerfile`、`docker-compose.yml` — 服務容器化與佈署。
- `requirements-service.txt` — 後端服務相依。
- `requirements-dev.txt` — 開發工具（black/ruff/pre-commit）。
- `pyproject.toml` — black/ruff 設定。
- `.pre-commit-config.yaml` — pre-commit 框架配置。

## Build, Test, and Development Commands
- Run analysis: `python attendance_analyzer.py "202508-姓名-出勤資料.txt" [excel|csv] [--incremental|--full|--reset-state]`.
- Quick local check: `python attendance_analyzer.py sample-attendance-data.txt csv`.
- Run tests (full): `python3 -m unittest -q`.
- Run specific test: `python3 -m unittest -q test.test_holiday_api_resilience`.
- Optional Excel support: `pip install openpyxl`.
 - Lint (ruff，如未安裝則跑 fallback)：`make lint`。
 - 開發工具與 pre-commit 框架設置：
   - `pip install -r requirements-dev.txt`（包含 pre-commit）
   - `make install-hooks`（自動安裝 pre-commit hooks）
   - `make pre-commit-run`（手動運行所有 hooks）
 - 啟動 Web 服務：`uvicorn server.main:app --reload`（或 `docker compose up --build -d`）。

## Coding Style & Naming Conventions
- Python 3.6+; follow PEP 8 (4‑space indentation, 100‑char soft wrap).
- Names: functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Prefer standard library; add deps only when necessary and documented.
- Use `logging` (logger.info/warning/error) for user‑visible messages; avoid `print`.
- Keep CLI flags backward compatible; update `README.md` if modified.

## Testing Guidelines
- Framework: `unittest`. Place tests under `test/` using `test_*.py`.
- Cover parsing, business rules (late/OT/WFH), exports (Excel/CSV), and state handling.
- Include edge cases for date ranges and Friday/holiday WFH logic.
- For holiday API logic: mock `urllib.request.urlopen`; do not perform real network calls.
- Prefer fast, deterministic tests; if covering backoff, set env vars to disable delays.

## CI
- GitHub Actions `ci.yml` 在 PR 上會執行：
  - 依 `requirements-dev.txt` 安裝開發相依
  - Ruff 檢查（lint）與 Black `--check`（格式）
  - 單元測試 + 以 stdlib trace 產生覆蓋率報告
  - 強制覆蓋率達 ≥90%

## Commit & Pull Request Guidelines
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` (bilingual messages OK).
- Commits should be small and purposeful; reference issues (e.g., `Fixes #12`).
- PRs include: summary, rationale, screenshots or sample output when UI/format changes, and test notes.
- Avoid force‑pushing branches with open PRs; if history cleanup is needed, open a new `-v2` branch and mark the PR as “supersedes”.
- For stacked PRs, set the correct base branch and keep diffs minimal and well‑scoped.

## Security & Configuration Tips
- Do NOT commit real attendance data or `attendance_state.json`; these are already in `.gitignore`.
- Exports and backups are user data; treat as local artifacts only.
- If adding network calls (e.g., holidays), provide graceful fallbacks and timeouts; use absolute dates in logs.
- Holiday API resilience: exponential backoff and fallback are supported via env vars:
  - `HOLIDAY_API_MAX_RETRIES` (default 3)
  - `HOLIDAY_API_BACKOFF_BASE` (default 0.5s)
  - `HOLIDAY_API_MAX_BACKOFF` (default 8s)
 - Server state 檔案位置可用 `FHR_STATE_FILE` 覆寫；Docker 預設寫入 `/app/build/attendance_state.json`，請掛載 `./build` 以保留狀態。

## Agent‑Specific Notes
- Keep file paths stable; avoid renaming `attendance_analyzer.py` or `lib/excel_exporter.py` without updating tests and docs.
- When changing CLI behavior or output schema (e.g., status column, last_analysis_time), update `README.md` and add tests.
- For holiday behavior changes, use existing `_try_load_from_gov_api` and fallback hooks; update docs and add tests for new scenarios.
- Excel export: maintain widths (F=40, G=24 when incremental), headers, and status row semantics; keep tests aligned.
- 新增 Web/Service 功能時，保持 `server/main.py` 與 `web/` 路徑穩定；若更動 API，務必更新 `docs/service.md` 與前端。

## Documentation & Task Management

### docs/ Directory Usage
- **Navigation**: Start with `docs/index.md` for the complete documentation map
- **Tiered Structure**: User docs → Operational docs → Developer docs → Enterprise docs
- **Updates**: When adding features, update relevant docs AND `docs/index.md` navigation
- **Cross-references**: Maintain links between related documentation files

### todos/ Directory Usage
- **Immediate Tasks**: Check `todos/immediate-documentation-tasks.md` for 2-3 hour tasks
- **Development Items**: See `todos/api-architecture-enhancements.md` for features requiring code changes
- **Planning**: Use `todos/documentation-enhancement-roadmap.md` for long-term roadmap
- **Adding Items**: Only add actionable items with clear deliverables, avoid long-term speculation
- **Maintenance**: Remove completed items and update status regularly

### Documentation Workflow
1. **Before Major Changes**: Check `todos/` for related improvement items
2. **After Implementation**: Update both implementation docs and navigation in `docs/index.md`
3. **Feature Additions**: Add corresponding documentation tasks to `todos/` if documentation requires separate work
4. **Testing**: Ensure documentation examples work as described in tests

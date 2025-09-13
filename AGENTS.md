# Repository Guidelines

This guide sets expectations for contributing to fhr, a small Python attendance analyzer with Taiwan holiday support. Keep changes focused, tested, and consistent with the current single‑file design. The content below preserves the original structure with targeted updates to reflect recent capabilities.

## Project Structure & Module Organization
- `attendance_analyzer.py` — main CLI and core logic (parsing, analysis, export).
- `lib/excel_exporter.py` — Excel helpers (headers, styles, widths, status row).
- `test/` — unittest suite (multiple `test_*.py` files, e.g. parsing/logic/exports/holiday resilience).
- `sample-attendance-data.txt` — example input.
- Generated (ignored): `*_analysis.(xlsx|csv)`, timestamped backups, `attendance_state.json`.

## Build, Test, and Development Commands
- Run analysis: `python attendance_analyzer.py "202508-姓名-出勤資料.txt" [excel|csv] [--incremental|--full|--reset-state]`.
- Quick local check: `python attendance_analyzer.py sample-attendance-data.txt csv`.
- Run tests (full): `python3 -m unittest -q`.
- Run specific test: `python3 -m unittest -q test.test_holiday_api_resilience`.
- Optional Excel support: `pip install openpyxl`.
- Lint/format: `black .` and `ruff check --select E9,F63,F7,F82 .` (CI enforces both).

## Coding Style & Naming Conventions
- Python 3.8+; follow PEP 8 (4‑space indentation, 100‑char soft wrap).
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

## Agent‑Specific Notes
- Keep file paths stable; avoid renaming `attendance_analyzer.py` or `lib/excel_exporter.py` without updating tests and docs.
- When changing CLI behavior or output schema (e.g., status column, last_analysis_time), update `README.md` and add tests.
- For holiday behavior changes, use existing `_try_load_from_gov_api` and fallback hooks; update docs and add tests for new scenarios.
- Excel export: maintain widths (F=40, G=24 when incremental), headers, and status row semantics; keep tests aligned.
- Formatting policy: repository uses Black (default). Please format before committing to avoid CI failures.
- TUI is optional; import Textual only under `--tui`. Provide a friendly message if not installed. i18n via `FHR_LANG`.

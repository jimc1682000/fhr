# Repository Guidelines

This guide sets expectations for contributing to fhr, a small Python attendance analyzer with Taiwan holiday support. Keep changes focused, tested, and consistent with the current single-file design.

## Project Structure & Module Organization
- `attendance_analyzer.py` — main CLI and core logic (parsing, analysis, export).
- `test/` — test suite directory (contains `test_attendance_analyzer.py`).
- `sample-attendance-data.txt` — example input.
- Generated (ignored): `*_analysis.(xlsx|csv)`, timestamped backups, `attendance_state.json`.

## Build, Test, and Development Commands
- Run analysis: `python attendance_analyzer.py "202508-姓名-出勤資料.txt" [excel|csv] [--incremental|--full|--reset-state]`.
- Run tests: `python3 -m unittest test.test_attendance_analyzer` (uses `unittest`).
- Optional Excel support: `pip install openpyxl`.
- Quick local check: `python attendance_analyzer.py sample-attendance-data.txt csv`.

## Coding Style & Naming Conventions
- Python 3.6+; follow PEP 8 (4‑space indentation, 100‑char soft wrap).
- Names: functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Keep CLI flags backward compatible; update `README.md` if modified.
- Prefer standard library; add deps only when necessary and documented.

## Testing Guidelines
- Framework: `unittest`. Place new tests in the `test/` directory using `test_*.py` files.
- Name tests `test_*` and cover: parsing, business rules (late/OT/WFH), exports, and state handling.
- Run full suite before PRs; include edge cases for date ranges and Friday/WFH logic.

## Commit & Pull Request Guidelines
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` (bilingual messages OK).
- Commits should be small and purposeful; reference issues (e.g., `#12`).
- PRs must include: summary, rationale, screenshots or sample output when UI/format changes, and test notes.

## Security & Configuration Tips
- Do NOT commit real attendance data or `attendance_state.json`; these are already in `.gitignore`.
- Exports and backups are user data; treat as local artifacts only.
- If adding network calls (e.g., holidays), provide graceful fallbacks and timeouts.

## Agent‑Specific Notes
- Keep file paths stable; avoid renaming `attendance_analyzer.py` without updating tests and docs.
- When changing CLI behavior, add tests demonstrating the new contract and examples in `README.md`.

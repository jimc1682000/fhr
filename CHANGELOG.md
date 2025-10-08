## v1.1.0 (2025-10-08)

### Feat

- implement export cleanup workflow and merge policy
- add debug mode with read-only state and verbose logging
- migrate to pre-commit framework and update coverage requirements
- add web service with FastAPI backend and static frontend
- **cli**: clearer --reset-state confirmation with timestamp (logger); test via assertLogs\n\nFixes #9
- **export**: include last_analysis_time in CSV/Excel status row; tests\n\nFixes #12
- **excel**: widen columns when status column present; tests
- add retry/backoff for holiday API; include tests
- add configurable rules and logging
- 增量分析與智慧備份功能完整實作

### Fix

- resolve lint errors and logging format issues
- resolve critical CSV merge bug and add security enhancements
- apply WFH recommendation to all Fridays regardless of attendance
- resolve E501 line length errors and add openpyxl dependency
- resolve linting errors from ruff
- resolve CI failures and security vulnerability
- **policy**: detect absence when punches missing
- validate holiday API URL scheme
- warn when holiday API returns no valid data

### Refactor

- dedupe logic; split analyzer; config; faster ranges
- **cli**: extract CLI orchestration into lib/cli.py; add tests
- **test**: delegate unprocessed-date filtering; add tests
- extract year/day helpers to lib/dates
- extract parser/grouping/report helpers into lib/
- slim attendance_analyzer.py for readability
- **lib**: introduce holiday providers and service (phase 3)
- **lib**: extract AttendanceStateManager and CSV exporter (phase 2)
- **lib**: extract filename/backup/policy from attendance_analyzer

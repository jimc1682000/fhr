# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based attendance analysis system that processes employee attendance records from HR portals and calculates late arrivals, overtime, work-from-home (WFH) recommendations, and forget-punch suggestions. The system is designed for companies with flexible working hours in Taiwan.

## Core Commands

### Running the Analyzer
```bash
python3 attendance_analyzer.py <attendance_file_path> [format] [options]
```

**Format options**: `excel` (default) or `csv`

**Analysis options**:
- `--incremental` / `-i`: Enable incremental analysis (default)
- `--full` / `-f`: Force complete re-analysis
- `--reset-state` / `-r`: Clear user's processing state

### Basic Usage Examples
```bash
# Default incremental analysis
python3 attendance_analyzer.py 202508-員工姓名-出勤資料.txt

# Force complete re-analysis
python3 attendance_analyzer.py 202508-員工姓名-出勤資料.txt --full

# Clear state and re-analyze
python3 attendance_analyzer.py 202508-員工姓名-出勤資料.txt --reset-state

# Specify output format
python3 attendance_analyzer.py 202508-員工姓名-出勤資料.txt csv
```

### Testing with Sample Data
```bash
python3 attendance_analyzer.py sample-attendance-data.txt
python3 attendance_analyzer.py sample-attendance-data.txt csv
```

### Running Unit Tests
```bash
# full suite (quiet)
python3 -m unittest -q

# run a specific test module
python3 -m unittest -q test.test_holiday_api_resilience
```

### File Format Requirements

#### Input File Naming (Required for Incremental Analysis)
For incremental analysis to work, files must follow this naming convention:
- **Single month**: `YYYYMM-Name-出勤資料.txt` (e.g., `202508-員工姓名-出勤資料.txt`)
- **Cross-month**: `YYYYMM-YYYYMM-Name-出勤資料.txt` (e.g., `202508-202509-員工姓名-出勤資料.txt`)

#### Data Format
- Input files must be tab-separated text files with 9 columns
- Expected format: 應刷卡時段, 當日卡鐘資料, 刷卡別, 卡鐘編號, 資料來源, 異常狀態, 處理狀態, 異常處理作業, 備註
- Attendance records with empty "當日卡鐘資料" are treated as absenteeism
- **Complete work days**: Days with both check-in and check-out records (regardless of actual punch times)

## Architecture

### Core Data Structures
- **AttendanceRecord**: Individual check-in/out records with timestamps and metadata
- **WorkDay**: Daily work record containing check-in and check-out records for a single date
- **Issue**: Identified problems requiring action (late, overtime, WFH, etc.) with new/existing status tracking
- **AttendanceStateManager**: Manages JSON-based state persistence for incremental analysis

### Main Components

#### AttendanceAnalyzer (Enhanced)
Central processing engine with enhanced incremental analysis capabilities:
- `parse_attendance_file()`: Parses data and initializes incremental state
- `group_records_by_day()`: Groups records and loads holiday data
- `analyze_attendance()`: Smart analysis (full or incremental mode)
- `generate_report()`: Enhanced reporting with incremental statistics
- `export_csv()`: Enhanced CSV export with status column
- `export_excel()`: Enhanced Excel export with status indicators
- `export_report()`: Unified export interface with automatic backup
- `_backup_existing_file()`: **NEW**: Automatic file backup with timestamp naming

#### AttendanceStateManager (New)
JSON-based state management for incremental analysis:
- `_load_state()`: Loads processing state from `attendance_state.json`
- `save_state()`: Persists current processing state
- `get_user_processed_ranges()`: Retrieves user's previously processed date ranges
- `update_user_state()`: Updates user processing state and forget-punch usage
- `detect_date_overlap()`: Identifies overlapping date ranges for smart merging
- `state_data`: Property holding current state information

#### ExcelExporter (New)
Shared helper library for Excel output:
- `init_workbook()`: 建立工作簿與樣式
- `write_headers()`: 寫入標題列
- `write_status_row()`: 在增量模式寫入狀態資訊
- `write_issue_rows()`: 逐筆寫入問題資料列
- `set_column_widths()`: 調整欄寬
- `save_workbook()`: 儲存分析檔案

#### Incremental Analysis Features
- **Smart Date Range Detection**: Parses filenames to extract user names and date ranges
- **Overlap Handling**: Detects and handles overlapping date ranges intelligently
- **Complete Work Day Identification**: Only processes days with both check-in and check-out records
- **Monthly Forget-Punch Tracking**: Maintains per-month usage counters across analysis sessions
- **State Persistence**: Saves processing history to `attendance_state.json`

### Business Rules (Hard-coded Constants)
- Working hours: 8 hours + 1 hour lunch break
- Flexible check-in: 08:30 (earliest) to 10:30 (latest)
- Lunch period: 12:30-13:30 (deducted from late calculations when applicable)
- Overtime threshold: Minimum 60 minutes to qualify for application
- Forget-punch allowance: 2 times per month for tardiness ≤60 minutes
- Friday WFH policy: Fridays are default WFH days (9-hour WFH leave recommended)

### Taiwan Holiday Integration
The system supports mixed holiday loading strategy:
- **2025 (Current Year)**: Hardcoded holidays for optimal performance
- **Other Years**: Dynamic loading with fallback to basic holidays when API unavailable
- **Auto-Detection**: Automatically detects years in attendance data and loads required holidays
- **API Integration**: Attempts to load from government open data API, falls back to basic holidays (New Year's Day, National Day) when API fails
- **Caching**: Tracks loaded years to avoid duplicate API calls

Key methods:
- `_load_taiwan_holidays(years)`: Main holiday loading coordinator
- `_load_hardcoded_2025_holidays()`: Efficient 2025 holiday loading
- `_load_dynamic_holidays(year)`: Dynamic loading for other years
- `_get_years_from_records()`: Extracts years from attendance data

## Key Behavioral Notes

### Issue Classification Logic
- **Forget-punch**: Tardiness ≤60 minutes with monthly allowance available
- **Late**: Tardiness >60 minutes or when forget-punch allowance exhausted
- **Overtime**: Work beyond calculated end time, minimum 60 minutes
- **WFH Leave**: Recommended for Fridays (unless national holiday)
- **Regular Leave**: Recommended for full-day absences on weekdays

## Incremental Analysis Workflow

### How It Works
1. **File Analysis**: System extracts user name and date range from filename
2. **State Loading**: Loads existing processing history from `attendance_state.json`
3. **Overlap Detection**: Identifies previously processed date ranges
4. **Complete Work Day Identification**: Finds days with both check-in and check-out records
5. **Smart Processing**: Analyzes only new complete work days
6. **State Update**: Saves updated processing state and forget-punch usage

### State File Structure
```json
{
  "users": {
    "員工姓名": {
      "processed_date_ranges": [
        {
          "start_date": "2025-08-01",
          "end_date": "2025-08-31", 
          "source_file": "202508-員工姓名-出勤資料.txt",
          "last_analysis_time": "2025-08-27T14:30:00"
        }
      ],
      "forget_punch_usage": {
        "2025-08": 1,
        "2025-09": 0
      }
    }
  }
}
```

### Cross-Month Data Handling
- Supports both single-month (`202508-員工姓名-出勤資料.txt`) and cross-month (`202508-202509-員工姓名-出勤資料.txt`) files
- Automatically detects date overlaps and processes only new ranges
- Maintains separate forget-punch counters for each month
- Provides clear overlap warnings during processing

### Output Formats

#### Automatic File Backup System
- **Smart Backup**: Before creating new analysis files, existing files are automatically backed up
- **Timestamp Naming**: Backup files use format `<original>_YYYYMMDD_HHMMSS.<ext>`
- **Example**: `sample-attendance-data_analysis.xlsx` → `sample-attendance-data_analysis_20250827_165618.xlsx`
- **User Control**: Users can manage their own file versions and retention policies
- **Safety First**: No data loss from accidental overwrites

#### Excel Format (Default) - Enhanced
- File naming: `<original_filename>_analysis.xlsx`
- Professional formatting with color-coded issue types:
  - Late: Light red background
  - Overtime: Light blue background
  - WFH: Light green background
  - Forget punch: Light orange background
- **NEW**: Status column in incremental mode showing "[NEW]" vs existing issues
- **NEW**: If no new issues in incremental mode, row 2 outputs a status row including
  the last processed date and the "last_analysis_time"
- Auto-adjusted column widths (incremental mode widens Calculation column to 40 and
  Status column to 24 for readability)
- Cross-platform compatibility (Windows/Mac/Linux)
- Requires `openpyxl` library (auto-fallback to CSV if unavailable)

#### CSV Format (Compatibility) - Enhanced
- File naming: `<original_filename>_analysis.csv`
- UTF-8-BOM encoding for Mac Excel compatibility
- Semicolon-delimited for proper Excel parsing
- **NEW**: Status column in incremental mode for tracking new vs existing issues;
  if no new issues, outputs a status row including "last_analysis_time"
- Includes emoji indicators and detailed calculation explanations

#### Terminal Report - Enhanced
- **NEW**: Incremental analysis statistics (processed/skipped days)
- **NEW**: User identification and date range information
- All existing formatting and emoji indicators preserved

### Holiday API Resilience (Important)
- Dynamic holiday loading uses retries with exponential backoff and jitter; non‑retryable
  4xx (e.g., 403) fails fast. On persistent failure it falls back to basic holidays.
- Environment variables (override defaults):
  - `HOLIDAY_API_MAX_RETRIES` (default: 3)
  - `HOLIDAY_API_BACKOFF_BASE` (default: 0.5)
  - `HOLIDAY_API_MAX_BACKOFF` (default: 8)
- Tests must mock `urllib.request.urlopen`; do not perform real network calls. To keep
  tests fast/deterministic, set the backoff env vars to 0 in test setup.

### Privacy Considerations
The .gitignore is configured to exclude real employee data files while preserving sample files for testing. Never commit files matching patterns like:
- `*-出勤資料.txt` or `*JimmyChen*.txt` (actual attendance data files)
- `*_analysis.csv` or `*_analysis.xlsx` (analysis result files)
- `attendance_state.json` (state file containing user identification information)

**Important**: The `attendance_state.json` file contains user names and processing history, and must be excluded from version control to protect user privacy.

## Testing and Validation

### Unit Tests
The system includes comprehensive unit tests across multiple files under `test/` covering:

#### Core Business Logic (8 tests)
- Basic file parsing and data grouping
- Late arrival calculations (including lunch time deduction logic)
- Overtime calculations with minimum thresholds
- Friday WFH recommendations
- Forget-punch suggestion logic
- Report generation functionality
- Error handling for empty files
- Cross-year attendance data processing

#### Export and Output
- CSV export functionality (status column and status row when applicable)
- Excel export with formatting/headers/status row
- Column widths in incremental mode (calculation/status columns wider)

#### Advanced Features
- Taiwan holiday recognition (hardcoded 2025 + dynamic loading)
- Holiday API retry/timeout/5xx fallback scenarios
- Friday WFH on national holiday edge case
- Overtime hourly rounding edges
- Cross-year data processing with holiday loading

## Logging & Privacy Notes
- Use `logging` (info/warning/error) for user‑visible messages; avoid `print`.
- Prefer absolute dates (YYYY‑MM‑DD) in logs to avoid ambiguity.
- Data structure validation (3 sub-tests)

#### **NEW: Incremental Analysis & Backup (5 tests)**
- **Incremental Analysis Core**: Filename parsing for user/date extraction, format validation
- **State Management**: JSON persistence, user state updates, overlap detection
- **Backup System**: Automatic file backup with timestamp naming, size verification
- **Complete Work Day Logic**: Identification of days with both check-in/out records
- **Enhanced Output**: Status column validation, new vs existing issue marking

#### **NEW: File Backup Testing**
- Automatic backup file creation with timestamp format `YYYYMMDD_HHMMSS`
- Backup file integrity verification (size matching)
- Non-existent file handling (graceful no-op behavior)
- Proper cleanup of temporary test files

Run tests with: `python3 -m unittest test.test_attendance_analyzer`

**Test Quality Features:**
- Isolated execution using temporary files
- Automatic cleanup of all test artifacts
- Real-world scenario validation
- Edge case and error condition coverage

### Integration Testing
Real-world testing scenarios have been validated:
- ✅ **Incremental Processing**: Skip previously analyzed data effectively
- ✅ **Cross-Month Support**: Handle `202508-202509-Name-出勤資料.txt` format
- ✅ **State Persistence**: Maintain processing history across sessions
- ✅ **Overlap Detection**: Smart handling of duplicate date ranges
- ✅ **Command Line Options**: All options (`--full`, `--reset-state`) working correctly
- ✅ **Output Enhancement**: Status columns and incremental statistics display properly

### Sample Data Testing
Use `sample-attendance-data.txt` for integration testing - it contains various scenarios including normal check-ins, tardiness, overtime, absences, and Friday WFH cases. The corresponding `sample-attendance-data_analysis.csv` shows expected output format.

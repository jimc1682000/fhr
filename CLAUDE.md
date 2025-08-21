# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based attendance analysis system that processes employee attendance records from HR portals and calculates late arrivals, overtime, work-from-home (WFH) recommendations, and forget-punch suggestions. The system is designed for companies with flexible working hours in Taiwan.

## Core Commands

### Running the Analyzer
```bash
python3 attendance_analyzer.py <attendance_file_path> [format]
```

**Format options**: `excel` (default) or `csv`

### Testing with Sample Data
```bash
python3 attendance_analyzer.py sample-attendance-data.txt
python3 attendance_analyzer.py sample-attendance-data.txt csv
```

### Running Unit Tests
```bash
python3 test_attendance_analyzer.py
```

### File Format Requirements
- Input files must be tab-separated text files with 9 columns
- Expected format: 應刷卡時段, 當日卡鐘資料, 刷卡別, 卡鐘編號, 資料來源, 異常狀態, 處理狀態, 異常處理作業, 備註
- Attendance records with empty "當日卡鐘資料" are treated as absenteeism

## Architecture

### Core Data Structures
- **AttendanceRecord**: Individual check-in/out records with timestamps and metadata
- **WorkDay**: Daily work record containing check-in and check-out records for a single date
- **Issue**: Identified problems requiring action (late, overtime, WFH, etc.)

### Main Components
- **AttendanceAnalyzer**: Central processing engine with these key methods:
  - `parse_attendance_file()`: Parses tab-separated attendance data
  - `group_records_by_day()`: Groups individual records into work days
  - `analyze_attendance()`: Core business logic for detecting issues
  - `generate_report()`: Creates formatted terminal output
  - `export_csv()`: Exports results with UTF-8-BOM for Mac Excel compatibility
  - `export_excel()`: Exports formatted Excel files with color coding and styling
  - `export_report()`: Unified export interface supporting both formats

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

### Output Formats

#### Excel Format (Default)
- File naming: `<original_filename>_analysis.xlsx`
- Professional formatting with color-coded issue types:
  - Late: Light red background
  - Overtime: Light blue background
  - WFH: Light green background
  - Forget punch: Light orange background
- Auto-adjusted column widths
- Cross-platform compatibility (Windows/Mac/Linux)
- Requires `openpyxl` library (auto-fallback to CSV if unavailable)

#### CSV Format (Compatibility)
- File naming: `<original_filename>_analysis.csv`
- UTF-8-BOM encoding for Mac Excel compatibility
- Semicolon-delimited for proper Excel parsing
- Includes emoji indicators and detailed calculation explanations

### Privacy Considerations
The .gitignore is configured to exclude real employee data files while preserving sample files for testing. Never commit files matching patterns like `*-出勤資料.txt` or `*JimmyChen*.txt`.

## Testing and Validation

### Unit Tests
The system includes comprehensive unit tests in `test_attendance_analyzer.py` covering:
- Basic file parsing and data grouping
- Late arrival calculations (including lunch time deduction logic)
- Overtime calculations with minimum thresholds
- Friday WFH recommendations
- Forget-punch suggestion logic
- CSV export functionality
- Excel export functionality with formatting validation
- Cross-year attendance data processing
- Taiwan holiday recognition (hardcoded 2025 + dynamic loading)
- Unified export interface testing
- Error handling for empty files

Run tests with: `python3 test_attendance_analyzer.py`

### Sample Data Testing
Use `sample-attendance-data.txt` for integration testing - it contains various scenarios including normal check-ins, tardiness, overtime, absences, and Friday WFH cases. The corresponding `sample-attendance-data_analysis.csv` shows expected output format.
import csv
import os
from collections import OrderedDict
from collections.abc import Iterable


def _header_row(incremental_mode: bool) -> list[str]:
    headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
    if incremental_mode:
        headers.append('狀態')
    return headers


def _status_row(last_date: str, complete_days: int, last_analysis_time: str) -> list[str]:
    return [
        last_date,
        "狀態資訊",
        0,
        (
            f"📊 增量分析完成，已處理至 {last_date}，共 {complete_days} 個完整工作日 | "
            f"上次分析時間: {last_analysis_time}"
        ),
        "",
        "上次處理範圍內無新問題需要申請",
        "系統狀態",
    ]


def _issue_row(issue, incremental_mode: bool) -> list[str]:
    row = [
        issue.date.strftime('%Y/%m/%d'),
        issue.type.value,
        issue.duration_minutes,
        issue.description,
        issue.time_range,
        issue.calculation,
    ]
    if incremental_mode:
        row.append("[NEW] 本次新發現" if getattr(issue, 'is_new', False) else "已存在")
    return row


def write_headers(writer: csv.writer, incremental_mode: bool) -> None:
    writer.writerow(_header_row(incremental_mode))


def write_status_row(
    writer: csv.writer, last_date: str, complete_days: int, last_analysis_time: str
) -> None:
    writer.writerow(_status_row(last_date, complete_days, last_analysis_time))


def write_issue_rows(writer: csv.writer, issues: Iterable, incremental_mode: bool) -> None:
    for issue in issues:
        writer.writerow(_issue_row(issue, incremental_mode))


def _build_rows(
    issues: list[object], incremental_mode: bool, status: tuple | None = None
) -> list[list[str]]:
    rows: list[list[str]] = []
    rows.append(_header_row(incremental_mode))
    if status and incremental_mode and not issues:
        last_date, complete_days, last_analysis_time = status
        rows.append(_status_row(last_date, complete_days, last_analysis_time))
    for issue in issues:
        rows.append(_issue_row(issue, incremental_mode))
    return rows


def _normalize_row(row: list[str], width: int) -> list[str]:
    if len(row) > width:
        return row[:width]
    if len(row) < width:
        return row + [''] * (width - len(row))
    return row


def _row_key(row: list[str]) -> tuple:
    if len(row) > 1 and row[1] == '狀態資訊':
        return ('STATUS', row[0])
    # Use only date and type as key to allow updating same-day same-type issues
    limit = min(2, len(row))
    return tuple(row[:limit])


def _merge_rows(existing: list[list[str]], new_rows: list[list[str]]) -> list[list[str]]:
    """Merge existing CSV rows with new rows, deduplicating by key.

    New rows take precedence over existing ones with the same key.
    Status rows should only appear when there are NO other data rows in the final result.
    """
    header = new_rows[0]
    width = len(header)
    merged = OrderedDict()

    # First, add existing rows (excluding header)
    if existing:
        for row in existing[1:]:  # Skip existing header
            if not row:
                continue
            normalized = _normalize_row(row, width)
            merged[_row_key(normalized)] = normalized

    # Then add/update with new rows (they take precedence)
    for row in new_rows[1:]:
        if not row:
            continue
        normalized = _normalize_row(row, width)
        merged[_row_key(normalized)] = normalized

    # Check if merged result has any non-status data rows
    has_any_issues = any(
        key and key[0] != 'STATUS'
        for key in merged
    )

    result: list[list[str]] = [header]

    # Extract status row if present
    status_key = None
    for key in list(merged):
        if key and key[0] == 'STATUS':
            status_key = key
            break

    # Only include status row if there are NO other data rows
    if status_key is not None:
        if has_any_issues:
            # Remove status row when other issues exist
            merged.pop(status_key)
        else:
            # Place status row immediately after header when it's the only data
            result.append(merged.pop(status_key))

    # Add remaining rows
    result.extend(merged.values())
    return result


def save_csv(
    filepath: str,
    issues: Iterable,
    incremental_mode: bool,
    status: tuple | None = None,
    merge: bool = False,
) -> None:
    """Persist CSV with optional status row.

    status: (last_date, complete_days, last_analysis_time) if provided
    merge: when True, rewrite the canonical export in place (no timestamped backup).
    """

    issues_list = list(issues)
    rows = _build_rows(issues_list, incremental_mode, status)

    if merge and os.path.exists(filepath):
        # Read existing CSV data for merging
        existing_rows: list[list[str]] = []
        try:
            with open(filepath, encoding='utf-8-sig') as f:
                reader = csv.reader(f, delimiter=';')
                existing_rows = list(reader)
        except (FileNotFoundError, OSError):
            # If file doesn't exist or can't be read, proceed with new rows only
            existing_rows = []
        rows = _merge_rows(existing_rows, rows)

    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(rows)

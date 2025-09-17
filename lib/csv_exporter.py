import csv
from collections.abc import Iterable


def write_headers(writer: csv.writer, incremental_mode: bool) -> None:
    headers = ['日期', '類型', '時長(分鐘)', '說明', '時段', '計算式']
    if incremental_mode:
        headers.append('狀態')
    writer.writerow(headers)


def write_status_row(
    writer: csv.writer, last_date: str, complete_days: int, last_analysis_time: str
) -> None:
    status_row = [
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
    writer.writerow(status_row)


def write_issue_rows(writer: csv.writer, issues: Iterable, incremental_mode: bool) -> None:
    for issue in issues:
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
        writer.writerow(row)


def save_csv(filepath: str, issues: Iterable, incremental_mode: bool,
             status: tuple | None = None) -> None:
    """Persist CSV with optional status row.

    status: (last_date, complete_days, last_analysis_time) if provided
    """
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f, delimiter=';')
        write_headers(writer, incremental_mode)
        if status and incremental_mode and (not list(issues)):
            last_date, complete_days, last_analysis_time = status
            write_status_row(writer, last_date, complete_days, last_analysis_time)
        # 寫入資料列
        write_issue_rows(writer, issues, incremental_mode)

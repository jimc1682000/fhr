"""Report building helpers for attendance analyzer.

Pure string assembly; no dependency on analyzer types.
"""

from collections.abc import Iterable


def build_incremental_lines(
    user: str, total_complete: int, unprocessed_count: int, unprocessed_dates: list[str]
) -> list[str]:
    lines: list[str] = []
    lines.append("## 📈 增量分析資訊：\n")
    lines.append(f"- 👤 使用者：{user}")
    lines.append(f"- 📊 總完整工作日：{total_complete} 天")
    lines.append(f"- 🔄 新處理工作日：{unprocessed_count} 天")
    lines.append(f"- ⏭️  跳過已處理：{total_complete - unprocessed_count} 天")
    if unprocessed_dates:
        preview = ", ".join(unprocessed_dates[:5])
        if len(unprocessed_dates) > 5:
            preview += f" 等 {len(unprocessed_dates)} 天"
        lines.append(f"- 📅 新處理日期：{preview}")
    lines.append("")
    return lines


def build_issue_section(
    title: str, prefix_icon: str, issues: Iterable, show_calc: bool = True
) -> list[str]:
    lines: list[str] = []
    if not issues:
        return lines
    lines.append(f"{title}\n")
    for i, issue in enumerate(issues, 1):
        lines.append(
            f"{i}. **{issue.date.strftime('%Y/%m/%d')}** - {prefix_icon} {issue.description}"
        )
        if getattr(issue, "time_range", ""):
            lines.append(f"   ⏰ 時段: {issue.time_range}")
        if show_calc and getattr(issue, "calculation", ""):
            lines.append(f"   🧮 計算: {issue.calculation}")
        lines.append("")
    return lines


def build_summary(
    forget: int,
    late: int,
    overtime: int,
    early_leave: int,
    weekday_leave: int,
    wfh: int,
) -> list[str]:
    return [
        "## 📊 統計摘要：\n",
        f"- 🔄 建議忘刷卡天數：{forget} 天",
        f"- 😰 需要請遲到天數：{late} 天",
        f"- 💪 加班天數：{overtime} 天",
        f"- ⏰ 早退天數：{early_leave} 天",
        f"- 📝 需要請假天數：{weekday_leave} 天",
        f"- 🏠 建議WFH天數：{wfh} 天",
    ]

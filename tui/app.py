from __future__ import annotations

import glob
import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from functools import partial
from typing import Any

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Log,
    ProgressBar,
    Select,
    Static,
    Switch,
)
from textual.worker import Worker, WorkerState

from lib.i18n import get_translator
from lib.service import (
    AnalysisCancelled,
    AnalysisError,
    AnalysisOptions,
    AnalysisResult,
    AnalyzerService,
    OutputRequest,
    ResetStateError,
)

_STAGE_LABELS: dict[str, str] = {
    "parse": "Parsing attendance data",
    "group": "Grouping daily records",
    "analyze": "Applying analysis rules",
    "export": "Exporting reports",
}

_WAITING_MESSAGE = "⏳ Waiting for analysis to start"
_PREPARING_MESSAGE = "🚀 Preparing analysis"
_SUCCESS_MESSAGE = "✅ Analysis complete"
_ERROR_MESSAGE = "❌ Analysis failed"
_CANCELLED_MESSAGE = "🛑 Analysis cancelled"
_LANGUAGE_MESSAGE_EN = "🌐 Language switched to English"
_LANGUAGE_MESSAGE_ZH = "🌐 Language switched to Traditional Chinese"


@dataclass(slots=True)
class _PendingRun:
    options: AnalysisOptions
    form_data: dict[str, Any]


class AnalysisForm(Static):
    """Collects analysis parameters from the operator."""

    DEFAULT_CSS = """
    AnalysisForm {
        background: $surface;
        border: tall $primary;
        padding: 0;
        height: 1fr;
    }

    AnalysisForm VerticalScroll {
        height: 1fr;
        padding: 1 2;
    }

    AnalysisForm .section-label {
        color: $text;
        text-style: bold;
        margin-top: 1;
    }

    AnalysisForm .file-hint {
        color: $text-muted;
        margin-left: 2;
    }

    AnalysisForm .file-button {
        width: 100%;
        margin-top: 0;
        margin-bottom: 0;
    }

    AnalysisForm Input,
    AnalysisForm Select,
    AnalysisForm Switch {
        margin-top: 1;
    }

    AnalysisForm #form-buttons Button {
        margin-top: 1;
    }

    AnalysisForm #form-buttons {
        padding-top: 1;
        margin-bottom: 1;
    }

    AnalysisForm #status-message {
        height: auto;
        margin-top: 1;
    }
    """

    class Submitted(Message):
        """Emitted when the operator requests an analysis run."""

        def __init__(self, sender: AnalysisForm, data: dict[str, Any]) -> None:
            self.data = data
            super().__init__()

    class CancelRequested(Message):
        """Emitted when the operator requests cancellation."""

        def __init__(self, sender: AnalysisForm) -> None:
            super().__init__()

    busy: reactive[bool] = reactive(False, repaint=False)

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Label("分析設定", classes="section-label")

            # Show available .txt files in current directory
            txt_files = sorted([f for f in glob.glob("*.txt") if not f.startswith("requirements")])
            if txt_files:
                yield Label(f"📂 快速選擇檔案 ({len(txt_files)} 個)：", classes="section-label")
                for fname in txt_files[:5]:  # Show first 5
                    file_btn = Button(f"📄 {fname}", classes="file-button", id=f"file-{fname}")
                    file_btn.variant = "default"
                    yield file_btn
                if len(txt_files) > 5:
                    yield Label(f"  ... 還有 {len(txt_files) - 5} 個檔案", classes="file-hint")

            yield Label("或手動輸入路徑：", classes="section-label")
            self.source_input = Input(placeholder="輸入考勤TXT檔案路徑", id="source-path")
            yield self.source_input

            self.output_input = Input(
                placeholder="輸出資料夾（留空沿用輸入檔同路徑）",
                id="output-dir",
            )
            yield self.output_input

            yield Label("輸出格式", classes="section-label")
            self.format_select = Select(
                (
                    ("Excel（含細節報表）", "excel"),
                    ("CSV（純文字報表）", "csv"),
                ),
                value="excel",
            )
            yield self.format_select

            yield Label("匯出策略", classes="section-label")
            self.export_policy_select = Select(
                (
                    ("merge（覆寫主檔案）", "merge"),
                    ("archive（保留時間戳備份）", "archive"),
                ),
                value="merge",
            )
            yield self.export_policy_select

            yield Label("分析模式", classes="section-label")
            self.mode_select = Select(
                (
                    ("增量（推薦，僅處理新紀錄）", "incremental"),
                    ("完整（重新分析）", "full"),
                ),
                value="incremental",
            )
            yield self.mode_select

            yield Label("清除使用者既有狀態後再分析", classes="section-label")
            self.reset_switch = Switch(value=False, id="reset-state", name="reset-state")
            yield self.reset_switch

            yield Label("Debug 模式（僅讀取、保留詳細日誌）", classes="section-label")
            self.debug_switch = Switch(value=False, id="debug-mode", name="debug-mode")
            yield self.debug_switch

            yield Label("記住此檔案（下次快速選擇）", classes="section-label")
            self.add_recent_switch = Switch(value=True, id="add-recent", name="add-recent")
            yield self.add_recent_switch

            yield Label("若為 Excel 同時輸出 CSV 副本", classes="section-label")
            self.extra_csv_switch = Switch(value=False, id="extra-csv", name="extra-csv")
            yield self.extra_csv_switch

            yield Label("預覽筆數上限", classes="section-label")
            self.preview_input = Input(
                value="100",
                placeholder="預覽最多顯示的異常筆數",
                id="preview-limit",
            )
            yield self.preview_input

            with Container(id="form-buttons"):
                self.run_button = Button("開始分析", id="run-analysis", variant="success")
                self.cancel_button = Button(
                    "取消執行",
                    id="cancel-run",
                    variant="warning",
                    disabled=True,
                )
                yield self.run_button
                yield self.cancel_button

            self.status_message = Static("", id="status-message")
            yield self.status_message

    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        for widget in (
            self.source_input,
            self.output_input,
            self.format_select,
            self.export_policy_select,
            self.mode_select,
            self.reset_switch,
            self.debug_switch,
            self.add_recent_switch,
            self.extra_csv_switch,
            self.preview_input,
        ):
            widget.disabled = busy
        self.run_button.disabled = busy or not self._has_source_path
        self.cancel_button.disabled = not busy

    @property
    def _has_source_path(self) -> bool:
        return bool(self.source_input.value.strip())

    def submit(self) -> None:
        if self.busy:
            return
        if not self._has_source_path:
            self.show_status("⚠️ 請先輸入考勤檔案路徑。", "warning")
            return
        self.post_message(self.Submitted(self, self._collect_data()))

    def request_cancel(self) -> None:
        if not self.cancel_button.disabled:
            self.post_message(self.CancelRequested(self))

    def show_status(self, message: str, level: str = "info") -> None:
        style = {
            "info": "bold $text",
            "success": "bold green",
            "warning": "bold $warning",
            "error": "bold red",
        }.get(level, "bold $text")
        self.status_message.update(Text(message, style=style))

    def clear_status(self) -> None:
        self.status_message.update("")

    def _collect_data(self) -> dict[str, Any]:
        return {
            "source_path": self.source_input.value.strip(),
            "output_dir": self.output_input.value.strip(),
            "format": self.format_select.value or "excel",
            "export_policy": self.export_policy_select.value or "merge",
            "mode": self.mode_select.value or "incremental",
            "reset_state": self.reset_switch.value,
            "debug": self.debug_switch.value,
            "add_recent": self.add_recent_switch.value,
            "extra_csv": self.extra_csv_switch.value,
            "preview_limit": self.preview_input.value.strip(),
        }

    @on(Button.Pressed, ".file-button")
    def _on_file_button_pressed(self, event: Button.Pressed) -> None:
        """Handle file button clicks"""
        if event.button.id and event.button.id.startswith("file-"):
            filename = event.button.id[5:]  # Remove "file-" prefix
            self.source_input.value = filename
            self.source_input.focus()

    @on(Input.Changed, "#source-path")
    def _on_source_changed(self, event: Input.Changed) -> None:
        self.run_button.disabled = self.busy or not bool(event.value.strip())

    @on(Input.Submitted, "#source-path")
    @on(Input.Submitted, "#output-dir")
    @on(Input.Submitted, "#preview-limit")
    def _on_input_submitted(self, _: Input.Submitted) -> None:
        """Handle Enter key in any input field"""
        if self.busy:
            self.show_status("⚠️ 目前已有分析在進行中，請按 Ctrl+C 取消或等待完成。", "warning")
        elif not self._has_source_path:
            self.show_status("⚠️ 請先輸入考勤檔案路徑。", "warning")
        else:
            self.submit()

    @on(Button.Pressed, "#run-analysis")
    def _on_submit_pressed(self, _: Button.Pressed) -> None:
        self.submit()

    @on(Button.Pressed, "#cancel-run")
    def _on_cancel_pressed(self, _: Button.Pressed) -> None:
        self.request_cancel()


class SummaryPanel(Static):
    """Displays the outcome of the most recent analysis."""

    DEFAULT_CSS = """
    SummaryPanel {
        border: round $secondary;
        padding: 1;
        height: auto;
        background: $surface-lighten-1;
    }
    """

    def on_mount(self) -> None:  # pragma: no cover - UI hook
        self.show_placeholder()

    def show_placeholder(self) -> None:
        self.update(Text("尚未執行分析", style="dim"))

    def update_result(self, result: AnalysisResult) -> None:
        lines: list[Text] = []

        header = Text("分析結果摘要", style="bold $text")
        lines.append(header)
        user_text = result.user_name or "無法自檔名判定"
        period = "—"
        if result.start_date or result.end_date:
            period = f"{result.start_date or '—'} ~ {result.end_date or '—'}"
        lines.append(Text(f"👤 使用者：{user_text}"))
        lines.append(Text(f"📅 期間：{period}"))

        mode_label = "增量" if result.effective_mode == "incremental" else "完整"
        requested = "增量" if result.requested_mode == "incremental" else "完整"
        lines.append(Text(f"⚙️ 模式：{mode_label}（請求：{requested}）"))
        if result.reset_applied:
            lines.append(Text("🗑️ 已清除使用者狀態", style="yellow"))
        elif result.first_time_user:
            lines.append(Text("✨ 首次分析該使用者", style="green"))

        if result.status:
            status_parts = [
                f"📌 增量狀態：最後日期 {result.status.last_date}，",
                f"完成 {result.status.complete_days} 天，",
                f"上次分析於 {result.status.last_analysis_time}",
            ]
            lines.append(Text("".join(status_parts), style="cyan"))

        if result.outputs:
            lines.append(Text("📂 匯出檔案："))
            for exported in result.outputs:
                note = " (CSV 回退)" if exported.fallback_applied else ""
                lines.append(
                    Text(f"  • {exported.actual_path}{note}", style="bold $success"),
                )

        totals = result.totals or {}
        if totals:
            lines.append(Text("📊 問題統計："))
            mapping = {
                "FORGET_PUNCH": "忘刷卡",
                "LATE": "遲到",
                "OVERTIME": "加班",
                "WFH": "WFH假",
                "WEEKDAY_LEAVE": "請假",
            }
            for key, label in mapping.items():
                if key in totals:
                    lines.append(Text(f"  • {label}: {totals[key]} 筆"))
            if "TOTAL" in totals:
                lines.append(Text(f"  • 合計: {totals['TOTAL']} 筆"))

        if not lines:
            self.show_placeholder()
            return

        output = Text()
        for index, line in enumerate(lines):
            if index:
                output.append("\n")
            output.append_text(line)
        self.update(output)


class AttendanceAnalyzerApp(App[None]):
    """Textual application that orchestrates attendance analysis runs."""

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }

    #main {
        layout: horizontal;
        height: 1fr;
        padding: 1 2;
    }

    #form-panel {
        width: 40%;
        min-width: 50;
    }

    #output-panel {
        width: 60%;
        layout: vertical;
        background: $surface-darken-1;
        border: tall $secondary;
        padding: 1 2;
        height: 1fr;
    }

    #progress-header,
    #preview-header,
    #summary-header {
        text-style: bold;
        color: $text;
        margin-bottom: 1;
    }

    #progress-bar {
        height: auto;
        margin-bottom: 1;
    }

    #progress-stage {
        height: auto;
        margin-bottom: 1;
    }

    #progress-log {
        height: 1fr;
        border: panel $primary;
        background: $surface;
    }

    #preview-table {
        height: 1fr;
        border: panel $primary;
        margin-top: 1;
    }

    SummaryPanel {
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("ctrl+d", "toggle_dark", "切換主題"),
        ("ctrl+c", "cancel_analysis", "取消分析"),
        ("ctrl+l", "toggle_language", "切換語言"),
        ("enter , f5", "submit_form", "執行分析"),
        ("q", "quit", "退出程式"),
    ]

    _TYPE_STYLES = {
        "遲到": "bold yellow",
        "忘刷卡": "bold red",
        "加班": "bold magenta",
        "WFH假": "bold green",
        "請假": "bold cyan",
    }

    def __init__(self) -> None:
        super().__init__()
        self._cancel_event: threading.Event | None = None
        self._analysis_worker: Worker[AnalysisResult] | None = None
        self._pending: _PendingRun | None = None
        self._last_form_data: dict[str, Any] | None = None
        self._language = os.getenv("FHR_LANG", "zh_TW")
        if self._language not in {"zh_TW", "en"}:
            self._language = "zh_TW"
        self._progress_message_id = _WAITING_MESSAGE
        self._progress_message_style = "bold $text"
        self._progress_message_suffix: str | None = None
        self.progress_stage: Static | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main"):
            yield AnalysisForm(id="form-panel")
            with Container(id="output-panel"):
                yield Label("執行進度", id="progress-header")
                self.progress_bar = ProgressBar(total=4, id="progress-bar")
                yield self.progress_bar
                self.progress_stage = Static(self._translate(_WAITING_MESSAGE), id="progress-stage")
                yield self.progress_stage
                self.progress_log = Log(highlight=True, auto_scroll=True, id="progress-log")
                yield self.progress_log

                yield Label("異常預覽", id="preview-header")
                with VerticalScroll(id="preview-table"):
                    self.preview_table = DataTable(show_header=True, zebra_stripes=True)
                    yield self.preview_table

                yield Label("分析摘要", id="summary-header")
                self.summary_panel = SummaryPanel()
                yield self.summary_panel
        yield Footer()

    def on_mount(self) -> None:
        self.dark = True
        self.preview_table.add_columns("日期", "類型", "時數", "描述", "狀態")
        self.preview_table.zebra_stripes = True
        self.summary_panel.show_placeholder()
        form = self.query_one(AnalysisForm)
        form.show_status("請填寫分析參數後按 Enter 或按鈕開始。")
        self._set_progress_message(_WAITING_MESSAGE, "bold $text")

    def on_analysis_form_submitted(self, message: AnalysisForm.Submitted) -> None:
        if self._analysis_worker and self._analysis_worker.is_running:
            self._form.show_status("⚠️ 目前已有分析在進行中。", "warning")
            return
        self._last_form_data = message.data
        try:
            pending = self._prepare_options(message.data)
        except ValueError as exc:
            self._form.show_status(f"⚠️ {exc}", "warning")
            return
        self._pending = pending
        self._start_analysis(pending)

    def on_analysis_form_cancel_requested(self, _: AnalysisForm.CancelRequested) -> None:
        self.action_cancel_analysis()

    def action_submit_form(self) -> None:
        if self._analysis_worker and self._analysis_worker.is_running:
            return
        self._form.submit()

    def action_cancel_analysis(self) -> None:
        if self._cancel_event and not self._cancel_event.is_set():
            self._cancel_event.set()
            self.progress_log.write_line("🛑 已送出取消要求…")
            self._form.show_status("🛑 已送出取消要求…", "warning")
        if self._analysis_worker and self._analysis_worker.is_running:
            self._analysis_worker.cancel()

    @property
    def _form(self) -> AnalysisForm:
        return self.query_one(AnalysisForm)

    def _prepare_options(self, data: dict[str, Any]) -> _PendingRun:
        source_path = data["source_path"]
        if not source_path:
            raise ValueError("請輸入考勤檔案路徑。")

        preview_limit_str = data.get("preview_limit", "").strip()
        if preview_limit_str:
            try:
                preview_limit = max(0, int(preview_limit_str))
            except ValueError as exc:  # pragma: no cover - UI validation
                raise ValueError("預覽筆數需為整數。") from exc
        else:
            preview_limit = 100

        output_dir = data.get("output_dir", "").strip()
        base_path, ext = os.path.splitext(source_path)
        if ext.lower() != ".txt":
            base_path = source_path
        if output_dir:
            filename = os.path.basename(base_path)
            base_path = os.path.join(output_dir, filename)

        format_choice = data.get("format", "excel") or "excel"
        export_policy = data.get("export_policy", "merge") or "merge"
        primary_ext = ".xlsx" if format_choice == "excel" else ".csv"
        primary_output = OutputRequest(
            path=f"{base_path}_analysis{primary_ext}",
            format=format_choice,
            export_policy=export_policy,
        )
        extra_outputs: list[OutputRequest] = []
        if format_choice == "excel" and data.get("extra_csv", True):
            extra_outputs.append(
                OutputRequest(
                    path=f"{base_path}_analysis.csv",
                    format="csv",
                    export_policy=export_policy,
                )
            )

        options = AnalysisOptions(
            source_path=source_path,
            requested_format=format_choice,
            mode=data.get("mode", "incremental") or "incremental",
            reset_state=bool(data.get("reset_state", False)),
            debug=bool(data.get("debug", False)),
            output=primary_output,
            extra_outputs=tuple(extra_outputs),
            add_recent=bool(data.get("add_recent", True)),
            preview_limit=preview_limit,
        )
        return _PendingRun(options=options, form_data=data)

    def _start_analysis(self, pending: _PendingRun) -> None:
        self._form.set_busy(True)
        self.progress_bar.update(progress=0)
        self._set_progress_message(_PREPARING_MESSAGE, "bold $text")
        self.progress_log.clear()
        self.progress_log.write_line("🚀 開始分析流程…")
        self.summary_panel.show_placeholder()

        self._cancel_event = threading.Event()
        work = partial(self._run_analysis, pending.options, self._cancel_event)
        self._analysis_worker = self.run_worker(
            work,
            name="analysis",
            description=f"分析 {os.path.basename(pending.options.source_path)}",
            exit_on_error=False,
            exclusive=True,
            thread=True,
        )

    def _run_analysis(
        self,
        options: AnalysisOptions,
        cancel_event: threading.Event,
    ) -> AnalysisResult:
        service = AnalyzerService()

        def _progress(stage: str, index: int | None, total: int | None) -> None:
            steps = total or 4
            current = index or 0
            self.call_from_thread(self._update_progress, stage, current, steps)

        return service.run(options, progress_cb=_progress, cancel_event=cancel_event)

    def _update_progress(self, stage: str, index: int, total: int) -> None:
        index = max(index, 0)
        total = max(total, 1)
        self.progress_bar.update(total=total, progress=index)
        label_id = _STAGE_LABELS.get(stage, stage)
        suffix = f" ({index}/{total})"
        self._set_progress_message(label_id, "bold cyan", suffix=suffix)
        self.progress_log.write_line(f"⏱️ {self._translate(label_id)}…")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if not self._analysis_worker or event.worker is not self._analysis_worker:
            return
        if event.state == WorkerState.SUCCESS:
            assert event.worker.result is not None
            self._handle_success(event.worker.result)
        elif event.state == WorkerState.ERROR:
            if isinstance(event.worker.error, AnalysisCancelled):
                self._handle_cancelled()
            else:
                self._handle_error(event.worker.error)
        elif event.state == WorkerState.CANCELLED:
            self._handle_cancelled()

    def _handle_success(self, result: AnalysisResult) -> None:
        self._form.set_busy(False)
        self.progress_bar.update(progress=self.progress_bar.total or 4)
        self._set_progress_message(_SUCCESS_MESSAGE, "bold green")
        self.progress_log.write_line("✅ 分析完成！")
        if result.reset_applied:
            self.progress_log.write_line("🗑️ 已清除使用者狀態檔案。")
        if result.first_time_user:
            self.progress_log.write_line("✨ 第一次分析該使用者，已自動使用完整模式。")
        if result.debug_mode:
            self.progress_log.write_line("🐞 Debug 模式啟用：未寫入狀態檔。")
        for exported in result.outputs:
            prefix = "📝" if exported.actual_format == "csv" else "📄"
            fallback = " (CSV 回退)" if exported.fallback_applied else ""
            self.progress_log.write_line(f"{prefix} {exported.actual_path}{fallback}")

        self.summary_panel.update_result(result)
        self._render_preview(result)
        self._form.show_status("✅ 分析完成。", "success")
        self._cleanup_worker()

    def _render_preview(self, result: AnalysisResult) -> None:
        self.preview_table.clear()
        preview = result.issues_preview
        if not preview:
            self.preview_table.add_row("—", "—", "—", "目前沒有異常紀錄", "")
            return
        for issue in preview:
            type_style = self._TYPE_STYLES.get(issue.type, "bold")
            type_text = Text(issue.type, style=type_style)
            duration_text = Text(f"{issue.duration_minutes} 分鐘")
            description = Text(issue.description)
            if issue.time_range:
                description.append(f"\n{issue.time_range}", style="dim")
            if issue.calculation:
                description.append(f"\n{issue.calculation}", style="dim")
            status_text = Text(issue.status or "")
            if issue.status and "NEW" in issue.status:
                status_text.stylize("bold green")
            elif issue.status:
                status_text.stylize("dim")
            self.preview_table.add_row(
                issue.date,
                type_text,
                duration_text,
                description,
                status_text,
            )
        if len(result.issues) > len(preview):
            remaining = len(result.issues) - len(preview)
            self.progress_log.write_line(
                f"ℹ️ 僅顯示前 {len(preview)} 筆異常，還有 {remaining} 筆可透過匯出檔查看。"
            )

    def _handle_error(self, error: BaseException | None) -> None:
        self._form.set_busy(False)
        message = "❌ 分析失敗。"
        level = "error"
        if isinstance(error, ResetStateError):
            message = f"⚠️ {error}"
            level = "warning"
        elif isinstance(error, AnalysisError):
            message = f"❌ {error}"
        elif error is not None:
            message = f"❌ 未預期錯誤：{error}"  # pragma: no cover - defensive
        self._set_progress_message(_ERROR_MESSAGE, "bold red")
        self.progress_log.write_line(message)
        self._form.show_status(message, level)
        self._cleanup_worker()

    def _handle_cancelled(self) -> None:
        self._form.set_busy(False)
        self._set_progress_message(_CANCELLED_MESSAGE, "bold yellow")
        self.progress_log.write_line("🛑 分析已取消。")
        self._form.show_status("🛑 分析已取消。", "warning")
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        self._analysis_worker = None
        self._cancel_event = None
        self._pending = None

    def action_toggle_language(self) -> None:
        self._language = "en" if self._language == "zh_TW" else "zh_TW"
        message_id = _LANGUAGE_MESSAGE_ZH if self._language == "zh_TW" else _LANGUAGE_MESSAGE_EN
        message = self._translate(message_id)
        self.progress_log.write_line(message)
        self._form.show_status(message)
        self._refresh_progress_message()

    def _translate(self, message_id: str) -> str:
        translator = get_translator(self._language)
        return translator(message_id)

    def _set_progress_message(
        self, message_id: str, style: str, *, suffix: str | None = None
    ) -> None:
        self._progress_message_id = message_id
        self._progress_message_style = style
        self._progress_message_suffix = suffix
        translated = self._translate(message_id)
        suffix_text = suffix or ""
        self.progress_stage.update(Text(f"{translated}{suffix_text}", style=style))

    def _refresh_progress_message(self) -> None:
        if self.progress_stage is None:
            return
        suffix_text = self._progress_message_suffix or ""
        translated = self._translate(self._progress_message_id)
        self.progress_stage.update(
            Text(f"{translated}{suffix_text}", style=self._progress_message_style)
        )


def run_app(*, webview: bool = False, dark: bool | None = None) -> None:
    """Run the Textual TUI, optionally launching through textual-web."""

    # Suppress logging output from attendance_analyzer module to prevent
    # ANSI codes from appearing in the TUI
    logging.basicConfig(level=logging.CRITICAL, format="%(message)s", force=True)

    if webview:
        try:
            import textual_web  # noqa: F401
        except Exception as exc:  # pragma: no cover - optional dependency
            raise SystemExit("textual-web 未安裝或初始化失敗，無法啟動瀏覽器模式。") from exc
        command = [sys.executable, "-m", "tui", "--no-webview"]
        if dark:
            command.append("--dark")
        args = [
            sys.executable,
            "-m",
            "textual_web.cli",
            "app",
            "--run",
            " ".join(command),
            "--web-interface",
        ]
        subprocess.run(args, check=False)
        return

    app = AttendanceAnalyzerApp()
    if dark is not None:
        app.dark = dark
    app.run()

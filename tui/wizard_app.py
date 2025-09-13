from typing import Dict, Any, List
import os

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Button,
    Label,
    DataTable,
    Input,
    Static,
    TextLog,
    DirectoryTree,
)
from textual.reactive import reactive

from .i18n import get_translator
from .adapters import truncate_rows, run_in_thread
from .recent import load_recent_files, add_recent_file
from .logging_bridge import TextualLogHandler
import logging
import threading


_ = get_translator()


class WizardApp(App):
    CSS = """
    Screen {align: center middle}
    #content {width: 80%;}
    #recent {height: 8;}
    """

    BINDINGS = [
        ("enter", "next", "Next"),
        ("escape", "back", "Back"),
        ("r", "run", "Run"),
        ("c", "cancel", "Cancel"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, prefill: Dict[str, Any], auto_close: bool = False) -> None:
        super().__init__()
        self.prefill = prefill
        self.auto_close = auto_close
        self.step = reactive(1)
        self.rows: List[dict] = []
        self.row_styles: List[str] = []
        self.log_sink: List[str] = []
        self._log_handler: TextualLogHandler | None = None
        self._cancel_event = threading.Event()
        self._running = False

    def compose(self) -> ComposeResult:
        with Vertical(id="content"):
            yield Label(_("Welcome"))
            with Horizontal():
                yield Button(_("Back"), id="back")
                yield Button(_("Next"), id="next")
                yield Button(_("Run"), id="run")
                yield Button(_("Cancel"), id="cancel")
                yield Button(_("Quit"), id="quit")
            # Step 1 controls
            with Vertical(id="step1"):
                yield Label(_("File"))
                yield Input(self.prefill.get("filepath", ""), id="filepath")
                yield Label(_("Recent"))
                with Horizontal(id="recent"):
                    for idx, p in enumerate(load_recent_files()):
                        yield Button(
                            os.path.basename(p), id=f"recent-{idx}", variant="primary"
                        )
                # Simple directory tree rooted at CWD
                yield DirectoryTree(os.getcwd(), id="tree")
            with Horizontal():
                yield Static(id="stage")
                yield TextLog(id="log", highlight=False)

    def on_mount(self) -> None:
        # Auto-quit for CI smoke if requested
        if self.auto_close or os.getenv("FHR_TUI_AUTOCLOSE") == "1":
            self.exit()
            return
        self._render_step()

    def on_button_pressed(self, event) -> None:
        bid = event.button.id
        if bid == "next":
            self.action_next()
        elif bid == "back":
            self.action_back()
        elif bid == "run":
            self.action_run()
        elif bid == "cancel":
            self.action_cancel()
        elif bid == "quit":
            self.action_quit()
        elif bid and bid.startswith("recent-"):
            # Set filepath from recent button label
            btn = event.button
            self.query_one("#filepath", Input).value = btn.renderable

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:  # type: ignore
        self.query_one("#filepath", Input).value = event.path

    def action_next(self) -> None:
        if self.step == 1:
            # validate filepath exists
            path = self.query_one("#filepath", Input).value.strip()
            if not path or not os.path.exists(path):
                self._show_error("File not found")
                return
            # clear error and store prefill
            self.prefill["filepath"] = path
            self._clear_error()
        self.step = min(5, self.step + 1)
        self._render_step()

    def action_back(self) -> None:
        self.step = max(1, self.step - 1)
        self._render_step()

    def action_run(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancel_event.clear()
        self._attach_logger()

        # run real analysis in background, then move to preview
        def work():
            try:
                self._do_analysis()
                if not self._cancel_event.is_set():
                    self.call_from_thread(self._go_preview)
            finally:
                self._detach_logger()
                self._running = False

        run_in_thread(work)

    def action_cancel(self) -> None:
        # For now, cancel returns to confirm step
        self.step = 3
        self._render_step()

    def action_quit(self) -> None:
        self.exit()

    def _render_step(self) -> None:
        stage = self.query_one("#stage", Static)
        stage.update("")
        # Toggle step1 controls visibility
        self.query_one("#step1").display = self.step == 1
        if self.step == 1:
            return
        if self.step == 2:
            inc = self.prefill.get("incremental", True)
            full = self.prefill.get("full", False)
            reset = self.prefill.get("reset_state", False)
            stage.update(
                f"{_('Options')}:\n- {_('Incremental')}: {inc}\n- {_('Full Re-Analyze')}: {full}\n- {_('Reset State')}: {reset}"
            )
        elif self.step == 3:
            stage.update(_("Confirm & Run"))
        elif self.step == 4:
            table = DataTable(id="preview")
            table.add_columns("date", "type", "minutes", "desc")
            style_map = {
                "late": "red",
                "ot": "cyan",
                "wfh": "green",
                "leave": "yellow",
                "other": "white",
            }
            self._styles_applied = []
            for idx, r in enumerate(truncate_rows(self.rows, 200)):
                style_name = style_map.get(
                    self.row_styles[idx] if idx < len(self.row_styles) else "other",
                    "white",
                )
                self._styles_applied.append(style_name)
                table.add_row(
                    r.get("date", ""),
                    r.get("type", ""),
                    str(r.get("minutes", 0)),
                    r.get("desc", ""),
                    style=style_name,
                )
            stage.update("")
            stage.mount(table)
        else:
            stage.update(_("Done"))

    def _go_preview(self) -> None:
        self.step = 4
        self._render_step()

    def _attach_logger(self) -> None:
        if self._log_handler is not None:
            return
        self._log_handler = TextualLogHandler(self.log_sink)
        self._log_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        logging.getLogger().addHandler(self._log_handler)
        logging.getLogger().setLevel(logging.INFO)

    def _detach_logger(self) -> None:
        if self._log_handler is not None:
            try:
                logging.getLogger().removeHandler(self._log_handler)
            except Exception:
                pass
            self._log_handler = None

    def _show_error(self, msg: str) -> None:
        stage = self.query_one("#stage", Static)
        stage.update(f"ERROR: {msg}")

    def _clear_error(self) -> None:
        stage = self.query_one("#stage", Static)
        stage.update("")

    def _type_class(self, t: str) -> str:
        t = t.lower()
        if "late" in t or "遲到" in t:
            return "late"
        if "overtime" in t or "加班" in t:
            return "ot"
        if "wfh" in t:
            return "wfh"
        if "leave" in t or "請假" in t:
            return "leave"
        return "other"

    def _do_analysis(self) -> None:
        # Early cancel check
        if self._cancel_event.is_set():
            return
        # Clear previous rows/styles
        self.rows = []
        self.row_styles = []
        # Obtain path
        path = self.prefill.get("filepath") or ""
        fmt = self.prefill.get("format", "excel")
        inc = self.prefill.get("incremental", True) and not self.prefill.get(
            "full", False
        )
        if not path or not os.path.exists(path):
            self.call_from_thread(lambda: self._show_error("File not found"))
            return
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.set_progress_callback(lambda *_: None)
        analyzer.set_cancel_check(lambda: self._cancel_event.is_set())
        logger = logging.getLogger(__name__)
        logger.info("解析檔案...")
        analyzer.parse_attendance_file(path, incremental=inc)
        if self._cancel_event.is_set():
            return
        logger.info("分組記錄...")
        analyzer.group_records_by_day()
        if self._cancel_event.is_set():
            return
        logger.info("分析考勤...")
        analyzer.analyze_attendance()
        if self._cancel_event.is_set():
            return
        # Build preview rows from issues
        preview = []
        styles = []
        for issue in analyzer.issues:
            preview.append(
                {
                    "date": issue.date.strftime("%Y/%m/%d"),
                    "type": (
                        issue.type.value
                        if hasattr(issue.type, "value")
                        else str(issue.type)
                    ),
                    "minutes": issue.duration_minutes,
                    "desc": issue.description,
                }
            )
            styles.append(
                self._type_class(
                    issue.type.value
                    if hasattr(issue.type, "value")
                    else str(issue.type)
                )
            )
        self.rows = preview
        self.row_styles = styles
        # Add to recent list
        add_recent_file(path)


def run_app(prefill: Dict[str, Any]) -> None:
    auto = os.getenv("FHR_TUI_AUTOCLOSE") == "1"
    WizardApp(prefill=prefill, auto_close=auto).run()

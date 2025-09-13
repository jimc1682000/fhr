from typing import Dict, Any, List
import os

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Label, DataTable, Input, Static
from textual.reactive import reactive

from .i18n import get_translator
from .adapters import truncate_rows
from .recent import load_recent_files


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
                yield Label("Recent")
                with Horizontal(id="recent"):
                    for idx, p in enumerate(load_recent_files()):
                        yield Button(os.path.basename(p), id=f"recent-{idx}", variant="primary")
            yield Static(id="stage")

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

    def action_next(self) -> None:
        self.step = min(5, self.step + 1)
        self._render_step()

    def action_back(self) -> None:
        self.step = max(1, self.step - 1)
        self._render_step()

    def action_run(self) -> None:
        self._simulate_run()
        self.step = 4
        self._render_step()

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
        self.query_one("#step1").display = (self.step == 1)
        if self.step == 1:
            return
        if self.step == 2:
            inc = self.prefill.get('incremental', True)
            full = self.prefill.get('full', False)
            reset = self.prefill.get('reset_state', False)
            stage.update(
                f"{_('Options')}:\n- {_('Incremental')}: {inc}\n- {_('Full Re-Analyze')}: {full}\n- {_('Reset State')}: {reset}"
            )
        elif self.step == 3:
            stage.update(_("Confirm & Run"))
        elif self.step == 4:
            table = DataTable(id="preview")
            table.add_columns("date", "type", "minutes", "desc")
            for r in truncate_rows(self.rows, 200):
                table.add_row(
                    r.get('date', ''),
                    r.get('type', ''),
                    str(r.get('minutes', 0)),
                    r.get('desc', ''),
                )
            stage.update("")
            stage.mount(table)
        else:
            stage.update(_("Done"))

    def _simulate_run(self) -> None:
        self.rows = [
            {"date": f"2025/07/{i:02d}", "type": "LATE", "minutes": i, "desc": "mock"}
            for i in range(1, 251)
        ]


def run_app(prefill: Dict[str, Any]) -> None:
    auto = os.getenv("FHR_TUI_AUTOCLOSE") == "1"
    WizardApp(prefill=prefill, auto_close=auto).run()

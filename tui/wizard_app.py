from typing import Dict, Any, List


def run_app(prefill: Dict[str, Any]) -> None:
    """Minimal multi-step wizard shell for Textual.

    Notes
    - Uses Chinese by default; if FHR_LANG is non-zh, shows English labels.
    - Step sequence: Welcome -> Options -> Confirm & Run -> Preview -> Done
    - Preview truncates rows to 200 via adapters.truncate_rows
    - Background run is a stub; integration with analyzer will be added later
    """
    from textual.app import App, ComposeResult
    from textual.containers import Vertical, Horizontal
    from textual.widgets import Button, Label, DataTable, Input, Static
    from textual.reactive import reactive

    from .i18n import get_translator
    from .adapters import truncate_rows

    _ = get_translator()

    class WizardApp(App):
        CSS = """
        Screen {align: center middle}
        #content {width: 80%;}
        """

        step = reactive(1)
        rows: List[dict] = []

        def compose(self) -> ComposeResult:
            with Vertical(id="content"):
                yield Label(_("Welcome"))
                with Horizontal():
                    yield Button(_("Back"), id="back")
                    yield Button(_("Next"), id="next")
                    yield Button(_("Run"), id="run")
                    yield Button(_("Cancel"), id="cancel")
                    yield Button(_("Quit"), id="quit")
                yield Static(id="stage")

        def on_mount(self) -> None:
            self._render_step()

        def on_button_pressed(self, event) -> None:
            bid = event.button.id
            if bid == "next":
                self.step = min(self.step + 1, 5)
            elif bid == "back":
                self.step = max(self.step - 1, 1)
            elif bid == "run":
                self._simulate_run()
                self.step = 4
            elif bid == "cancel":
                self.step = 3
            elif bid == "quit":
                self.exit()
            self._render_step()

        def _render_step(self) -> None:
            stage = self.query_one("#stage", Static)
            stage.update("")
            if self.step == 1:
                stage.update(f"{_("File")}: {prefill.get('filepath','')}\n{_("Format")}: {prefill.get('format','excel')}")
            elif self.step == 2:
                inc = prefill.get('incremental', True)
                full = prefill.get('full', False)
                reset = prefill.get('reset_state', False)
                stage.update(f"{_("Options")}:\n- {_("Incremental")}: {inc}\n- {_("Full Re-Analyze")}: {full}\n- {_("Reset State")}: {reset}")
            elif self.step == 3:
                stage.update(_("Confirm & Run"))
            elif self.step == 4:
                # build preview table
                table = DataTable(id="preview")
                table.add_columns("date", "type", "minutes", "desc")
                for r in truncate_rows(self.rows, 200):
                    table.add_row(r.get('date',''), r.get('type',''), str(r.get('minutes',0)), r.get('desc',''))
                stage.update("")
                stage.mount(table)
            else:
                stage.update(_("Done"))

        def _simulate_run(self) -> None:
            # Produce 250 fake rows
            self.rows = [
                {"date": f"2025/07/{i:02d}", "type": "LATE", "minutes": i, "desc": "mock"}
                for i in range(1, 251)
            ]

    WizardApp().run()


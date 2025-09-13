"""TUI entry for the Textual wizard.

This module exposes `launch_tui(prefill: dict)` and performs import lazily
so non-TUI CLI workflows remain dependency-free.
"""
from typing import Dict, Any


def launch_tui(prefill: Dict[str, Any]) -> None:
    try:
        # Local import to keep optional dependency
        from .wizard_app import run_app
    except Exception as e:  # pragma: no cover - surfaced in CLI for message
        # Re-raise to let CLI show a friendly install hint
        raise

    run_app(prefill)


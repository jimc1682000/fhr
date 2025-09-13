"""TUI entry for the Textual wizard.

This module exposes `launch_tui(prefill: dict)` and performs import lazily
so non-TUI CLI workflows remain dependency-free.
"""

from typing import Dict, Any
import importlib


def launch_tui(prefill: Dict[str, Any]) -> None:
    # Verify dependency early to produce a clear error upstream
    importlib.import_module("textual")  # may raise ImportError
    # Local import to keep optional dependency surface small
    from .wizard_app import run_app

    run_app(prefill)

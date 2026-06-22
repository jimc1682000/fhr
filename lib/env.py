"""Minimal `.env` loader.

We deliberately don't depend on python-dotenv — the format we need is
a strict subset (KEY=VALUE per line, # for comments) and the analyzer
ships with no third-party Python dependencies. This file is loaded
exactly once at startup by callers that need EHR / portal credentials
(e.g. `fhr portal fetch`), and only fills in env vars that aren't
already set so a real environment override always wins.

Security policy: this loader MUST NOT log values. The 104 EHR Portal
flow never stores user passwords (see CLAUDE.md) — the .env only
holds URLs, company info, and Slack user IDs.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_dotenv(start: str | Path | None = None) -> Path | None:
    """Walk upward from `start` (default: CWD) until a `.env` is found
    or the filesystem root is reached. Returns None when none exists."""
    cur = Path(start or os.getcwd()).resolve()
    while True:
        candidate = cur / ".env"
        if candidate.is_file():
            return candidate
        if cur.parent == cur:
            return None
        cur = cur.parent


def _parse_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if "=" not in s:
        return None
    key, _, value = s.partition("=")
    key = key.strip()
    if not key or not key.replace("_", "").isalnum():
        return None
    value = value.strip()
    # Strip surrounding quotes (single or double), but only if balanced.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def load(path: str | Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Parse `path` (or auto-discover) and inject keys into `os.environ`.

    Returns the dict of *applied* (key → value) pairs — keys that were already
    set in the environment are skipped unless `override=True`.

    Silently no-ops if no .env exists, so callers can call this freely at
    startup.
    """
    target = Path(path) if path else find_dotenv()
    applied: dict[str, str] = {}
    if not target or not target.is_file():
        return applied
    with target.open(encoding="utf-8") as f:
        for raw in f:
            kv = _parse_line(raw)
            if not kv:
                continue
            key, value = kv
            if not override and key in os.environ:
                continue
            os.environ[key] = value
            applied[key] = value
    return applied

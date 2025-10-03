"""Recent file persistence helpers shared by CLI/Web/TUI."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import datetime


def _recent_path() -> str:
    env_path = os.getenv("FHR_RECENT_FILE")
    if env_path:
        return env_path
    return os.path.join(os.getcwd(), ".fhr_recent.json")


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _write_json(path: str, data: dict) -> None:
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_recent_files(limit: int = 10, *, include_missing: bool = False) -> list[str]:
    data = _read_json(_recent_path())
    items = data.get("recent", [])
    paths: list[str] = []
    for item in items:
        if isinstance(item, str):
            path = item
        elif isinstance(item, dict):
            path = item.get("path")
        else:
            continue
        if not isinstance(path, str):
            continue
        if os.path.exists(path) or include_missing:
            paths.append(path)
        if len(paths) >= limit:
            break
    return paths


def add_recent_file(path: str, limit: int = 10) -> None:
    if not path:
        return
    store_path = _recent_path()
    data = _read_json(store_path)
    items = data.get("recent", [])
    normalized: list[dict[str, str]] = []
    seen = set()
    timestamp = datetime.now().isoformat()
    # Put new file first
    normalized.append({"path": path, "last_used": timestamp})
    seen.add(path)
    for item in items:
        if isinstance(item, str):
            candidate = item
            last_used = timestamp
        elif isinstance(item, dict):
            candidate = item.get("path")
            last_used = item.get("last_used", timestamp)
        else:
            continue
        if not isinstance(candidate, str) or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append({"path": candidate, "last_used": last_used})
        if len(normalized) >= limit:
            break
    data["recent"] = normalized[:limit]
    try:
        _write_json(store_path, data)
    except Exception:
        # Non-critical: ignore persistence errors
        pass


def clear_recent_files() -> None:
    path = _recent_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def seed_recent_files(paths: Iterable[str], limit: int = 10) -> None:
    """Utility for tests: seed the recent file list with specific paths."""
    store_path = _recent_path()
    entries = []
    timestamp = datetime.now().isoformat()
    for idx, path in enumerate(paths):
        if idx >= limit:
            break
        entries.append({"path": path, "last_used": timestamp})
    data = {"recent": entries}
    try:
        _write_json(store_path, data)
    except Exception:
        pass

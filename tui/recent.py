import json
import os
from typing import List


_RECENT_PATH = os.path.join(os.getcwd(), ".fhr_recent.json")


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_recent_files(limit: int = 10) -> List[str]:
    data = _read_json(_RECENT_PATH)
    items = data.get("recent", [])
    # Keep only existing files for UX cleanliness
    out = [p for p in items if isinstance(p, str) and os.path.exists(p)]
    return out[:limit]


def add_recent_file(path: str, limit: int = 10) -> None:
    if not path:
        return
    data = _read_json(_RECENT_PATH)
    items = data.get("recent", [])
    if path in items:
        items.remove(path)
    items.insert(0, path)
    items = items[:limit]
    data["recent"] = items
    try:
        with open(_RECENT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # Non-fatal; silently ignore file write errors
        pass

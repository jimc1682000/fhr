"""Versioned schema helpers for fhr's interop JSON formats.

Producers stamp every payload with a `schema_version` string. Consumers
call `require_schema_version()` (or `load_payload()`) at the boundary
and bail out with a friendly error if the major version doesn't match.

Schemas live under `docs/schema/` and follow `<name>/v<major>` naming
(e.g. `attendance-analysis/v1`). Adding fields is a minor change and
does not require a bump; renaming or removing fields is a major bump.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_VERSION_RE = re.compile(r"^(?P<name>[a-z][a-z0-9-]*)/v(?P<major>\d+)(?:\.(?P<minor>\d+))?$")


class SchemaVersionError(ValueError):
    """Raised when a payload's schema_version is missing, malformed, or
    incompatible with what the consumer expects."""


def parse_version(version: str) -> tuple[str, int, int]:
    """Parse a `<name>/v<major>[.<minor>]` string into (name, major, minor).

    >>> parse_version("attendance-analysis/v1")
    ('attendance-analysis', 1, 0)
    >>> parse_version("attendance-analysis/v2.3")
    ('attendance-analysis', 2, 3)
    """
    m = _VERSION_RE.match(version or "")
    if not m:
        raise SchemaVersionError(
            f"無法解析 schema_version: {version!r}（預期格式 '<name>/v<major>[.<minor>]'）"
        )
    return m.group("name"), int(m.group("major")), int(m.group("minor") or 0)


def require_schema_version(payload: Any, expected: str) -> None:
    """Verify that `payload['schema_version']` matches `expected`'s major version.

    Raises SchemaVersionError if:
    - `payload` is not a dict
    - `schema_version` field is missing
    - the version's name doesn't match
    - the version's major doesn't match (minor differences are OK — we trust
      additive evolution within a major)
    """
    if not isinstance(payload, dict):
        raise SchemaVersionError(
            f"預期 JSON 物件含 schema_version，實際得到 {type(payload).__name__}"
        )
    actual = payload.get("schema_version")
    if not actual:
        raise SchemaVersionError(f"payload 缺少 schema_version 欄位；預期 {expected!r}")
    exp_name, exp_major, _ = parse_version(expected)
    act_name, act_major, _ = parse_version(str(actual))
    if act_name != exp_name:
        raise SchemaVersionError(f"schema_version 名稱不符：預期 {exp_name!r}，得到 {act_name!r}")
    if act_major != exp_major:
        raise SchemaVersionError(
            f"schema_version {actual!r} 與預期 {expected!r} 的主版本不相容；"
            "請升級對方工具或使用對應版本的 importer/exporter"
        )


def load_payload(path: str | Path, expected: str) -> dict:
    """Load a JSON file and validate its schema_version in one step."""
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        payload = json.load(f)
    require_schema_version(payload, expected)
    return payload


def stamp(payload: dict, version: str) -> dict:
    """Return `payload` with `schema_version` injected (in-place + returned)."""
    payload["schema_version"] = version
    return payload

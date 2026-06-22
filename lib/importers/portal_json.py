"""Import `portal-attendance-snapshot/v1` JSON → fhr 9-column `.txt`.

The snapshot is the JSON shape that an agent-browser `eval` over the
104 EHR Portal "全部刷卡資料" table produces (see
`docs/schema/portal-attendance-snapshot-v1.md`). Once written as
tab-delimited 9-column .txt, the existing `attendance_analyzer.py`
can ingest it without modification.

Column mapping (must include header row):
  0 應刷卡時段      ← record["scheduledTime"]
  1 當日卡鐘資料    ← record["actualTime"] (empty string when absent)
  2 刷卡別          ← record["type"]
  3 卡鐘編號        ← "1"
  4 資料來源        ← "刷卡匯入" if actualTime else ""
  5 異常狀態        ← record["status"]
  6 處理狀態        ← "" (fresh snapshot — never marked 已處理 here)
  7 異常處理作業    ← ""
  8 備註            ← ""
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.schema import load_payload, require_schema_version

SCHEMA_VERSION = "portal-attendance-snapshot/v1"

HEADER_COLUMNS = (
    "應刷卡時段",
    "當日卡鐘資料",
    "刷卡別",
    "卡鐘編號",
    "資料來源",
    "異常狀態",
    "處理狀態",
    "異常處理作業",
    "備註",
)


def records_to_txt_lines(records: list[dict]) -> list[str]:
    """Render a list of snapshot records as 9-column tab-delimited lines.

    Returns lines without trailing newline; caller joins as needed. Header is
    always the first line — fhr's parser filters non-上班/下班 type rows so
    the header gets silently dropped during analysis.
    """
    lines = ["\t".join(HEADER_COLUMNS)]
    for r in records:
        sched = r.get("scheduledTime", "") or ""
        actual = r.get("actualTime", "") or ""
        typ = r.get("type", "") or ""
        status = r.get("status", "") or ""
        source = "刷卡匯入" if actual else ""
        lines.append("\t".join([sched, actual, typ, "1", source, status, "", "", ""]))
    return lines


def import_snapshot(path: str | Path) -> list[dict]:
    """Load + validate a snapshot JSON; returns the `records` list."""
    payload = load_payload(path, SCHEMA_VERSION)
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"snapshot 缺少 records list: {path}")
    return records


def import_from_dict(payload: dict) -> list[dict]:
    """Same as import_snapshot but reads a dict instead of a file."""
    require_schema_version(payload, SCHEMA_VERSION)
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("snapshot 缺少 records list")
    return records


def write_txt(out_path: str | Path, records: list[dict]) -> None:
    """Persist records to a 9-column .txt file (tab-delimited, UTF-8)."""
    Path(out_path).write_text(
        "\n".join(records_to_txt_lines(records)) + "\n",
        encoding="utf-8",
    )


def convert_file(snapshot_path: str | Path, txt_path: str | Path) -> int:
    """Read a snapshot JSON file → write a fhr .txt. Returns record count."""
    records = import_snapshot(snapshot_path)
    write_txt(txt_path, records)
    return len(records)


def snapshot_from_legacy_json(path: str | Path) -> dict:
    """Promote a legacy agent-browser JSON dump (no schema_version) into the
    v1 shape. Useful for one-off conversion of artifacts captured before
    `fhr portal fetch` shipped."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "records" in raw:
        records = raw["records"]
        total_pages = raw.get("totalPages", 1)
        record_count = raw.get("recordCount", len(records))
    elif isinstance(raw, list):
        records = raw
        total_pages = 1
        record_count = len(raw)
    else:
        raise ValueError(f"無法辨識 legacy JSON 結構: {path}")
    return {
        "schema_version": SCHEMA_VERSION,
        "totalPages": total_pages,
        "recordCount": record_count,
        "records": records,
    }

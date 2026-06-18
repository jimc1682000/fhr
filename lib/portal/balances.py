"""Scrape leave-balance tables from the Portal's 請假單 form.

The 請假單 form embeds two side-panel iframes:
  - 假勤項目統計  → 補休 / 事假 / 半薪病假 / 有薪病假 / 公假 / 忘刷 / 異地辦公 / 生日假
  - 特休統計      → 上期結轉 + 本年度 + 已休 + 剩餘 (天 + 小時)

Both render as plain HTML tables — no postback shenanigans needed once
we land on the form. We pull every cell with the same `<iframe>`-walking
JS that the session prototype used and return a normalized dict.

The form list URL is the same Queues page used by `fhr portal-apply`;
we click the 請假單 cell to open the form. agent-browser snapshot refs
can't be used here because clicking the cell requires a real DOM event
that the snapshot ref doesn't expose — we shell out via eval.
"""

from __future__ import annotations

import logging
import re

from lib.portal.client import PortalSession, js_escape

logger = logging.getLogger(__name__)

FORM_QUEUES_URL_PATH = (
    "/eWorkFlow/eWorkFlow_NewRed.asp?URL=~/Workflow_Frontend/Queues/Default.aspx"
)

# Lower-cased numbers like "1 小時" / "0 工作天" parsed into typed pieces.
_RE_HOURS = re.compile(r"^\s*(\d+)\s*小時\s*$")
_RE_DAYS_HOURS = re.compile(r"(\d+)\s*天.*?(\d+)\s*小時")
_RE_DAYS = re.compile(r"^\s*(\d+)\s*天.*$")
_RE_WORKDAYS = re.compile(r"(\d+(?:\.\d+)?)\s*工作天")

# JS: open the 請假單 form by clicking the matching cell.
_OPEN_LEAVE_FORM_JS = """
(function() {
  const cells = document.querySelectorAll('td');
  for (const c of cells) {
    if (c.textContent.trim() === '請假單') { c.click(); return {ok: true}; }
  }
  return {error: 'not found'};
})()
"""

# JS for the items panel ("假勤項目統計"). Returns one row per known cell,
# parsed by Python (cell text varies by leave-class).
_ITEMS_TABLE_JS = """
(function() {
  function findStats(doc) {
    if (doc.body && doc.body.innerText.includes('目前可休時數')) return doc;
    for (const f of doc.querySelectorAll('iframe')) {
      try { const r = findStats(f.contentDocument); if (r) return r; } catch(e) {}
    }
    return null;
  }
  const doc = findStats(document);
  if (!doc) return {error: 'items panel not found'};
  const rows = [];
  doc.querySelectorAll('tr').forEach(tr => {
    const cells = Array.from(tr.querySelectorAll('td')).map(t => t.innerText.trim());
    if (cells.length) rows.push(cells);
  });
  return {rows};
})()
"""

# JS for the 特休統計 panel.
_ANNUAL_TABLE_JS = """
(function() {
  function find(doc) {
    if (doc.body && doc.body.innerText.includes('特休假統計')) return doc;
    for (const f of doc.querySelectorAll('iframe')) {
      try { const r = find(f.contentDocument); if (r) return r; } catch(e) {}
    }
    return null;
  }
  const doc = find(document);
  if (!doc) return {error: '特休統計 panel not found'};
  const rows = [];
  doc.querySelectorAll('tr').forEach(tr => {
    const cells = Array.from(tr.querySelectorAll('td')).map(t => t.innerText.trim());
    if (cells.length) rows.push(cells);
  });
  return {rows};
})()
"""


def _parse_hours(text: str) -> int | None:
    """Coerce "8 小時" / "8h" / "8" into an int. Anything else → None."""
    if not text:
        return None
    m = _RE_HOURS.match(text)
    if m:
        return int(m.group(1))
    try:
        return int(text)
    except ValueError:
        return None


def parse_items_panel(rows: list[list[str]]) -> dict[str, dict]:
    """Convert the items-panel cell matrix into {leave_name: {可休總, 已休, 剩餘}}.

    The Portal wraps the real grid in nested tables, so the rows we get back
    are noisy: a flattened blob row, the four metric labels each on their own
    single-cell row, then the clean grid. The clean grid is:
      header:   [加班, 補休假, 事假..., 異地辦公(8hr一週), 生日假]   # leave names
      +1 可休總時數:  ["", "28 小時", "", ..., "40 小時 / 1 月", ...]
      +2 目前可休時數: [...]                                     # often blank
      +3 已休(加班)時數: ["43 小時", "0 小時", "50 小時", ...]
      +4 剩餘時數:    ["", "28 小時", "", "0 小時", ...]

    We locate the header row dynamically (the row that carries 補休假 as its
    own cell) and read the following metric rows positionally — the Portal
    never attaches the metric label to the data row, so order is the only
    anchor. Columns without a 小時 value (事假/半薪病假 = legal, no cap) stay
    None, which the cascade treats as unlimited.
    """
    # Header = the leave-name row. Its first cell is always 加班 and it
    # carries 補休假 as a standalone cell. The flattened blob row also
    # contains "補休假" (as a substring inside a tab-joined cell) and can be
    # 60+ cells wide, so match on r[0] == "加班" to avoid picking it up.
    h = None
    for i, r in enumerate(rows):
        if r and r[0] == "加班" and "補休假" in r:
            h = i
            break
    if h is None:
        return {}
    headers = rows[h]
    width = len(headers)
    # Metric rows follow the header in fixed order; keep only same-width rows.
    metric_rows = [r for r in rows[h + 1 :] if len(r) == width][:4]
    by_key: dict[str, list[str]] = {}
    for key, r in zip(
        ("total", "current", "used", "remaining"), metric_rows, strict=False
    ):
        by_key[key] = r

    out: dict[str, dict] = {}
    for col, name in enumerate(headers):
        if not name:
            continue
        entry: dict[str, str | int | None] = {}
        for key in ("total", "used", "remaining"):
            r = by_key.get(key)
            raw = r[col] if r and col < len(r) else ""
            if not raw:
                entry[key] = None
                continue
            entry[key] = _parse_hours(raw)
            entry[f"{key}_raw"] = raw
        out[name] = entry
    return out


def parse_annual_panel(rows: list[list[str]]) -> dict | None:
    """Pick the data row out of the 特休統計 panel and emit typed fields.

    Layout per session capture: the leaf data row has 6 cells, in column
    order [上期結轉, 結轉截止日, 本年度, 合計, 已休天數, 剩餘天數]. The
    panel duplicates rows because nested tables — we pick the row that
    contains both a date and a `(N 小時)` clause."""
    data_row = _find_annual_data_row(rows)
    if not data_row:
        return None
    grant = _to_hours(data_row[3] if len(data_row) > 3 else "")
    used = _to_hours(data_row[-2] if len(data_row) >= 2 else "")
    remaining = _to_hours(data_row[-1] if data_row else "")
    if grant is None and remaining is None:
        return None
    return {
        "grant_hours": grant,
        "used_hours": used,
        "remaining_hours": remaining,
    }


def _find_annual_data_row(rows: list[list[str]]) -> list[str] | None:
    """Return the leaf row containing both a date and a paren-hours marker."""
    date_re = re.compile(r"\d{4}/\d{1,2}/\d{1,2}")
    paren_re = re.compile(r"\(\s*\d+\s*小時\s*\)")
    for row in rows:
        if (
            len(row) >= 5
            and any(date_re.search(c) for c in row)
            and any(paren_re.search(c) for c in row)
        ):
            return row
    return None


def _to_hours(cell: str) -> int | None:
    """Coerce cells like '10 天又 1 小時 (81 小時)' / '0 天(0 小時)' / '0 小時'."""
    if not cell:
        return None
    paren = re.search(r"\((\d+)\s*小時\)", cell)
    if paren:
        return int(paren.group(1))
    dh = _RE_DAYS_HOURS.search(cell)
    if dh:
        return int(dh.group(1)) * 8 + int(dh.group(2))
    d = re.search(r"(\d+)\s*天", cell)
    if d:
        return int(d.group(1)) * 8
    h = re.search(r"(\d+)\s*小時", cell)
    if h:
        return int(h.group(1))
    return None


def open_leave_form(portal: PortalSession, base_url: str) -> None:
    """Navigate Queues → click 請假單 cell. Caller must already be logged in."""
    portal.open(f"{base_url}{FORM_QUEUES_URL_PATH}")
    portal.wait(3000)
    result = portal.eval_json(_OPEN_LEAVE_FORM_JS)
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"無法開啟請假單表單: {result!r}")
    portal.wait(3000)


def fetch_balances(portal: PortalSession, base_url: str) -> dict:
    """Open the leave form and read both balance panels."""
    open_leave_form(portal, base_url)

    items_raw = portal.eval_json(_ITEMS_TABLE_JS)
    if not isinstance(items_raw, dict) or "rows" not in items_raw:
        raise RuntimeError(f"無法抓取假勤項目統計: {items_raw!r}")
    items = parse_items_panel(items_raw["rows"])

    annual_raw = portal.eval_json(_ANNUAL_TABLE_JS)
    annual: dict | None = None
    if isinstance(annual_raw, dict) and "rows" in annual_raw:
        annual = parse_annual_panel(annual_raw["rows"])

    return {
        "items": items,
        "annual_leave": annual,
    }


def format_balance_table(balances: dict) -> str:
    """Human-readable summary, used by `fhr portal-balances` CLI."""
    lines = ["假別\t剩餘\t已休\t可休總"]
    for name, info in balances.get("items", {}).items():
        rem = _fmt_cell(info.get("remaining"), info.get("remaining_raw"))
        used = _fmt_cell(info.get("used"), info.get("used_raw"))
        total = _fmt_cell(info.get("total"), info.get("total_raw"))
        lines.append(f"{name}\t{rem}\t{used}\t{total}")
    annual = balances.get("annual_leave")
    if annual:
        rem = annual.get("remaining_hours")
        used = annual.get("used_hours")
        total = annual.get("grant_hours")
        rem_s = f"{rem}h" if rem is not None else "?"
        used_s = f"{used}h" if used is not None else "?"
        total_s = f"{total}h" if total is not None else "?"
        lines.append(f"特休假\t{rem_s}\t{used_s}\t{total_s}")
    return "\n".join(lines)


def _fmt_cell(value, raw) -> str:
    if isinstance(value, int):
        return f"{value}h"
    if raw:
        return raw
    return "—"


def js_escape_export(s: str) -> str:
    """Re-export for downstream modules (apply_forms) to share encoding."""
    return js_escape(s)

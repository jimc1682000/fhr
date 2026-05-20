"""Scrape "全部刷卡資料" from the 104 EHR Portal.

Navigates the personal attendance error page, sets the date range, picks
the "全部刷卡資料" data type, and walks every result page extracting one
row per checkin / checkout record. Returns a `portal-attendance-snapshot/v1`
payload (see `docs/schema/portal-attendance-snapshot-v1.md`).

We do NOT trust snapshot refs across navigations — they go stale. The
JavaScript walks the mainFrame iframe directly. The page-select dropdown
is the only reliable way to flip pages (clicking `<a>` numbers is broken
on the Portal — see `docs/personal-query.md`).

Reused from `code_agent_hr/scripts/personal/fetch_data.py` with light
cleanup (no behavior change in the JS).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from lib.importers.portal_json import (
    SCHEMA_VERSION,
    write_txt,
)
from lib.portal.client import PortalSession

logger = logging.getLogger(__name__)

ATTENDANCE_URL_PATH = "/DEPT/Personal_Atten_Error.asp"

# JS extracted from code_agent_hr/scripts/personal/fetch_data.py — paginates
# the result table inside iframe[name="mainFrame"] and returns one row per
# checkin/checkout. We keep the exact upstream behavior so the shape stays
# stable.
_PAGINATE_AND_EXTRACT_JS = """
(async () => {
  const mainFrame = document.querySelector('iframe[name="mainFrame"]');
  if (!mainFrame || !mainFrame.contentDocument) return {error: 'mainFrame not found'};

  let resultDoc = mainFrame.contentDocument;
  const pageSelect = resultDoc.querySelector('select');
  const totalPages = pageSelect ? pageSelect.options.length : 1;

  const allRecords = [];
  const seenKeys = new Set();

  for (let pageIdx = 0; pageIdx < totalPages; pageIdx++) {
    resultDoc = mainFrame.contentDocument;
    const sel = resultDoc.querySelector('select');

    if (sel && pageIdx > 0) {
      sel.selectedIndex = pageIdx;
      sel.dispatchEvent(new Event('change', {bubbles: true}));
      await new Promise(r => setTimeout(r, 1500));
      resultDoc = mainFrame.contentDocument;
    }

    const rows = resultDoc.querySelectorAll('table tr');
    for (const row of rows) {
      const cells = row.querySelectorAll('td');
      if (cells.length >= 6) {
        const data = Array.from(cells).map(c => c.innerText.trim());
        if (data[0] && /^[0-9]{4}\\/[0-9]{2}\\/[0-9]{2}/.test(data[0])) {
          const key = data[0] + '|' + data[2];
          if (!seenKeys.has(key)) {
            seenKeys.add(key);
            allRecords.push({
              scheduledTime: data[0],
              actualTime: data[1],
              type: data[2],
              status: data[5]
            });
          }
        }
      }
    }
  }

  return {totalPages, recordCount: allRecords.length, records: allRecords};
})()
"""


def _set_query_form(portal: PortalSession, start_year: int, start_month: int,
                    end_year: int, end_month: int) -> None:
    """Populate the date range + data-type dropdowns + click the search button.

    We fetch fresh refs each call because snapshot refs go stale on navigation.
    """
    raw_snapshot = portal._run(["snapshot", "-i"])  # noqa: SLF001 (internal use)
    refs = _extract_form_refs(raw_snapshot)
    if not refs:
        raise RuntimeError(
            "找不到查詢表單欄位 — Portal 頁面結構可能改版,請更新 lib/portal/attendance.py"
        )

    # 起始 / 結束年份
    portal._run(["fill", refs["start_year"], str(start_year)])  # noqa: SLF001
    portal._run(["fill", refs["end_year"], str(end_year)])      # noqa: SLF001
    portal.select_ref(refs["start_month"], str(start_month))
    portal.select_ref(refs["end_month"], str(end_month))
    portal.select_ref(refs["data_type"], "全部刷卡資料")
    portal.click_ref(refs["search"])
    portal.wait(3000)


def _extract_form_refs(snapshot: str) -> dict[str, str]:
    """Resolve the @refN identifiers for the query form fields.

    The page's snapshot lists the cells/inputs in a stable order:
      - textbox (start year), combobox (start month)
      - textbox (end year), combobox (end month)
      - combobox 異常刷卡資料 / 全部刷卡資料
      - combobox 異常狀態
      - link (查詢)

    We scan the lines for the first 4 textbox/combobox pairs after the
    cell that contains "出勤刷卡期間" (the section heading).
    """
    refs: dict[str, str] = {}
    lines = snapshot.splitlines()
    in_section = False
    inputs: list[tuple[str, str]] = []
    for line in lines:
        if "出勤刷卡期間" in line:
            in_section = True
            continue
        if not in_section:
            continue
        # capture textbox / combobox refs
        for kind in ("textbox", "combobox"):
            marker = f"- {kind} ["
            if marker in line and "ref=" in line:
                ref = "@" + line.split("ref=")[1].split("]")[0]
                inputs.append((kind, ref))
                break
        if " link [ref=" in line and "search" not in refs:
            # first link after the form is the 查詢 button
            ref = "@" + line.split("ref=")[1].split("]")[0]
            refs["search"] = ref
            break

    expected = ["textbox", "combobox", "textbox", "combobox", "combobox", "combobox"]
    if len(inputs) < len(expected):
        return {}
    for (got_kind, _), want in zip(inputs[: len(expected)], expected, strict=False):
        if got_kind != want:
            return {}
    refs["start_year"] = inputs[0][1]
    refs["start_month"] = inputs[1][1]
    refs["end_year"] = inputs[2][1]
    refs["end_month"] = inputs[3][1]
    refs["data_type"] = inputs[4][1]
    # inputs[5] is 異常狀態 (請選擇) — we leave it default.
    if "search" not in refs:
        return {}
    return refs


def fetch_snapshot(
    portal: PortalSession,
    base_url: str,
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> dict[str, Any]:
    """Drive the Portal and return a `portal-attendance-snapshot/v1` payload."""
    url = f"{base_url}{ATTENDANCE_URL_PATH}"
    logger.info("📡 正在查詢出勤紀錄 (%d/%02d ~ %d/%02d)...",
                start_year, start_month, end_year, end_month)
    portal.open(url)
    portal.wait(1500)
    _set_query_form(portal, start_year, start_month, end_year, end_month)

    result = portal.eval_json(_PAGINATE_AND_EXTRACT_JS)
    if not isinstance(result, dict) or "records" not in result:
        raise RuntimeError(f"eval 失敗或回傳格式異常: {result!r}")
    if "error" in result:
        raise RuntimeError(f"agent-browser eval 回報錯誤: {result['error']}")

    total_pages = int(result.get("totalPages", 1))
    records = list(result["records"])
    logger.info("✅ 共取得 %d 筆出勤紀錄 (%d 頁)", len(records), total_pages)
    return {
        "schema_version": SCHEMA_VERSION,
        "totalPages": total_pages,
        "recordCount": len(records),
        "records": records,
    }


def fetch_to_txt(
    portal: PortalSession,
    base_url: str,
    out_txt: str,
    *,
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> int:
    """Scrape + write the fhr-native 9-column .txt in one call.

    Returns the record count so callers can log it.
    """
    snapshot = fetch_snapshot(
        portal, base_url,
        start_year=start_year, start_month=start_month,
        end_year=end_year, end_month=end_month,
    )
    write_txt(out_txt, snapshot["records"])
    return len(snapshot["records"])


def _ensure_recent_pause() -> None:  # pragma: no cover (timing only)
    time.sleep(0)  # placeholder for future polite-pause logic

"""Scrape submitted-form tracking ("表單申請追蹤") from the Portal.

The Portal's eWorkFlow Search page lists every form the user has
submitted (加班單 / 請假單 / ...). For dedup we want the actual
work-date range (NOT the form-submission date) which is encoded in
the row's `wsdinfotext` attribute. Per `docs/personal-query.md §3`,
the first page is sufficient when sorted by submission date — recent
records appear first.

For multi-month dedup we still iterate every page (the Portal has its
own 全部 / 已核准 / 未處理 filter). Pagination follows the same
select-dropdown trick as attendance scraping.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from lib.portal.client import PortalSession

logger = logging.getLogger(__name__)

FORM_LIST_URL_PATH = "/eWorkFlow/eWorkFlow_NewRed.asp?URL=~/Workflow_Frontend/Search/Default.aspx"

# Maps each (form-name, JS-side filter-value) pair we care about.
FORM_NAMES = {
    "overtime": "加班單",
    "leave": "請假單",
}

# The page itself parses `wsdinfotext`; we re-derive everything from that
# attribute so we don't depend on column ordering across Portal updates.
#
# Example wsdinfotext content:
#   員工編號：546
#   員工姓名：陳建豪(Jimmy Chen)
#   ...
#   假勤日期：(開始時間 StartDate) 2026/04/17 09:30(結束時間 EndDate) 2026/04/17 18:30
#   可申請假勤項目：異地辦公(8hr一週)
#   合計時數：8 小時
_RE_START = re.compile(r"\(開始時間 StartDate\)\s*(\d{4}/\d{2}/\d{2})\s*(\d{2}:\d{2})")
_RE_END = re.compile(r"\(結束時間 EndDate\)\s*(\d{4}/\d{2}/\d{2})\s*(\d{2}:\d{2})")
_RE_HOURS = re.compile(r"合計時數[：:]\s*(\d+)\s*小時")
_RE_LEAVE_TYPE = re.compile(r"可申請假勤項目[：:]\s*(.+)")
_RE_OT_LOCATION = re.compile(r"加班地點[：:]\s*(.+)")
_RE_REASON = re.compile(r"(加班原因|請假原因)[：:]\s*(.+)")
_RE_STATUS = re.compile(r"(目前狀態|簽核狀態|表單狀態)[：:]\s*(.+)")

# JS that reads ONE page of the form list (and reports totalPages).
# Navigating + parsing 25 pages inside a single eval kept the daemon busy
# long enough to time out / go unresponsive, so the Python side drives the
# pagination instead — one short eval per page. `__PAGE__` is substituted
# with the target page index before each call.
_READ_PAGE_JS = """
(async () => {
  const iframes = document.querySelectorAll('iframe');
  if (iframes.length === 0) return {error: 'No iframe found'};
  const dataFrame = iframes[iframes.length - 1];
  let doc = dataFrame.contentDocument;
  if (!doc) return {error: 'Cannot access iframe contentDocument'};

  const target = __PAGE__;
  const sel = doc.querySelector('select');
  const totalPages = sel ? sel.options.length : 1;

  if (sel && sel.selectedIndex !== target) {
    sel.selectedIndex = target;
    sel.dispatchEvent(new Event('change', {bubbles: true}));
    await new Promise(r => setTimeout(r, 1500));
    doc = dataFrame.contentDocument;
  }

  const rows = Array.from(
    doc.querySelectorAll('tr[id^="tbWorkSheetDataList_"]')
  ).map(r => {
    // Column 4 (index 3) is the 狀態 column, e.g. 「流程結束(完成)」/
    // 「流程結束(駁回)」. wsdinfotext carries the form body but not the
    // approval status, so we read the visible cell instead.
    const cells = Array.from(r.querySelectorAll('td')).map(td => (td.innerText || '').trim());
    return {
      id: r.id || '',
      wsdinfotext: r.getAttribute('wsdinfotext') || '',
      status_cell: cells[3] || '',
    };
  });
  return {totalPages, page: target, rows};
})()
"""


def parse_wsdinfotext(text: str) -> dict | None:
    """Extract the structured fields we care about from a wsdinfotext blob.

    Returns None if no valid start date — the row is malformed or empty."""
    start = _RE_START.search(text or "")
    if not start:
        return None
    end = _RE_END.search(text or "")
    hours = _RE_HOURS.search(text or "")
    leave_type = _RE_LEAVE_TYPE.search(text or "")
    location = _RE_OT_LOCATION.search(text or "")
    reason = _RE_REASON.search(text or "")
    status = _RE_STATUS.search(text or "")

    return {
        "date": start.group(1),  # YYYY/MM/DD
        "start_time": start.group(2).replace(":", ""),  # HHMM
        "end_date": end.group(1) if end else start.group(1),
        "end_time": end.group(2).replace(":", "") if end else "",
        "hours": int(hours.group(1)) if hours else None,
        "leave_type": (leave_type.group(1).strip() if leave_type else None),
        "location": (location.group(1).strip() if location else None),
        "reason": (reason.group(2).strip() if reason else ""),
        "status": (status.group(2).strip() if status else ""),
    }


def _set_form_filter(portal: PortalSession, form_name_zh: str, status_zh: str = "全部") -> None:
    """Set 狀態=<status_zh> + 表單名稱=<form_name_zh> + click 提交.

    `status_zh` accepts any option offered by the Portal's 狀態 dropdown
    (未處理 / 已處理 / 已核准 / 已駁回 / 全部). Defaults to 全部 so the
    sync path mirrors every submitted form."""
    raw = portal._run(["snapshot", "-i"])  # noqa: SLF001
    refs = _extract_filter_refs(raw)
    if not refs:
        raise RuntimeError("找不到 eWorkFlow 查詢表單 refs — Portal 版本可能不相容")
    portal.select_ref(refs["status"], status_zh)
    portal.select_ref(refs["form"], form_name_zh)
    portal.click_ref(refs["submit"])
    portal.wait(3000)


def _extract_filter_refs(snapshot: str) -> dict[str, str]:
    """Locate 狀態/表單名稱/提交 refs on the Search page.

    Heuristic: take the first two visible enabled comboboxes that are
    not the disabled `陳建豪` textbox; the first button labelled 提交
    is the submit."""
    refs: dict[str, str] = {}
    comboboxes: list[str] = []
    for line in snapshot.splitlines():
        if " combobox " in line and "[disabled" not in line and "ref=" in line:
            ref = "@" + line.split("ref=")[1].split("]")[0]
            comboboxes.append(ref)
        if (
            'button "提交"' in line
            and "[disabled" not in line
            and "ref=" in line
            and "submit" not in refs
        ):
            refs["submit"] = "@" + line.split("ref=")[1].split("]")[0]
    if len(comboboxes) < 2 or "submit" not in refs:
        return {}
    refs["status"] = comboboxes[0]
    refs["form"] = comboboxes[1]
    return refs


def fetch_form_entries(
    portal: PortalSession,
    base_url: str,
    form_name_zh: str,
    status_zh: str = "全部",
) -> list[dict]:
    """Return parsed entries for a single form type (e.g. "加班單").

    `status_zh` filters by the Portal's 狀態 dropdown (預設 全部). Pages are
    read one short eval at a time (Python drives pagination) so a long form
    list doesn't tie up the agent-browser daemon."""
    portal.open(f"{base_url}{FORM_LIST_URL_PATH}")
    portal.wait(2500)
    _set_form_filter(portal, form_name_zh, status_zh)

    def _read_page(idx: int) -> dict:
        result = portal.eval_json(_READ_PAGE_JS.replace("__PAGE__", str(idx)))
        if isinstance(result, dict) and "error" in result:
            raise RuntimeError(f"eval 回報錯誤: {result['error']}")
        if not isinstance(result, dict) or "rows" not in result:
            raise RuntimeError(f"eval 失敗或回傳格式異常: {result!r}")
        return result

    entries: list[dict] = []
    seen: set[str] = set()

    first = _read_page(0)
    total_pages = int(first.get("totalPages", 1) or 1)

    def _collect(rows: list[dict]) -> None:
        for row in rows:
            rid = row.get("id", "")
            if rid and rid in seen:
                continue
            if rid:
                seen.add(rid)
            parsed = parse_wsdinfotext(row.get("wsdinfotext", ""))
            if parsed is None:
                continue
            # The visible 狀態 column is the reliable approval status;
            # wsdinfotext rarely carries it. Prefer the cell when present.
            status_cell = row.get("status_cell", "")
            if status_cell:
                parsed["status"] = status_cell
            parsed["row_id"] = rid
            entries.append(parsed)

    _collect(first["rows"])
    for idx in range(1, total_pages):
        _collect(_read_page(idx)["rows"])

    logger.info("✅ %s: %d 筆 (%d 頁)", form_name_zh, len(entries), total_pages)
    return entries


def fetch_all_applied_forms(
    portal: PortalSession,
    base_url: str,
    *,
    kinds: Iterable[str] = ("overtime", "leave"),
    status_zh: str = "全部",
) -> dict[str, list[dict]]:
    """Scrape all requested form kinds. Returns dict keyed by english name.

    `status_zh` filters every kind by the Portal's 狀態 dropdown (預設 全部)."""
    out: dict[str, list[dict]] = {}
    for kind in kinds:
        zh = FORM_NAMES.get(kind)
        if not zh:
            raise ValueError(f"未知的 form kind: {kind!r}")
        out[kind] = fetch_form_entries(portal, base_url, zh, status_zh)
    return out

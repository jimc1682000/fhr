"""Submit 加班單 / 請假單 forms via agent-browser.

Ported from `code_agent_hr/scripts/personal/apply_forms.py` with the
agent-browser session abstracted behind `PortalSession`. All JS payloads
match the original byte-for-byte so the Portal-side behavior is the
same as the version that submitted 28 forms successfully during the
session.

Each `submit_*` returns a status string (see the constants below). A form
only counts as submitted once it shows up with an explicitly recognized active status:
the old snapshot heuristic (`disabled` / 主管簽核 in the page) reported
success even when the Portal silently rejected the form, because the
rejected form page itself contains disabled widgets."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from lib.portal import approvals
from lib.portal.balances import FORM_QUEUES_URL_PATH
from lib.portal.client import AgentBrowserError, PortalSession, js_escape

logger = logging.getLogger(__name__)

# Per-entry outcome. Only CONFIRMED / ALREADY_PENDING mean the form exists on
# the Portal; DRY_RUN counts as done for plan bookkeeping only.
CONFIRMED = "confirmed"  # 送出後在 Portal 有效單據清單查到
ALREADY_PENDING = "already_pending"  # 送出前就已在清單上，未重送
UNCONFIRMED = "unconfirmed"  # 已按送出，但清單查不到；不可直接重送
FAILED = "failed"  # 沒有按送出（假別比對失敗、送出前查不到清單等）
BLOCKED = "blocked"  # 前置條件不符（非 WFH 假單缺職務代理人），未開表單
DRY_RUN = "dry_run"
OK_STATUSES = frozenset({CONFIRMED, ALREADY_PENDING, DRY_RUN})

# 實際清單狀態與既有 Portal 狀態別名；未知狀態不可推定單據有效或失效。
ACTIVE_FORM_STATUSES = frozenset(
    {"未處理", "簽核中", "已核准", "主管簽核 - 一階主管", "流程結束(完成)"}
)
INACTIVE_FORM_STATUSES = frozenset({"已駁回", "退件", "已撤回", "流程結束(駁回)", "流程停止(抽單)"})


class SubmissionInterrupted(AgentBrowserError):
    """送出中斷後的對帳結果，由批次層持久化再停止。"""

    def __init__(self, status: str):
        super().__init__("送出中斷，已嘗試對帳；請先確認結果再重跑")
        self.status = status


def _snap_filename(form_type: str, entry: dict, seq: int) -> str:
    """`<seq:03d>-<form_type>-<date>-<start>-<end>.png` — sortable + readable."""
    date_safe = entry.get("date", "").replace("/", "")
    st = entry.get("start_time", "")
    et = entry.get("end_time", "")
    return f"{seq:03d}-{form_type}-{date_safe}-{st}-{et}.png"


def _take_dry_run_screenshot(
    portal: PortalSession,
    screenshot_dir: Path | None,
    form_type: str,
    entry: dict,
    seq: int,
) -> Path | None:
    if screenshot_dir is None:
        return None
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    path = screenshot_dir / _snap_filename(form_type, entry, seq)
    # Viewport-only (no --full): the Portal renders forms inside small
    # iframes; --full extends the canvas to the entire document height
    # (often 5000+ px of whitespace) while the actual form sits in the
    # top-left corner. Viewport capture matches what the human sees.
    if portal.screenshot(str(path)):
        logger.info("    📸 screenshot: %s", path)
        return path
    logger.warning("    ⚠️  screenshot 失敗")
    return None


def _open_form(portal: PortalSession, base_url: str, form_name_zh: str) -> None:
    """Navigate Queues → click the form name cell."""
    portal.open(f"{base_url}{FORM_QUEUES_URL_PATH}")
    portal.wait(3000)
    escaped = js_escape(form_name_zh)
    result = portal.eval_json(
        f"""
    (function() {{
        const cells = document.querySelectorAll('td');
        for (const c of cells) {{
            if (c.textContent.trim() === '{escaped}') {{
                c.click();
                return {{success: true}};
            }}
        }}
        return {{error: '{escaped} not found'}};
    }})()
    """
    )
    if not isinstance(result, dict) or not result.get("success"):
        raise RuntimeError(f"無法開啟表單 {form_name_zh}: {result!r}")
    portal.wait(3000)


def _fill_datetime(portal: PortalSession, date: str, start_time: str, end_time: str) -> None:
    """Populate StartDate / StartTime / EndDate / EndTime fields via eval."""
    escaped_date = js_escape(date)
    portal.eval_json(
        f"""
    (function() {{
        const sd = document.querySelector('input[name*="StartDate"]');
        const st = document.querySelector('input[name*="StartTime"]');
        const ed = document.querySelector('input[name*="EndDate"]');
        const et = document.querySelector('input[name*="EndTime"]');
        for (const [el, val] of [[sd,'{escaped_date}'], [st,'{start_time}'],
                                 [ed,'{escaped_date}'], [et,'{end_time}']]) {{
            if (!el) continue;
            el.value = val;
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return {{ok: true}};
    }})()
    """
    )
    portal.wait(1000)


def _trigger_hour_calc(portal: PortalSession) -> None:
    """Fire change+blur on every *Time input so the Portal recomputes 合計時數."""
    portal.eval_json(
        """
    document.querySelectorAll('input').forEach(i => {
        if (i.name && i.name.includes('Time')) {
            i.dispatchEvent(new Event('change', {bubbles: true}));
            i.dispatchEvent(new Event('blur', {bubbles: true}));
        }
    });
    """
    )
    portal.wait(2000)


def _click_submit(portal: PortalSession) -> None:
    """Recursively walk every iframe to find and click the 確定送出 button."""
    portal.eval_json(
        """
    (function() {
        function findAndClick(doc) {
            const btns = Array.from(doc.querySelectorAll(
                'button, input[type="button"], input[type="submit"]'));
            const target = btns.find(b =>
                b.textContent.trim() === '確定送出' || b.value === '確定送出');
            if (target) { target.focus(); target.click(); return true; }
            const frames = doc.querySelectorAll('iframe');
            for (const f of frames) {
                try { if (findAndClick(f.contentDocument)) return true; } catch(e) {}
            }
            return false;
        }
        return findAndClick(document);
    })()
    """
    )
    portal.wait(2000)
    portal.dialog_accept()
    portal.wait(1000)
    portal.dialog_accept()
    portal.wait(2000)


def _find_in_portal(portal: PortalSession, base_url: str, form_name_zh: str, entry: dict) -> bool:
    """比對全部狀態，只接受明確有效的單據；未知狀態停止送單。"""
    rows = approvals.fetch_form_entries(portal, base_url, form_name_zh, "全部")

    def key(row):
        return (
            row.get("date"),
            row.get("start_time"),
            row.get("end_date") or row.get("date"),
            row.get("end_time"),
        )

    for row in rows:
        status = row.get("status", "")
        if status in INACTIVE_FORM_STATUSES:
            continue
        if status not in ACTIVE_FORM_STATUSES:
            raise RuntimeError(f"清單出現無法判斷的狀態：{status!r}")
        if key(row) != key(entry):
            continue
        if form_name_zh == "請假單":
            leave_type = row.get("leave_type")
            if not leave_type:
                raise RuntimeError("清單缺少可辨識的假別")
            if leave_type != entry.get("leave_type"):
                continue
        return True
    return False


def _precheck(portal: PortalSession, base_url: str, form_name_zh: str, entry: dict) -> str | None:
    """Stop before submitting when the form already exists or we can't tell.

    Returns ALREADY_PENDING / FAILED to stop, None to go ahead. Not being able
    to read the list is treated as "don't submit" so a retry after a timeout
    can't create a duplicate."""
    try:
        if _find_in_portal(portal, base_url, form_name_zh, entry):
            logger.info("    ⏭  Portal 上已有這張單（含已核准），不重送")
            return ALREADY_PENDING
    except RuntimeError as e:
        logger.error("    ❌ 送出前無法讀取 Portal 清單（%s），為避免重複送出，跳過此單", e)
        return FAILED
    return None


def _confirm(portal: PortalSession, base_url: str, form_name_zh: str, entry: dict) -> str:
    """After clicking 確定送出: CONFIRMED only if the form is on the Portal list."""
    try:
        found = _find_in_portal(portal, base_url, form_name_zh, entry)
    except RuntimeError as e:
        logger.warning("    ⚠️ 送出後無法讀取 Portal 清單：%s", e)
        found = False
    if found:
        logger.info("    ✅ 提交成功（Portal 有效單據清單已查到）")
        return CONFIRMED
    logger.warning(
        "    ⚠️ 已按送出，但 Portal 有效單據清單查不到這張單。"
        "請勿直接重送，先跑 fhr portal-check 或到 Portal 確認"
    )
    return UNCONFIRMED


def _submit_and_confirm(
    portal: PortalSession, base_url: str, form_name_zh: str, entry: dict
) -> str:
    try:
        _click_submit(portal)
    except AgentBrowserError as error:
        status = _confirm(portal, base_url, form_name_zh, entry)
        raise SubmissionInterrupted(status) from error
    return _confirm(portal, base_url, form_name_zh, entry)


def submit_overtime(
    portal: PortalSession,
    base_url: str,
    entry: dict,
    reason: str,
    *,
    dry_run: bool = False,
    dry_run_pause_secs: int = 5,
    screenshot_dir: Path | None = None,
    screenshot_seq: int = 0,
) -> str:
    """Open 加班單 and submit one entry. Returns one of the status constants.

    When `dry_run=True`, fill every field but skip the final 確定送出 click
    and the Portal list checks. The form is left on screen for the
    configured pause so the user can eyeball the values. Returns DRY_RUN so
    the caller treats the entry as "completed for this run", but nothing is
    written to Portal and no `applied_forms` cache mutation should happen.
    """
    date = entry["date"]
    start = entry["start_time"]
    end = entry["end_time"]
    logger.info(
        "📝 加班單%s: %s %s:%s-%s:%s (%dh)",
        " [DRY RUN]" if dry_run else "",
        date,
        start[:2],
        start[2:],
        end[:2],
        end[2:],
        entry.get("hours", 0),
    )
    if not dry_run and (stop := _precheck(portal, base_url, "加班單", entry)):
        return stop

    _open_form(portal, base_url, "加班單")
    _fill_datetime(portal, date, start, end)

    location = js_escape(entry.get("location", "在辦公室"))
    portal.eval_json(
        f"""
    (function() {{
        const selects = document.querySelectorAll('select');
        for (const sel of selects) {{
            const opts = Array.from(sel.options).map(o => o.textContent);
            if (opts.includes('在辦公室') || opts.includes('在外地')) {{
                for (const opt of sel.options) {{
                    if (opt.textContent.includes('{location}')) {{
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        break;
                    }}
                }}
                break;
            }}
        }}
        return true;
    }})()
    """
    )
    portal.wait(1000)

    escaped_reason = js_escape(reason)
    portal.eval_json(
        f"""
    (function() {{
        const tb = document.getElementById('OVERTIME_REASON_TextBox1');
        if (tb) {{
            tb.value = '{escaped_reason}';
            tb.dispatchEvent(new Event('input', {{bubbles: true}}));
            tb.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return true;
    }})()
    """
    )
    portal.wait(1000)
    _trigger_hour_calc(portal)
    if dry_run:
        _take_dry_run_screenshot(portal, screenshot_dir, "overtime", entry, screenshot_seq)
        logger.info(
            "    ✋ DRY RUN: 表單已填寫完成,請瀏覽器手動檢查 (%ds)...",
            dry_run_pause_secs,
        )
        portal.wait(dry_run_pause_secs * 1000)
        return DRY_RUN
    return _submit_and_confirm(portal, base_url, "加班單", entry)


def _select_leave_type(portal: PortalSession, leave_type_name: str) -> str:
    """依完全相同優先、子字串次之選取唯一假別，回傳實際全名。"""
    escaped_leave = js_escape(leave_type_name)
    match = portal.eval_json(
        f"""
    (function() {{
        const sel = document.getElementById('LEAVE_CLASS_DropDownList1');
        if (!sel) return {{error: 'select not found', matched: 0}};
        const name = '{escaped_leave}';
        const exact = [], partial = [];
        for (let i = 0; i < sel.options.length; i++) {{
            const text = sel.options[i].text;
            if (text === name) exact.push({{index: i, text: text}});
            else if (text.includes(name)) partial.push({{index: i, text: text}});
        }}
        const matches = exact.length > 0 ? exact : partial;
        if (matches.length === 1) {{
            sel.selectedIndex = matches[0].index;
            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return {{matched: matches.length, matches: matches}};
    }})()
    """
    )
    matches = match.get("matches") if isinstance(match, dict) else None
    if not isinstance(matches, list) or len(matches) != 1 or match.get("matched") != 1:
        raise RuntimeError(f"假別 {leave_type_name} 無法匹配唯一選項")
    name = matches[0].get("text") if isinstance(matches[0], dict) else None
    if not isinstance(name, str) or not name:
        raise RuntimeError("假別選項缺少名稱")
    return name


def submit_leave(
    portal: PortalSession,
    base_url: str,
    entry: dict,
    leave_type_name: str,
    reason: str,
    proxy_employee: str | None = None,
    *,
    dry_run: bool = False,
    dry_run_pause_secs: int = 5,
    screenshot_dir: Path | None = None,
    screenshot_seq: int = 0,
) -> str:
    """Open 請假單 and submit one entry. Returns one of the status constants.

    WFH-type leaves (異地辦公 / WFH) skip the proxy field per company policy.
    Any other leave type needs a proxy: without one the Portal silently drops
    the form, so we return BLOCKED before opening it (dry runs included).

    `dry_run=True` behaves the same way as for `submit_overtime`: fills the
    form fully and leaves it on screen for `dry_run_pause_secs`, without
    clicking 確定送出. Returns DRY_RUN so the run treats the entry as done.
    """
    date = entry["date"]
    start = entry["start_time"]
    end = entry["end_time"]
    logger.info(
        "📝 請假單%s: %s %s:%s-%s:%s (%dh) [%s]",
        " [DRY RUN]" if dry_run else "",
        date,
        start[:2],
        start[2:],
        end[:2],
        end[2:],
        entry.get("hours", 0),
        leave_type_name,
    )

    entry = {**entry, "leave_type": leave_type_name}
    is_wfh = "異地辦公" in leave_type_name
    if not is_wfh and not proxy_employee:
        logger.error("    ❌ 非 WFH 假單必須指定職務代理人（--proxy），否則 Portal 會靜默擋下")
        return BLOCKED
    if not dry_run:
        # 預查會離開表單；先解析全名，確認沒有既有單後再開表單填寫。
        _open_form(portal, base_url, "請假單")
        try:
            leave_type_name = _select_leave_type(portal, leave_type_name)
        except RuntimeError as error:
            logger.error("    ❌ %s，跳過此單", error)
            return FAILED
        entry = {**entry, "leave_type": leave_type_name}
        if stop := _precheck(portal, base_url, "請假單", entry):
            return stop

    _open_form(portal, base_url, "請假單")

    if not is_wfh and proxy_employee:
        escaped_proxy = js_escape(proxy_employee)
        portal.eval_json(
            f"""
        (function() {{
            const sel = document.getElementById('AGENT_ID_ddlDelegate');
            if (sel) {{
                for (let i = 0; i < sel.options.length; i++) {{
                    if (sel.options[i].text.includes('{escaped_proxy}')) {{
                        sel.selectedIndex = i;
                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                        break;
                    }}
                }}
            }}
            return true;
        }})()
        """
        )
        portal.wait(1000)

    try:
        selected = _select_leave_type(portal, leave_type_name)
    except RuntimeError as error:
        logger.error("    ❌ %s，跳過此單", error)
        return FAILED
    if selected != entry["leave_type"] and not dry_run:
        logger.error("    ❌ 假別選項已變更，跳過此單")
        return FAILED
    entry = {**entry, "leave_type": selected}
    portal.wait(3000)

    _fill_datetime(portal, date, start, end)
    _trigger_hour_calc(portal)

    escaped_reason = js_escape(reason)
    portal.eval_json(
        f"""
    (function() {{
        let field = document.querySelector('textarea[id*="REASON"], input[id*="REASON"]');
        if (!field) {{
            const sel = (
                'textarea:not([disabled]):not([readonly]),' +
                ' input[type="text"]:not([disabled]):not([readonly])'
            );
            const all = document.querySelectorAll(sel);
            if (all.length > 0) field = all[all.length - 1];
        }}
        if (field) {{
            field.value = '{escaped_reason}';
            field.dispatchEvent(new Event('input', {{bubbles: true}}));
            field.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return true;
    }})()
    """
    )
    portal.wait(1000)
    if dry_run:
        _take_dry_run_screenshot(portal, screenshot_dir, "leave", entry, screenshot_seq)
        logger.info(
            "    ✋ DRY RUN: 表單已填寫完成,請瀏覽器手動檢查 (%ds)...",
            dry_run_pause_secs,
        )
        portal.wait(dry_run_pause_secs * 1000)
        return DRY_RUN
    return _submit_and_confirm(portal, base_url, "請假單", entry)


def batch_submit(
    portal: PortalSession,
    base_url: str,
    overtime_plan: Iterable[dict],
    leave_plan: Iterable[dict],
    *,
    on_overtime_done=None,
    on_leave_done=None,
    dry_run: bool = False,
    dry_run_pause_secs: int = 5,
    screenshot_dir: Path | None = None,
) -> tuple[int, int, int, int]:
    """Submit every plan entry. Callbacks fire after each submission with
    `(plan, status)` so the caller can persist progress (`fhr portal-apply`
    writes a result file). The ok counts include OK_STATUSES only.

    `dry_run=True` propagates to every submit_*() call: forms are opened and
    filled but never actually submitted. Callers should NOT update their
    state cache from these "successes".

    Returns (ot_ok, ot_total, lv_ok, lv_total).
    """
    ot_total = ot_ok = 0
    for plan in overtime_plan:
        if plan.get("action") != "submit":
            continue
        ot_total += 1
        try:
            status = submit_overtime(
                portal,
                base_url,
                plan["entry"],
                plan["reason"],
                dry_run=dry_run,
                dry_run_pause_secs=dry_run_pause_secs,
                screenshot_dir=screenshot_dir,
                screenshot_seq=ot_total,
            )
        except SubmissionInterrupted as error:
            if on_overtime_done:
                on_overtime_done(plan, error.status)
            raise
        if status in OK_STATUSES:
            ot_ok += 1
        if on_overtime_done:
            on_overtime_done(plan, status)

    lv_total = lv_ok = 0
    for plan in leave_plan:
        if plan.get("action") != "submit":
            continue
        lv_total += 1
        try:
            status = submit_leave(
                portal,
                base_url,
                plan["entry"],
                plan["leave_type"],
                plan["reason"],
                plan.get("proxy"),
                dry_run=dry_run,
                dry_run_pause_secs=dry_run_pause_secs,
                screenshot_dir=screenshot_dir,
                screenshot_seq=ot_total + lv_total,
            )
        except SubmissionInterrupted as error:
            if on_leave_done:
                on_leave_done(plan, error.status)
            raise
        if status in OK_STATUSES:
            lv_ok += 1
        if on_leave_done:
            on_leave_done(plan, status)

    return ot_ok, ot_total, lv_ok, lv_total

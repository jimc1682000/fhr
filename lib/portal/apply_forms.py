"""Submit 加班單 / 請假單 forms via agent-browser.

Ported from `code_agent_hr/scripts/personal/apply_forms.py` with the
agent-browser session abstracted behind `PortalSession`. All JS payloads
match the original byte-for-byte so the Portal-side behavior is the
same as the version that submitted 28 forms successfully during the
session.

Each `submit_*` returns True / False — the Portal doesn't expose a clean
post-submit confirmation other than the form becoming `disabled` + a
form ID showing up in the snapshot, so we use the same heuristic from
the original implementation."""
from __future__ import annotations

import logging
from collections.abc import Iterable

from lib.portal.balances import FORM_QUEUES_URL_PATH
from lib.portal.client import PortalSession, js_escape

logger = logging.getLogger(__name__)


def _open_form(portal: PortalSession, base_url: str, form_name_zh: str) -> None:
    """Navigate Queues → click the form name cell."""
    portal.open(f"{base_url}{FORM_QUEUES_URL_PATH}")
    portal.wait(3000)
    escaped = js_escape(form_name_zh)
    result = portal.eval_json(f"""
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
    """)
    if not isinstance(result, dict) or not result.get("success"):
        raise RuntimeError(f"無法開啟表單 {form_name_zh}: {result!r}")
    portal.wait(3000)


def _fill_datetime(portal: PortalSession, date: str, start_time: str, end_time: str) -> None:
    """Populate StartDate / StartTime / EndDate / EndTime fields via eval."""
    escaped_date = js_escape(date)
    portal.eval_json(f"""
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
    """)
    portal.wait(1000)


def _trigger_hour_calc(portal: PortalSession) -> None:
    """Fire change+blur on every *Time input so the Portal recomputes 合計時數."""
    portal.eval_json("""
    document.querySelectorAll('input').forEach(i => {
        if (i.name && i.name.includes('Time')) {
            i.dispatchEvent(new Event('change', {bubbles: true}));
            i.dispatchEvent(new Event('blur', {bubbles: true}));
        }
    });
    """)
    portal.wait(2000)


def _click_submit(portal: PortalSession) -> None:
    """Recursively walk every iframe to find and click the 確定送出 button."""
    portal.eval_json("""
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
    """)
    portal.wait(2000)
    portal.dialog_accept()
    portal.wait(1000)
    portal.dialog_accept()
    portal.wait(2000)


def _verify_submission(portal: PortalSession, form_name_zh: str) -> bool:
    """Heuristic: after submit, the form is disabled or a 主管簽核 panel appears."""
    snap = portal._run(["snapshot"])  # noqa: SLF001
    if not snap:
        return False
    return form_name_zh in snap and ("主管簽核" in snap or "disabled" in snap.lower())


def submit_overtime(
    portal: PortalSession,
    base_url: str,
    entry: dict,
    reason: str,
    *,
    dry_run: bool = False,
    dry_run_pause_secs: int = 5,
) -> bool:
    """Open 加班單 and submit one entry. Returns True on confirmed success.

    When `dry_run=True`, fill every field but skip the final 確定送出 click
    and the post-submit verification. The form is left on screen for the
    configured pause so the user can eyeball the values. Returns True so the
    caller treats the entry as "completed for this run", but nothing is
    written to Portal and no `applied_forms` cache mutation should happen.
    """
    date = entry["date"]
    start = entry["start_time"]
    end = entry["end_time"]
    logger.info("📝 加班單%s: %s %s:%s-%s:%s (%dh)",
                " [DRY RUN]" if dry_run else "",
                date, start[:2], start[2:], end[:2], end[2:], entry.get("hours", 0))

    _open_form(portal, base_url, "加班單")
    _fill_datetime(portal, date, start, end)

    location = js_escape(entry.get("location", "在辦公室"))
    portal.eval_json(f"""
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
    """)
    portal.wait(1000)

    escaped_reason = js_escape(reason)
    portal.eval_json(f"""
    (function() {{
        const tb = document.getElementById('OVERTIME_REASON_TextBox1');
        if (tb) {{
            tb.value = '{escaped_reason}';
            tb.dispatchEvent(new Event('input', {{bubbles: true}}));
            tb.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        return true;
    }})()
    """)
    portal.wait(1000)
    _trigger_hour_calc(portal)
    if dry_run:
        logger.info("    ✋ DRY RUN: 表單已填寫完成,請瀏覽器手動檢查 (%ds)...",
                    dry_run_pause_secs)
        portal.wait(dry_run_pause_secs * 1000)
        return True
    _click_submit(portal)
    ok = _verify_submission(portal, "加班單")
    logger.info("    %s", "✅ 提交成功" if ok else "⚠️ 提交結果不確定，請手動確認")
    return ok


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
) -> bool:
    """Open 請假單 and submit one entry. Returns True on confirmed success.

    WFH-type leaves (異地辦公 / WFH) skip the proxy field per company policy.

    `dry_run=True` behaves the same way as for `submit_overtime`: fills the
    form fully and leaves it on screen for `dry_run_pause_secs`, without
    clicking 確定送出. Returns True so the run treats the entry as done.
    """
    date = entry["date"]
    start = entry["start_time"]
    end = entry["end_time"]
    logger.info("📝 請假單%s: %s %s:%s-%s:%s (%dh) [%s]",
                " [DRY RUN]" if dry_run else "",
                date, start[:2], start[2:], end[:2], end[2:],
                entry.get("hours", 0), leave_type_name)

    _open_form(portal, base_url, "請假單")

    is_wfh = "異地辦公" in leave_type_name
    if not is_wfh and proxy_employee:
        escaped_proxy = js_escape(proxy_employee)
        portal.eval_json(f"""
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
        """)
        portal.wait(1000)

    escaped_leave = js_escape(leave_type_name)
    match = portal.eval_json(f"""
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
    """)
    if isinstance(match, dict):
        matched = match.get("matched", 0)
        if matched == 0:
            logger.error("    ❌ 找不到假別 %s，跳過此單", leave_type_name)
            return False
        if matched > 1:
            options = [m.get("text") for m in match.get("matches", [])]
            logger.error("    ❌ 假別 %s 匹配多個 %s，跳過此單", leave_type_name, options)
            return False
    portal.wait(3000)

    _fill_datetime(portal, date, start, end)
    _trigger_hour_calc(portal)

    escaped_reason = js_escape(reason)
    portal.eval_json(f"""
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
    """)
    portal.wait(1000)
    if dry_run:
        logger.info("    ✋ DRY RUN: 表單已填寫完成,請瀏覽器手動檢查 (%ds)...",
                    dry_run_pause_secs)
        portal.wait(dry_run_pause_secs * 1000)
        return True
    _click_submit(portal)
    ok = _verify_submission(portal, "請假單")
    logger.info("    %s", "✅ 提交成功" if ok else "⚠️ 提交結果不確定，請手動確認")
    return ok


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
) -> tuple[int, int, int, int]:
    """Submit every plan entry. Callbacks fire after each submission so the
    caller can persist progress (`fhr portal-apply` writes a result file).

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
        ok = submit_overtime(portal, base_url, plan["entry"], plan["reason"],
                             dry_run=dry_run, dry_run_pause_secs=dry_run_pause_secs)
        if ok:
            ot_ok += 1
        if on_overtime_done:
            on_overtime_done(plan, ok)

    lv_total = lv_ok = 0
    for plan in leave_plan:
        if plan.get("action") != "submit":
            continue
        lv_total += 1
        ok = submit_leave(
            portal, base_url, plan["entry"],
            plan["leave_type"], plan["reason"],
            plan.get("proxy"),
            dry_run=dry_run, dry_run_pause_secs=dry_run_pause_secs,
        )
        if ok:
            lv_ok += 1
        if on_leave_done:
            on_leave_done(plan, ok)

    return ot_ok, ot_total, lv_ok, lv_total

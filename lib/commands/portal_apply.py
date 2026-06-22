"""`fhr portal-apply` — interactive submission of overtime / leave forms.

3 phases (matches code_agent_hr's apply_forms.py contract):
  1. Decision-gathering — read analysis JSON, ask the user per entry,
     persist each answer to a plan file so Ctrl+C can resume.
  2. Confirmation summary.
  3. Batch submission — open Portal once, submit each form, persist
     per-entry result.

Adds compared to the legacy tool:
  - Reads the v1 attendance-analysis schema (`fhr export` output)
  - Auto pre-fetches balances + cascade allocation so the prompt
    default is informed by the user's real remaining hours
  - Skips entries already in `state.applied_forms` (Portal-mirrored)
  - Displays actual punch times next to every entry
  - Annotates overtime entries when the user arrived early
    (expected checkout shifts before 18:30)
  - Triggers `portal-sync` automatically when the cache is stale
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from lib.schema import require_schema_version


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "portal-apply",
        aliases=["portal_apply"],
        help="互動式 / 自動批次送加班 + 請假單",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 互動模式 (推薦),用 cascade + 餘額預先帶入建議
  fhr portal-apply --user JimmyChen --input tmp/analysis.json --proxy 賴菁甫

  # 自動模式,完全跟著 cascade 配置
  fhr portal-apply --user JimmyChen --input tmp/analysis.json --auto

依賴:
  - analysis.json 來自 `fhr export --to=code-agent-hr`
  - attendance .txt 用於顯示實際打卡時間 (auto-detected)
  - state cache 用於跳過已申請的條目 (auto-syncs if older than --sync-max-age)
        """,
    )
    parser.add_argument("--user", required=True, help="state cache 使用者")
    parser.add_argument("--input", required=True, help="analysis-v1 JSON 路徑")
    parser.add_argument("--attendance", help="出勤 .txt (用於顯示打卡時間;預設 auto-detect)")
    parser.add_argument("--proxy", help="非 WFH 請假的職務代理人")
    parser.add_argument(
        "--auto", action="store_true", help="自動模式,完全用 cascade 結果送單 (不互動)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help=(
            "演習模式:開表單 + 填日期/時間/假別/原因/代理人/位置,"
            "但跳過『確定送出』按鈕 + 不寫 applied_forms cache。"
            "適合 E2E 驗證流程。"
        ),
    )
    parser.add_argument(
        "--dry-run-pause-secs",
        type=int,
        default=5,
        help="dry-run 時每筆表單填完後停留秒數 (預設 5)",
    )
    parser.add_argument(
        "--screenshot-dir",
        dest="screenshot_dir",
        help=(
            "把 dry-run 期間每張表單填好後的截圖存到此目錄。"
            "預設 dry-run 時自動寫到 tmp/dry-run-screenshots/<timestamp>/。"
            "傳空字串 (--screenshot-dir '') 可顯式停用。"
        ),
    )
    parser.add_argument("--overtime-only", action="store_true", help="只送加班單")
    parser.add_argument("--leave-only", action="store_true", help="只送請假單")
    parser.add_argument("--base-url", help="EHR base URL (預設讀 env EHR_URL)")
    parser.add_argument("--session", help="agent-browser session 名稱")
    parser.add_argument(
        "--no-sync", action="store_true", help="跳過 portal-sync (信任現有 state cache)"
    )
    parser.add_argument(
        "--sync-max-age-hours",
        type=int,
        default=4,
        help="若 last_full_sync 早於此時數就先 sync (預設 4)",
    )
    parser.add_argument("--debug", action="store_true", help="啟用 debug 日誌")
    return parser


# ---------- analysis-v1 + attendance helpers ----------


def _load_analysis(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    require_schema_version(payload, "attendance-analysis/v1")
    return payload


def _resolve_base_url(args: argparse.Namespace) -> str:
    if args.base_url:
        return args.base_url.rstrip("/")
    raw = os.environ.get("EHR_URL", "").rstrip("/")
    if not raw:
        raise RuntimeError("找不到 EHR_URL — 請在 .env 設定 `EHR_URL=...` 或傳 --base-url")
    for suffix in ("/LoginFOrginal.asp", "/LoginFOpen.asp"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return raw


def _load_attendance_map(attendance_path: str | None) -> dict[str, dict[str, str]]:
    """Return {YYYY/MM/DD: {"上班": HH:MM, "下班": HH:MM}}."""
    out: dict[str, dict[str, str]] = {}
    if not attendance_path:
        return out
    p = Path(attendance_path)
    if not p.is_file():
        return out
    with p.open(encoding="utf-8") as f:
        for line in f:
            cells = line.rstrip("\n").split("\t")
            if len(cells) < 3:
                continue
            sched = cells[0]
            if " " not in sched:
                continue
            date = sched.split()[0]
            typ = cells[2]
            if typ not in ("上班", "下班"):
                continue
            actual = cells[1]
            time_only = actual.split()[-1] if " " in actual else (actual or "—")
            out.setdefault(date, {})[typ] = time_only
    return out


def _auto_detect_attendance(analysis_path: str) -> str | None:
    """Best-effort find of the 9-col .txt next to the analysis file."""
    p = Path(analysis_path).parent
    for f in sorted(p.glob("*-出勤資料.txt")):
        return str(f)
    return None


def _is_early_arrival(
    date: str, schedule_start: str, latest_checkin: str, attendance: dict
) -> tuple[bool, int]:
    """True if the user clocked in BEFORE latest_checkin on `date`. Also
    returns the delta minutes vs schedule_start (positive → early)."""
    rec = attendance.get(date)
    if not rec or "上班" not in rec or rec["上班"] in ("—", ""):
        return False, 0
    actual = rec["上班"]
    if ":" not in actual:
        return False, 0
    ah, am = (int(x) for x in actual.split(":")[:2])
    lh, lm = (int(x) for x in latest_checkin.split(":"))
    sh, sm = (int(x) for x in schedule_start.split(":"))
    if (ah, am) >= (lh, lm):
        return False, 0
    delta = (sh * 60 + sm) - (ah * 60 + am)
    return True, delta


# ---------- entry display ----------


def _fmt_time(hhmm: str) -> str:
    return f"{hhmm[:2]}:{hhmm[2:]}"


def _format_entry(
    entry: dict,
    attendance: dict,
    *,
    schedule_start: str,
    latest_checkin: str,
    expected_checkout: str | None = None,
) -> str:
    st = entry["start_time"]
    et = entry["end_time"]
    base = f"{entry['date']} {_fmt_time(st)}-{_fmt_time(et)} ({entry['hours']}h)"
    rec = attendance.get(entry["date"])
    if rec:
        base += f"  | 實際 上班 {rec.get('上班', '—')}  下班 {rec.get('下班', '—')}"
    if expected_checkout:
        base += f"\n  💡 早到 → 預期下班 {expected_checkout}"
    return base


# ---------- plan / result persistence ----------


def _plan_path(input_path: str) -> Path:
    base = Path(input_path)
    return base.with_name(base.stem.replace("analysis", "apply_plan") + ".json")


def _result_path(input_path: str) -> Path:
    base = Path(input_path)
    return base.with_name(base.stem.replace("analysis", "apply_result") + ".json")


def _entry_key(entry: dict, form_type: str) -> str:
    return f"{form_type}|{entry['date']}|{entry['start_time']}|{entry['end_time']}"


def _load_plan(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    out = {}
    for form_type in ("overtime", "leave"):
        for item in data.get(form_type, []):
            out[item["key"]] = item
    return out


def _save_plan(path: Path, plan: dict[str, list[dict]]) -> None:
    data = {"overtime": [], "leave": []}
    for form_type in ("overtime", "leave"):
        for p in plan[form_type]:
            data[form_type].append({k: v for k, v in p.items() if k != "entry"})
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_completed(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        results = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    out: set[str] = set()
    for form_type in ("overtime", "leave"):
        for r in results.get(form_type, []):
            # Dry-run records show `submitted: true` for plan-bookkeeping
            # only — Portal-side nothing happened, so they MUST NOT count
            # as completed for future runs.
            if r.get("dry_run"):
                continue
            if r.get("submitted") and r.get("entry"):
                out.add(_entry_key(r["entry"], form_type))
    return out


def _save_results(path: Path, results: dict) -> None:
    path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


# ---------- dedup against state cache ----------


def _portal_dedup(state_manager, user: str, entry: dict, form_type: str) -> bool:
    if not state_manager:
        return False
    return state_manager.is_form_already_applied(user, form_type, entry)


# ---------- main interactive flow ----------


def _maybe_sync(args: argparse.Namespace, base_url: str, logger) -> None:
    """If state cache is stale or --no-sync is unset, run portal-sync first."""
    if args.no_sync:
        return
    from lib.state import AttendanceStateManager

    sm = AttendanceStateManager(read_only=False)
    last = sm.get_applied_forms(args.user).get("last_full_sync", "")
    age_hours = None
    if last:
        try:
            t = datetime.fromisoformat(last)
            age_hours = (datetime.now() - t).total_seconds() / 3600
        except ValueError:
            age_hours = None
    if age_hours is None or age_hours > args.sync_max_age_hours:
        logger.info(
            "ℹ️ state cache 已老 (%.1fh) — 先跑 portal-sync",
            age_hours if age_hours is not None else float("inf"),
        )
        from lib.portal import approvals
        from lib.portal.client import PortalSession, ensure_login

        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            entries = approvals.fetch_all_applied_forms(portal, base_url)
        sm.replace_applied_forms(
            args.user,
            entries,
            datetime.now().isoformat(timespec="seconds"),
        )
        sm.save_state()


def _should_fetch_balances(leave: list[dict], no_sync: bool) -> bool:
    """Live balance retrieval is independent from portal-sync cache refresh."""
    return bool(leave)


def _interactive_overtime(
    *,
    overtime: list[dict],
    attendance: dict,
    completed: set[str],
    schedule_start: str,
    latest_checkin: str,
    saved_plan: dict,
    plan: dict,
    plan_path: Path,
    logger,
) -> None:
    if not overtime:
        return
    logger.info("\n%s\n加班單 (%d 筆) — 蒐集決策中\n%s", "=" * 50, len(overtime), "=" * 50)
    for i, entry in enumerate(overtime, 1):
        key = _entry_key(entry, "overtime")
        if key in completed:
            logger.info(
                "[%d/%d] %s ✅ 已申請,略過",
                i,
                len(overtime),
                _format_entry(
                    entry,
                    attendance,
                    schedule_start=schedule_start,
                    latest_checkin=latest_checkin,
                ),
            )
            plan["overtime"].append({"entry": entry, "action": "skip", "already_done": True})
            continue
        if key in saved_plan:
            d = saved_plan[key]
            plan["overtime"].append({**d, "entry": entry})
            logger.info(
                "[%d/%d] %s ↩️  沿用 (%s)",
                i,
                len(overtime),
                _format_entry(
                    entry,
                    attendance,
                    schedule_start=schedule_start,
                    latest_checkin=latest_checkin,
                ),
                d.get("action"),
            )
            continue

        early, delta = _is_early_arrival(entry["date"], schedule_start, latest_checkin, attendance)
        early_hint = None
        if early:
            sh, sm = (int(x) for x in schedule_start.split(":"))
            shift_min = delta
            new_total = sh * 60 + sm + 9 * 60 - shift_min
            early_hint = f"{new_total // 60:02d}:{new_total % 60:02d}"
        logger.info(
            "\n[%d/%d] %s",
            i,
            len(overtime),
            _format_entry(
                entry,
                attendance,
                schedule_start=schedule_start,
                latest_checkin=latest_checkin,
                expected_checkout=early_hint,
            ),
        )
        while True:
            action = input("  申請? (y=送出 / s=跳過) [y]: ").strip().lower() or "y"
            if action == "y":
                default_reason = entry.get("reason", "工作需要")
                reason = input(f"  加班原因 [{default_reason}]: ").strip() or default_reason
                plan["overtime"].append(
                    {"entry": entry, "action": "submit", "key": key, "reason": reason}
                )
                _save_plan(plan_path, plan)
                break
            if action == "s":
                plan["overtime"].append({"entry": entry, "action": "skip", "key": key})
                _save_plan(plan_path, plan)
                break


def _interactive_leave(
    *,
    leave: list[dict],
    attendance: dict,
    completed: set[str],
    schedule_start: str,
    latest_checkin: str,
    saved_plan: dict,
    plan: dict,
    plan_path: Path,
    proxy: str | None,
    allocations: dict[str, str],
    leave_type_map: dict[str, str],
    logger,
) -> None:
    if not leave:
        return
    common_keys = ["27", "30", "1", "2", "5", "18"]
    common_display = "  ".join(f"{k}={leave_type_map.get(k, '?')}" for k in common_keys)
    full_display = "\n".join(f"  {k:>2}={v}" for k, v in leave_type_map.items())
    inv_map = {v: k for k, v in leave_type_map.items()}

    logger.info("\n%s\n請假單 (%d 筆) — 蒐集決策中\n%s", "=" * 50, len(leave), "=" * 50)
    for i, entry in enumerate(leave, 1):
        key = _entry_key(entry, "leave")
        if key in completed:
            logger.info(
                "[%d/%d] %s ✅ 已申請,略過",
                i,
                len(leave),
                _format_entry(
                    entry,
                    attendance,
                    schedule_start=schedule_start,
                    latest_checkin=latest_checkin,
                ),
            )
            plan["leave"].append({"entry": entry, "action": "skip", "already_done": True})
            continue
        if key in saved_plan:
            d = saved_plan[key]
            plan["leave"].append({**d, "entry": entry})
            logger.info(
                "[%d/%d] %s ↩️  沿用 (%s / %s)",
                i,
                len(leave),
                _format_entry(
                    entry,
                    attendance,
                    schedule_start=schedule_start,
                    latest_checkin=latest_checkin,
                ),
                d.get("action"),
                d.get("leave_type", ""),
            )
            continue
        suggested = allocations.get(_entry_key(entry, "leave"))
        suggested_code = inv_map.get(suggested) if suggested else None

        logger.info(
            "\n[%d/%d] %s [%s]",
            i,
            len(leave),
            _format_entry(
                entry,
                attendance,
                schedule_start=schedule_start,
                latest_checkin=latest_checkin,
            ),
            entry.get("type_hint", ""),
        )
        if suggested:
            logger.info("  💡 建議 cascade → %s (%s)", suggested, suggested_code)
        while True:
            default_code = suggested_code or ("27" if entry.get("type_hint") == "WFH" else "30")
            choice = (
                input(f"  假別 [{common_display}  ?=展開] ({default_code}): ").strip()
                or default_code
            )
            if choice == "?":
                logger.info(full_display)
                continue
            leave_type = leave_type_map.get(choice)
            if not leave_type:
                logger.info("  ❌ 無效選項,請重新輸入")
                continue
            action = input("  申請? (y=送出 / s=跳過) [y]: ").strip().lower() or "y"
            if action == "y":
                default_reason = entry.get("reason", "personal matter")
                reason = input(f"  請假原因 [{default_reason}]: ").strip() or default_reason
                entry_proxy = proxy
                if "異地辦公" not in leave_type and proxy:
                    new_proxy = input(f"  代理人 [{proxy},Enter 保留]: ").strip()
                    if new_proxy:
                        entry_proxy = new_proxy
                plan["leave"].append(
                    {
                        "entry": entry,
                        "action": "submit",
                        "key": key,
                        "leave_type": leave_type,
                        "reason": reason,
                        "proxy": entry_proxy,
                    }
                )
                _save_plan(plan_path, plan)
                break
            if action == "s":
                plan["leave"].append({"entry": entry, "action": "skip", "key": key})
                _save_plan(plan_path, plan)
                break


# Leave type code → 假別名 (matches code_agent_hr's table).
LEAVE_TYPE_MAP: dict[str, str] = {
    "1": "特休假",
    "2": "事假",
    "3": "半薪病假",
    "4": "住院病假",
    "5": "有薪病假",
    "6": "安胎假",
    "7": "婚假",
    "8": "訂婚假",
    "9": "陪產假",
    "10": "陪產假-o",
    "11": "八日喪假",
    "12": "六日喪假",
    "13": "三日喪假",
    "14": "公假-教召",
    "15": "公假-訓練",
    "16": "公假-公出",
    "17": "公傷病假",
    "18": "忘刷忘帶卡",
    "19": "國內出差",
    "20": "國外出差",
    "21": "行政假",
    "22": "榮譽假",
    "23": "產檢假-新",
    "24": "防疫照顧假",
    "25": "防疫假",
    "26": "疫苗接種假",
    "27": "異地辦公",
    "28": "謀職假",
    "29": "社團參與假",
    "30": "補休假",
    "31": "生日假",
    "32": "遲到早退",
    "33": "出勤異常扣薪",
}


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.cascade import DEFAULT_CASCADES, allocate
    from lib.config import AttendanceConfig
    from lib.env import load as load_env
    from lib.portal import apply_forms as af, balances as bal
    from lib.portal.client import (
        AgentBrowserMissing,
        LoginTimeout,
        PortalSession,
        ensure_login,
    )
    from lib.state import AttendanceStateManager

    if args.debug:
        logger.setLevel(logging.DEBUG)

    load_env()
    try:
        base_url = _resolve_base_url(args)
    except RuntimeError as e:
        logger.error("❌ %s", e)
        sys.exit(2)

    # Step 1 — sync if needed (Portal is truth for dedup)
    try:
        _maybe_sync(args, base_url, logger)
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)
    except Exception as e:
        logger.warning("⚠️ portal-sync 失敗 (%s) — 改用既有 state cache", e)

    # Step 2 — load analysis + attendance + state
    try:
        analysis = _load_analysis(args.input)
    except Exception as e:
        logger.error("❌ 無法載入 analysis.json: %s", e)
        sys.exit(2)
    config = AttendanceConfig()
    attendance_path = args.attendance or _auto_detect_attendance(args.input)
    attendance = _load_attendance_map(attendance_path)
    if attendance:
        logger.info("📂 出勤打卡資料: %s (%d 日)", attendance_path, len(attendance))

    sm = AttendanceStateManager(read_only=False)
    completed_in_state: set[str] = set()
    for kind, entries in [
        ("overtime", sm.get_applied_forms(args.user, "overtime")),
        ("leave", sm.get_applied_forms(args.user, "leave")),
    ]:
        for e in entries:
            completed_in_state.add(_entry_key(e, kind))

    overtime = list(analysis.get("overtime", []))
    leave = list(analysis.get("leave", []))
    if args.overtime_only:
        leave = []
    if args.leave_only:
        overtime = []

    # Step 3 — cascade allocation
    try:
        bal_data = None
        if _should_fetch_balances(leave, args.no_sync):
            with PortalSession(args.session) as portal:
                ensure_login(portal, base_url)
                bal_data = bal.fetch_balances(portal, base_url)
    except Exception as e:
        logger.warning("⚠️ 無法抓取餘額 (%s) — cascade 使用預設值", e)
        bal_data = {"items": {}, "annual_leave": None}
    allocations: dict[str, str] = {}
    if leave and bal_data:
        result = allocate(
            leave,
            bal_data,
            cascades=DEFAULT_CASCADES,
            already_applied=sm.get_applied_forms(args.user, "leave"),
        )
        for d in result.decisions:
            if d.leave_type:
                allocations[_entry_key(d.entry, "leave")] = d.leave_type
        logger.info("\n📋 Cascade 建議分配:\n%s", _summarize_decisions(result))

    # Step 4 — interactive / auto
    plan_path = _plan_path(args.input)
    result_path = _result_path(args.input)
    saved_plan = _load_plan(plan_path)
    completed_in_results = _load_completed(result_path)
    completed = completed_in_state | completed_in_results
    plan: dict = {"overtime": [], "leave": []}

    if args.auto:
        for e in overtime:
            key = _entry_key(e, "overtime")
            if key in completed:
                plan["overtime"].append({"entry": e, "action": "skip", "already_done": True})
                continue
            plan["overtime"].append(
                {
                    "entry": e,
                    "action": "submit",
                    "key": key,
                    "reason": e.get("reason", "工作需要"),
                }
            )
        for e in leave:
            key = _entry_key(e, "leave")
            if key in completed:
                plan["leave"].append({"entry": e, "action": "skip", "already_done": True})
                continue
            assigned = allocations.get(key) or (
                "異地辦公" if e.get("type_hint") == "WFH" else "補休假"
            )
            plan["leave"].append(
                {
                    "entry": e,
                    "action": "submit",
                    "key": key,
                    "leave_type": assigned,
                    "reason": e.get("reason", "personal matter"),
                    "proxy": args.proxy,
                }
            )
    else:
        _interactive_overtime(
            overtime=overtime,
            attendance=attendance,
            completed=completed,
            schedule_start=config.schedule_start,
            latest_checkin=config.latest_checkin,
            saved_plan=saved_plan,
            plan=plan,
            plan_path=plan_path,
            logger=logger,
        )
        _interactive_leave(
            leave=leave,
            attendance=attendance,
            completed=completed,
            schedule_start=config.schedule_start,
            latest_checkin=config.latest_checkin,
            saved_plan=saved_plan,
            plan=plan,
            plan_path=plan_path,
            proxy=args.proxy,
            allocations=allocations,
            leave_type_map=LEAVE_TYPE_MAP,
            logger=logger,
        )

    submit_ot = [p for p in plan["overtime"] if p["action"] == "submit"]
    submit_lv = [p for p in plan["leave"] if p["action"] == "submit"]
    logger.info("\n%s\n📋 送出確認\n%s", "=" * 50, "=" * 50)
    for p in submit_ot:
        logger.info(
            "  加班 %s  reason: %s",
            _format_entry(
                p["entry"],
                attendance,
                schedule_start=config.schedule_start,
                latest_checkin=config.latest_checkin,
            ),
            p["reason"],
        )
    for p in submit_lv:
        logger.info(
            "  請假 %s [%s] reason: %s",
            _format_entry(
                p["entry"],
                attendance,
                schedule_start=config.schedule_start,
                latest_checkin=config.latest_checkin,
            ),
            p["leave_type"],
            p["reason"],
        )
    if not (submit_ot or submit_lv):
        logger.info("(無需送出項目)")
        return

    if not args.auto:
        prompt_suffix = " (DRY RUN — 不會實際送出)" if args.dry_run else ""
        confirm = (
            input(f"\n確認送出 {len(submit_ot) + len(submit_lv)} 筆{prompt_suffix}? (y/n) [y]: ")
            .strip()
            .lower()
            or "y"
        )
        if confirm != "y":
            logger.info("⏹ 已取消")
            return

    # Step 5 — submit
    results: dict[str, list[dict]] = {"overtime": [], "leave": []}

    def _persist_ot(plan_entry, ok):
        results["overtime"].append(
            {
                "entry": plan_entry["entry"],
                "submitted": ok,
                "dry_run": args.dry_run,
                "reason": plan_entry["reason"],
            }
        )
        _save_results(result_path, results)
        # Don't poison applied_forms cache during a dry run.
        if ok and not args.dry_run:
            sm.record_applied_form(
                args.user,
                "overtime",
                {
                    **plan_entry["entry"],
                    "leave_type": None,
                    "status": "已送出 (本機新增)",
                },
                datetime.now().isoformat(timespec="seconds"),
            )
            sm.save_state()

    def _persist_lv(plan_entry, ok):
        results["leave"].append(
            {
                "entry": plan_entry["entry"],
                "submitted": ok,
                "dry_run": args.dry_run,
                "leave_type": plan_entry["leave_type"],
                "reason": plan_entry["reason"],
            }
        )
        _save_results(result_path, results)
        if ok and not args.dry_run:
            sm.record_applied_form(
                args.user,
                "leave",
                {
                    **plan_entry["entry"],
                    "leave_type": plan_entry["leave_type"],
                    "status": "已送出 (本機新增)",
                },
                datetime.now().isoformat(timespec="seconds"),
            )
            sm.save_state()

    try:
        with PortalSession(args.session) as portal:
            ensure_login(portal, base_url)
            ot_ok, ot_total, lv_ok, lv_total = af.batch_submit(
                portal,
                base_url,
                _wrap_submit_iter(submit_ot, completed, "overtime"),
                _wrap_submit_iter(submit_lv, completed, "leave"),
                on_overtime_done=_persist_ot,
                on_leave_done=_persist_lv,
                dry_run=args.dry_run,
                dry_run_pause_secs=args.dry_run_pause_secs,
                screenshot_dir=_resolve_screenshot_dir(args),
            )
        prefix = "🧪 DRY RUN 結果" if args.dry_run else "📊 本次申請結果"
        logger.info("\n%s: 加班 %d/%d, 請假 %d/%d", prefix, ot_ok, ot_total, lv_ok, lv_total)
        if args.dry_run:
            logger.info(
                "ℹ️ DRY RUN 已跳過『確定送出』+ 未寫入 applied_forms cache "
                "(Portal 上不會出現任何單據)"
            )
        logger.info("✅ 結果寫入 %s", result_path)
    except AgentBrowserMissing as e:
        logger.error("❌ %s", e)
        sys.exit(3)
    except LoginTimeout as e:
        logger.error("❌ %s", e)
        sys.exit(4)


def _resolve_screenshot_dir(args) -> Path | None:
    """Return the directory for dry-run screenshots, or None to disable.

    Rules:
      - Non-dry-run runs: no screenshots (returns None).
      - User passed `--screenshot-dir ''`: explicit opt-out → None.
      - User passed `--screenshot-dir PATH`: honor it.
      - Default dry-run: tmp/dry-run-screenshots/<UTC timestamp>/.
    """
    if not args.dry_run:
        return None
    if args.screenshot_dir is not None:
        # Explicit empty string disables screenshots
        if args.screenshot_dir == "":
            return None
        return Path(args.screenshot_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("tmp") / "dry-run-screenshots" / stamp


def _wrap_submit_iter(plans: list[dict], completed: set[str], form_type: str) -> Iterable[dict]:
    """Yield only plans that still need submission, gracefully skipping
    completed ones (state cache may have been updated mid-run)."""
    for p in plans:
        if _entry_key(p["entry"], form_type) in completed:
            continue
        yield p


def _summarize_decisions(result) -> str:
    from lib.cascade import summarize

    return summarize(result)

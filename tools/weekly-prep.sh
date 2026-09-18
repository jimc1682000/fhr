#!/usr/bin/env bash
#
# Stage a fhr attendance wave: Portal pre-flight, fetch, sync, export, git
# evidence. Everything up to the point where judgement is needed.
#
# What it deliberately does NOT do: correct the analyzer's false positives,
# grade Slack/任務系統/Calendar evidence, write HR-facing reasons, pick 假別, or
# submit anything. Those are phases 3-5 of `.claude/skills/fhr-attendance-run`
# and they need a Claude Code session, not a shell script.
#
# The first portal-* call opens a headed Chromium and waits up to 600s for a
# password. That is why this notifies before starting: on a schedule, nobody
# is watching the terminal.
#
# Usage:  tools/weekly-prep.sh [--out-dir DIR]
# Env:    EHR_URL (required; also read from ./.env), FHR_USER (default JimmyChen)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FHR_USER="${FHR_USER:-JimmyChen}"
OUT_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$OUT_DIR" ] || OUT_DIR="tmp/$(date +%Y%m)"

notify() {
    # Best-effort: a missing osascript (CI, Linux) must not fail the run.
    osascript -e "display notification \"$2\" with title \"fhr $1\"" 2>/dev/null || true
    echo "[$1] $2"
}

# EHR_URL may carry the login path; `fhr --base-url` wants the base only.
if [ -z "${EHR_URL:-}" ] && [ -f .env ]; then
    EHR_URL="$(grep -m1 '^EHR_URL=' .env | cut -d= -f2-)"
fi
if [ -z "${EHR_URL:-}" ]; then
    notify "設定缺漏" "EHR_URL 未設定，跳過這次"
    exit 2
fi
BASE_URL="${EHR_URL%/LoginFOrginal.asp}"
BASE_URL="${BASE_URL%/}"

fhr() { python3 -c 'from lib.cli import run; run()' "$@"; }

# Off the office network (WFH Monday, VPN down) is a skip, not a failure —
# exiting non-zero would just fill the launchd log with noise.
if ! curl -sS -o /dev/null --max-time 10 "$BASE_URL/LoginFOrginal.asp" 2>/dev/null; then
    notify "跳過" "連不到 EHR，可能不在辦公室網路上"
    exit 0
fi

mkdir -p "$OUT_DIR"
# Cover the previous month too: a run early in the month would otherwise miss
# the tail of the last one. portal-apply dedups on (date, start, end) anyway.
DATE_S="$(date -v-1m +%Y/%m/01)"
DATE_E="$(date +%Y/%m/%d)"
TODAY="$DATE_E"
ATTENDANCE="$OUT_DIR/$(date -v-1m +%Y%m)-$(date +%Y%m)-${FHR_USER}-出勤資料.txt"

notify "要登入" "瀏覽器開了，請輸入 EHR 密碼（10 分鐘內）"

fhr portal-check --base-url "$BASE_URL" | tee "$OUT_DIR/portal-check.txt" || true
fhr portal-balances --base-url "$BASE_URL" | tee "$OUT_DIR/balances.txt"
fhr portal-fetch --user "$FHR_USER" --date-s "$DATE_S" --date-e "$DATE_E" \
    --out "$ATTENDANCE" --base-url "$BASE_URL"
fhr portal-sync --user "$FHR_USER" --base-url "$BASE_URL"
fhr export --to=analysis-v1 "$ATTENDANCE" --out "$OUT_DIR/analysis.json" --today "$TODAY"
# Authors and the company git host identify a workplace, so they live in the
# environment, not in this repo. FHR_AUTHORS is comma-separated.
reasons_args=()
IFS=',' read -ra _authors <<< "${FHR_AUTHORS:-}"
for a in "${_authors[@]}"; do
    [ -n "$a" ] && reasons_args+=(--author "$a")
done
if [ ${#reasons_args[@]} -eq 0 ]; then
    notify "設定缺漏" "FHR_AUTHORS 未設定，跳過 git 證據收集"
else
    [ -n "${FHR_WORK_HOST:-}" ] && reasons_args+=(--work-host "$FHR_WORK_HOST")
    fhr reasons --input "$OUT_DIR/analysis.json" \
        --out "$OUT_DIR/reasons-evidence.json" "${reasons_args[@]}" --weekend
fi

notify "資料備好" "$OUT_DIR — 開 Claude Code 跑 /fhr-attendance-run 接 Phase 3"

#!/usr/bin/env bash
#
# Thin wrapper around `fhr portal-apply` so the command stays short enough to
# copy out of a terminal without soft-wrap turning into real newlines.
#
# Usage:  tools/apply-wave.sh tmp/YYYYMM/analysis-foo.json [--dry-run ...]
# Env:    EHR_URL (required; also read from ./.env), FHR_USER, FHR_PROXY

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ANALYSIS="${1:-}"
if [ -z "$ANALYSIS" ]; then
    echo "usage: tools/apply-wave.sh <analysis.json> [portal-apply flags]" >&2
    exit 2
fi
shift

if [ -z "${EHR_URL:-}" ] && [ -f .env ]; then
    EHR_URL="$(grep -m1 '^EHR_URL=' .env | cut -d= -f2-)"
fi
if [ -z "${EHR_URL:-}" ]; then
    echo "EHR_URL 未設定（可放進 .env）" >&2
    exit 2
fi
BASE_URL="${EHR_URL%/LoginFOrginal.asp}"
BASE_URL="${BASE_URL%/}"

set -- python3 attendance_analyzer.py portal-apply \
    --user "${FHR_USER:-JimmyChen}" \
    --input "$ANALYSIS" \
    --base-url "$BASE_URL" \
    "$@"
# The 職務代理人 is a colleague's name, so it stays in the environment rather
# than in the repo. WFH leave types skip the field anyway.
[ -n "${FHR_PROXY:-}" ] && set -- "$@" --proxy "$FHR_PROXY"

exec "$@"

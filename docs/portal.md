# Portal automation (`fhr portal-*`)

End-to-end Portal integration via the optional [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI. Covers attendance scraping, leave-balance reads, dedup against already-submitted forms, and interactive batch submission.

## Subcommands

| Command | Purpose |
|---------|---------|
| `fhr portal-fetch`     | Scrape 全部刷卡資料 → fhr-native 9-column `.txt` |
| `fhr portal-sync`      | Mirror Portal's already-submitted 加班 / 請假單 into the state cache |
| `fhr portal-balances`  | Print 假別餘額 table (補休 / 特休 / 事假 / 病假 / 異地辦公) |
| `fhr portal-apply`     | Interactive (or `--auto`) batch submission of OT + leave forms |

## Setup

1. **Install agent-browser** (optional dep — only the `portal-*` subcommands need it)
   ```bash
   npm install -g agent-browser
   agent-browser install
   ```

2. **`.env`** at the repo root (NEVER commit this file):
   ```
   EHR_URL=http://192.168.101.247/ehrPortal/LoginFOrginal.asp
   EHR_COMPANY_NO=53003028
   EHR_COMPANY_NAME=台灣威亞數位科技股份有限公司
   # optional — defaults to "fhr"
   AGENT_BROWSER_SESSION=fhr
   ```

3. **Manual first login** — every `portal-*` subcommand calls `ensure_login()` which opens a headed Chromium window and waits for the user to type their password directly. The CLI never touches credentials.

## End-to-end flow

```bash
# 1. Scrape this month's punches → .txt the analyzer can ingest
fhr portal-fetch --user JimmyChen

# 2. Run analysis
fhr analyze tmp/202605-JimmyChen-出勤資料.txt

# 3. Export to the interop schema
fhr export --to=code-agent-hr tmp/202605-JimmyChen-出勤資料.txt \
    --out tmp/analysis.json --cutoff 2026/04/17 --today 2026/05/19

# 4. (Optional) collect raw evidence + abstract reasons via agent skill
fhr reasons --input tmp/analysis.json --author 'Jimmy Chen' \
    --out tmp/reasons-evidence.json
# In Claude Code: /fhr-reason-abstract

# 5. Submit. Pre-syncs already-applied forms from Portal automatically.
fhr portal-apply --user JimmyChen --input tmp/analysis.json --proxy 賴菁甫
```

## State cache

Per-user data persists in `attendance_state.json` (or wherever `FHR_STATE_FILE` points):

```jsonc
{
  "users": {
    "JimmyChen": {
      "processed_date_ranges": [...],         // analyzer (legacy)
      "forget_punch_usage": {...},             // analyzer
      "applied_forms": {                       // portal-sync writes this
        "overtime": [...],
        "leave": [...],
        "last_full_sync": "2026-05-20T10:00:00"
      }
    }
  }
}
```

`portal-apply` consults `applied_forms` to skip dates already submitted. It auto-runs `portal-sync` if `last_full_sync` is older than `--sync-max-age-hours` (default 4).

## Security

- **Never** put a password in `.env` (loader will accept it, but the Portal flow doesn't need it). The login flow always goes through a real browser window.
- `agent-browser eval` runs JavaScript inside the Portal page; we only execute payloads checked into `lib/portal/`.
- The state cache mirrors Portal data only — no plaintext secrets.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `AgentBrowserMissing` | `npm install -g agent-browser` not run, or `npm` bin not on PATH |
| `LoginTimeout` | The browser window closed or `--max-wait-secs` expired; rerun and log in faster |
| `agent-browser timed out after 30s` | Portal slow / iframe still loading — bump `PortalSession(..., timeout_secs=...)` in the call site |
| 找不到查詢表單欄位 | Portal layout drifted; update `_extract_form_refs` / `_extract_filter_refs` heuristics in `lib/portal/attendance.py` / `approvals.py` |
| 假別匹配多個 | Pick a more specific `leave_type_name` in the cascade config or the interactive prompt |

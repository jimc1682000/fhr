# Portal automation (`fhr portal-*`)

End-to-end Portal integration via the optional [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI. Covers attendance scraping, leave-balance reads, dedup against already-submitted forms, and interactive batch submission.

## Subcommands

| Command | Purpose |
|---------|---------|
| `fhr portal-fetch`     | Scrape 全部刷卡資料 → fhr-native 9-column `.txt` |
| `fhr portal-sync`      | Mirror Portal's already-submitted 加班 / 請假單 into the state cache |
| `fhr portal-check`     | Pre-flight: list 已駁回 (rejected) + 未處理 (still in-flow) forms before a new batch |
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
# 0. Pre-flight — nothing rejected / stuck in簽核 before a new batch
fhr portal-check --since 2026/05

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

## Pre-flight check (`portal-check`)

Run this **before** submitting a new wave of forms. It queries the eWorkFlow
Search page's 狀態 dropdown for the two buckets that need attention and skips
the terminal ones:

- **已駁回** — a form was rejected; decide whether to re-submit.
- **未處理** — still waiting on an approver (in-flow); avoid stacking new forms.

Anything 已核准 or withdrawn is terminal and not surfaced. `--since YYYY/MM`
scopes the report to a work-date window (lexical prefix match on `YYYY/MM/DD`);
omit it to scan all history. Read-only — no Portal writes, no cache mutation.

> Status taxonomy (validated against the live Portal): the 狀態 dropdown offers
> `未處理 / 已處理 / 已核准 / 已駁回 / 全部`. `已處理` = every acted-on form
> (= 全部 when nothing is pending); `未處理` is the in-flow bucket. The approval
> status shown per row lives in the visible 狀態 column (`流程結束(完成/駁回)`),
> **not** in `wsdinfotext` — `portal-sync` now stores it on each cached entry
> (previously blank).

```bash
fhr portal-check                 # all history
fhr portal-check --since 2026/05 # only work-dates >= 2026/05
```

Exits `0` only when the report is clean; rejected / in-flow findings exit `1`,
and query failures exit `6`,
so scripted gating works: `fhr portal-check --since 2026/05 && fhr portal-apply …`.

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

## Submission confirmation (`portal-apply`)

A form only counts as submitted once it shows up in the Portal's **全部**
list, excluding rejected and withdrawn forms. The Portal gives no reliable signal on the form page itself: a non-WFH
leave without a 職務代理人 is dropped silently, the page stays at
`目前狀態：新增`, and that page contains disabled widgets, which the old
snapshot heuristic took as success.

For every entry (dry runs skip the list lookups):

1. **Precondition**: non-WFH leave without `--proxy` → `blocked`. The CLI checks
   this for the whole batch first and exits `2` before submitting anything.
2. **預查**：查全部狀態，只排除退件與撤回。起訖日期、時間及假別皆相同才回傳
   `already_pending`，包含已核准的單。假別無法辨識、資料列無法解析、分頁重複
   或不完整時回傳 `failed`，不送單。
3. **Confirmation**: after 確定送出, the entry is `confirmed` only if the list
   now has it; otherwise `unconfirmed`.

| Status | On the Portal? | Counts as submitted |
|---|---|---|
| `confirmed` | yes | yes |
| `already_pending` | yes（預查已存在，含已核准） | yes |
| `unconfirmed` | not found after clicking submit | no — check before re-submitting |
| `failed` | submit not clicked (leave type mismatch, list unreadable) | no |
| `blocked` | form never opened (missing proxy) | no |
| `dry_run` | no (preview only) | bookkeeping only |

The result file records `status` per entry next to `submitted`. `portal-apply`
exits `5` when any entry ends outside `confirmed / already_pending / dry_run`.

同一使用者的本機執行會共用 lock，第二個 `portal-apply` 在接觸 Portal 前以 `5`
結束。此鎖僅涵蓋同一台機器、同一作業系統使用者；不協調其他機器或人工送單。
按「確定送出」拋出 `AgentBrowserError` 時，先對帳並將該筆 `confirmed` 或
`unconfirmed` 寫入結果檔，再以 `5` 結束，不繼續批次。即使回傳 `confirmed`，
這次執行仍以 `5` 表示曾中斷，重跑前須先讀結果檔。

送單後 hook 用 shell token 辨識真正的指令，支援加引號的指令名稱與
`--input=檔案`，並將 `--base-url`、`--session` 傳給 `portal-check`。
`--dry-run-pause-secs` 不會被誤當成 `--dry-run`；背景執行只提醒稍後對帳。
`FHR_PORTAL_CHECK_TIMEOUT` 不是正整數時回到預設 150 秒。

| 指令 | 結束碼 | 說明 |
|---|---|---|
| `portal-apply` | `0` | 全部完成或預覽完成；仍須讀每筆狀態 |
| `portal-apply` | `5` | 有未完成項目、送出中斷，或本機已有另一個程序執行 |
| `portal-check` | `0` | 查詢成功且沒有退件／簽核中項目 |
| `portal-check` | `1` | 查詢成功，有退件／簽核中項目 |
| `portal-check` | `6` | 查詢失敗，hook 不把錯誤輸出當成對帳證據 |
| 兩者 | `2`／`3`／`4` | 參數錯誤／瀏覽器缺失／登入逾時 |


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

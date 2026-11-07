# Portal automation (`fhr portal-*`)

End-to-end Portal integration via the optional [`agent-browser`](https://github.com/vercel-labs/agent-browser) CLI. Covers attendance scraping, leave-balance reads, dedup against already-submitted forms, and interactive batch submission.

## Subcommands

| Command | Purpose |
|---------|---------|
| `fhr portal-fetch`     | Scrape 全部刷卡資料 → fhr-native 9-column `.txt` |
| `fhr portal-sync`      | Mirror Portal's already-submitted 加班 / 請假單 into the state cache |
| `fhr portal-check`     | Pre-flight: list 已駁回、流程停止(抽單) and 未處理 forms before a new batch |
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
Search page for rejected, withdrawn and in-flow forms:

- **已駁回** — a form was rejected; decide whether to re-submit.
- **流程停止(抽單)** — listed from the 全部 query; decide whether a replacement is needed.
- **未處理** — still waiting on an approver (in-flow); avoid stacking new forms.

Approved forms are not surfaced. Withdrawn findings also exit `1`. `--since YYYY/MM`
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
lock contention exits `5`, and query failures exit `6`,
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
list with an explicitly recognized active status. The Portal gives no reliable signal on the form page itself: a non-WFH
leave without a 職務代理人 is dropped silently, the page stays at
`目前狀態：新增`, and that page contains disabled widgets, which the old
snapshot heuristic took as success.

For every entry (dry runs skip the list lookups):

1. **Precondition**: non-WFH leave without `--proxy` → `blocked`. The CLI checks
   this for the whole batch first and exits `2` before submitting anything.
2. **預查**：先開請假表單，依下拉選單「完全相同優先、子字串次之」解析唯一
   假別全名；例如 `事假` 解析為 `事假(含家庭照顧假)`。沒有匹配或匹配多個選項時
   回傳 `failed`。查全部狀態，比對起訖日期、時間與實際假別全名；相同有效單回傳
   `already_pending`。允許的有效狀態為「主管簽核 - 一階主管」、「流程結束(完成)」，
   以及既有別名「未處理」、「簽核中」、「已核准」。
   「流程停止(抽單)」與「流程結束(駁回)」不算既有有效單，並保留舊版失效狀態
   別名的辨識。其他未知狀態、假別無法辨識、資料列無法解析、分頁重複或不完整時
   回傳 `failed`，不送單。預查後重新開表單並確認假別全名未變，再填寫送出。
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

同一使用者的本機 `portal-apply` 與 `portal-check` 共用 apply lock，取不到鎖的程序
在接觸 Portal 前以 `5` 結束。`portal-check` 從登入到瀏覽器查詢結束都持有此鎖。
此鎖僅涵蓋同一台機器、同一作業系統使用者；不協調其他機器或人工送單。
按「確定送出」拋出 `AgentBrowserError` 時，先對帳並將該筆 `confirmed` 或
`unconfirmed` 寫入結果檔，再以 `5` 結束，不繼續批次。即使回傳 `confirmed`，
這次執行仍以 `5` 表示曾中斷，重跑前須先讀結果檔。

結果檔保留 `overtime`／`leave` 陣列，頂層新增 `run_id`（每次送單唯一的 UUID）
與 `completed`。逐筆進度保存為 `false`；正常批次或送出中斷完成收尾後保存為
`true`，再於 stdout 印出獨立一行 `結果寫入：<絕對路徑>（run_id=<UUID>）`。
每次保存都先寫同目錄暫存檔，再以 rename 原子替換，讀者不會讀到半份 JSON。
`completed: true` 表示已完成結果收尾，**不表示每筆都成功或全部項目都已處理**；
中斷時只包含已取得結果的項目，仍以 exit 5 停止。
既有結果的 `overtime`／`leave` 仍可用於重跑去重，但沒有新格式收據的舊檔不能
作為本次確認依據。

### 送單後提醒

hook 同時註冊 `PostToolUse` 與 `PostToolUseFailure` 兩種 Bash 事件，
輸出的 `hookEventName` 與收到的事件一致，以 `additionalContext` 回傳同一段
固定提醒。成功與非 0 結束碼都會提醒，無須完成標記或結果檔。

偵測以 shell token 辨識 `fhr`、`attendance_analyzer.py` 或
`python -m attendance_analyzer` 的 `portal-apply`／`portal_apply` 呼叫，
支援引號、環境變數前綴、`uv run`、`timeout N`、換行與重新導向。
忽略 `--dry-run`、`-h`、`--help` 與明顯只讀文字的 `echo`、`grep` 等指令；
`--dry-run-pause-secs` 不會被誤當成 `--dry-run`。
這是提醒用的簡單偵測，不解析 `bash -c "…"` 等內層 shell。

提醒內容：

- 結果以 `portal-apply` 印出的逐筆狀態與 exit code 為準，只有
  `confirmed`／`already_pending` 代表送單時已確認 Portal 上有有效單，
  未必仍在簽核中。`unconfirmed`、`failed`、`blocked` 都不算。
- exit 5 表示有未確認的單、送出中斷，或另一個 `portal-apply`／`portal-check`
  正在執行。回報前先跑 `fhr portal-check --since <最早日期>` 對帳，
  **不可以直接重送**。日期應涵蓋本次所有待確認項目。
- `run_in_background`、shell 的 `&` 或 `tool_response.backgroundTaskId`
  表示背景執行時，送單可能還在進行，須等它完成、看完輸出再對帳，
  不可以說成「沒有送單」。背景結束後不保證再次觸發 hook。
- 任何一筆沒有確認，就不可以把該筆或整批回報為「已送出」或「簽核中」。

hook 不讀寫結果檔、不解析收據、不比對 run_id 或 mtime、不取 lock、
不執行 `portal-check`，也不產生快照。查重、flock、逐筆對帳、exit code、
run_id 與原子寫入仍由 `portal-apply` 負責；`portal-check` 仍持鎖查詢。

先前已確認、這次跳過的單不會列出；**沒出現在結果檔，不代表未確認**，
請另查先前證據，不可據此重送或聲稱本次確認。`portal-check` 報告只補充
需要注意的單；已核准的單不會列出，報告缺單或查詢失敗不推翻已確認的逐筆結果。

下表的待處理項目亦包含抽單，與駁回、簽核中項目同樣回傳 `1`。

| 指令 | 結束碼 | 說明 |
|---|---|---|
| `portal-apply` | `0` | 全部完成或預覽完成；仍須讀每筆狀態 |
| `portal-apply` | `5` | 有未完成項目、送出中斷，或本機已有另一個程序執行 |
| `portal-check` | `0` | 查詢成功且沒有退件／簽核中項目 |
| `portal-check` | `1` | 查詢成功，有退件／簽核中項目 |
| `portal-check` | `5` | apply lock 被占用，未接觸瀏覽器，稍後再對帳 |
| `portal-check` | `6` | 查詢失敗，錯誤輸出不可當成對帳證據 |
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

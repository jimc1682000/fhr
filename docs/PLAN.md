# fhr v2: 整合 Portal 抓取 / 申請 / Reason 收集

## Context

目前 fhr (`~/github/fhr`) 是 CSV-based 分析器: user 從 EHR Portal 手動匯出 tab-delimited `.txt` 出勤檔 → 跑 `attendance_analyzer.py` → 產出加班/請假/WFH 建議報表 (CSV/Excel)。後續開單 user 還是要手動到 Portal 填表。

code_agent_hr (`~/workdir/code_agent_hr`) 已有完整的 Portal 自動化(透過 agent-browser): `fetch_data.py` 自動抓刷卡、`apply_forms.py` 互動式批次送加班/請假單。但分析邏輯寫死 10:00/19:00 班表(對 09:30/18:30 班表的 user 全錯), 沒有 reason 自動收集, dedup 靠人工維護的 cutoff_date。

本次 session 寫了**兩個**converter 橋接:
- **inline (未成檔)**: agent-browser 抓到的 JSON 出勤紀錄 → fhr tab-delimited `.txt` (含 9 欄 header,當時 session 用 python heredoc 跑)
- **`scripts/personal/fhr_to_analysis.py`**: fhr CSV 分析結果 → code_agent_hr `analysis.json` schema

並:
- PR #36 / #37 修了 fhr 兩個 bug (headerless file, 假日 API)
- 探出 Portal 假勤項目統計 + 特休統計 iframe 可程式化抓餘額
- 用 Slack + git log 雙來源產 reason
- 抽象化 reason 給 HR 看
- 加 04/25 在外地 OT (Slack 顯示週六有事件處理)
- 修 OT/leave end_time bug (應 = start + hours,不是 actual punch)
- patch apply_forms 顯示實際打卡時間

User 想把 code_agent_hr 的 Portal 抓取/申請/dedup 邏輯 port 進 fhr,並把 state 檔升級成 Portal-derived dedup,並把 reason 收集 + 概念化、週末 OT 偵測、餘額預抓 + cascade 自動分配、早到日 OT 提示 都做成新功能。

目標: fhr 成為 single-source 工具, user 只需 `fhr portal apply` 一條指令就能 (i) 抓出勤 (ii) 分析 (iii) 自動依餘額 cascade 分配假別 (iv) 互動確認 (v) 批次送出,不再需要外部腳本。

## Decisions

| 議題 | 選擇 |
|------|------|
| Code layout | fhr CLI 升級為 multi-subcommand (`fhr analyze`/`fhr portal {fetch,apply,balances,sync}`/`fhr reasons`) |
| agent-browser dep | **Optional**: lazy-import + 友善錯誤訊息;CSV-based analyze 仍可獨立使用 |
| Reason 概念化引擎 | **Raw evidence 不直接 call LLM API**;另寫 Claude Code agent skill (`.claude/skills/fhr-reason-abstract`),user 自選任何模型來執行 |
| Dedup 來源 | **Portal-first + state cache**: 每次 apply 前 sync Portal eWorkFlow 已申請單 → 更新 state cache → 用 cache 作 in-process dedup |

### `fhr portal sync` 語意澄清

**不是** dump 本地 plan/result 暫存檔回 state。**是實際打 Portal**:

```
fhr portal sync
  → ensure_login (agent-browser session)
  → 導航 http://.../eWorkFlow_NewRed.asp?URL=~/Workflow_Frontend/Search/Default.aspx
  → 設條件: 狀態=全部, 表單名稱=加班單 → 提交
  → eval 抓 tr[id^="tbWorkSheetDataList_"] 的 wsdinfotext → 解析 {date, start, end, hours, status}
  → 同樣抓 表單名稱=請假單
  → merge 到 state cache 的 applied_forms (idempotent by key)
```

→ state cache 是 Portal 上實際已申請的鏡像,不是「本地我以為送過」的紀錄。重跑、換機器、清 plan 檔都不影響準確性。

## Architecture

### 新增 lib/ 模組

| 路徑 | 功能 | 取材自 |
|------|------|--------|
| `lib/portal/client.py` | agent-browser CLI wrapper: session 管理, login check, navigate, eval helper, dialog accept | `code_agent_hr/scripts/personal/fetch_data.py` `run_browser_cmd` / `browser_eval` / `ensure_login` |
| `lib/portal/attendance.py` | 抓出勤紀錄 (含分頁), 回傳 records list (相容既有 `AttendanceRecord` schema), 並可 `--export-txt` 直接吐 tab-delimited 9 欄 .txt (取代本 session 的 inline converter) | `code_agent_hr/scripts/personal/fetch_data.py` 翻頁 eval 邏輯 + `docs/personal-query.md` + 本 session inline JSON→txt 腳本 |
| `lib/portal/approvals.py` | 抓 eWorkFlow 已申請單, 解析 `wsdinfotext`,回傳 `[{form_type, date, start_time, end_time, hours, status}]` | `code_agent_hr` 同檔 `wsdinfotext` regex + 本 session `docs/personal-query.md §3` |
| `lib/portal/balances.py` | 抓「假勤項目統計」+「特休統計」iframe,回傳 dict `{假別: {可休總, 已休, 剩餘}}` | 本 session eval 程式碼 (找 `目前可休時數` / `特休假統計` 兩個 iframe) |
| `lib/portal/apply_forms.py` | submit_overtime / submit_leave (含 trigger_hour_calculation, click_submit, verify_submission) | `code_agent_hr/scripts/personal/apply_forms.py:234-401` 直接 port |
| `lib/portal/dedup.py` | Portal-first dedup: sync approvals → 比對 candidate entries → 標記 already_applied | 本 session 設計;state cache 用 fhr `AttendanceStateManager` 擴充 |
| `lib/cascade.py` | cascade allocation: 給定 leave entries + balances + cascade order config → 自動指派每筆假別 | 本 session 手動分配邏輯 |
| `lib/reasons.py` | Raw evidence harvester: 每筆 OT entry 抓對應日期 18:30 (或 user 班表 schedule_end) 後的 Slack 訊息 + `~/git` `~/workdir` `~/github` 各 repo 該日 git commits | 本 session Slack MCP 查詢 + git log 範例 |
| `lib/weekend_ot.py` | 週末/假日 OT 偵測: scan Slack `on:DATE` for Saturday/Sunday/holiday → 列為 `在外地` OT 候選 | 本 session 04/25 案例 |

### 新增 CLI subcommands

```
fhr analyze <file>                  # 現有功能, 完全不動
fhr portal fetch                    # 自動抓出勤 → 寫成 fhr 可吃的格式 (跳過手動 CSV 匯出)
fhr portal balances                 # 顯示假別餘額表 (補休/特休/事假/有薪病假/半薪病假/異地辦公)
fhr portal sync                     # 同步 Portal 已申請單 → 更新 state cache
fhr portal apply [--auto|--interactive]  # 互動式批次送加班/請假單 (含 cascade 自動分配)
fhr reasons [--for=YYYY-MM-DD,...]  # 收集 raw evidence (Slack + git) 寫 .json
```

實作: `lib/cli.py` 改用 `argparse` subparsers (現是單 command)。每 subcommand 對應一個 `lib/commands/*.py` handler。

### 設定擴充

`lib/config.py` `AttendanceConfig` 加 fields:

```python
# 既有: schedule_start, schedule_end, latest_checkin, work_hours, lunch_hours, ...

# 新增
ehr_url: str = ""                          # 從 env 載入
ehr_company_no: str = ""
ehr_company_name: str = ""
agent_browser_session: str = "fhr"
git_repo_roots: list[str] = ["~/git", "~/workdir", "~/github"]
slack_user_id: str = ""                    # 自己的 Slack UID (e.g. UHXDE1X1N)
leave_cascade_late: list[str] = ["補休假", "特休假", "事假"]
leave_cascade_sick_paid: list[str] = ["有薪病假"]      # 用完才 fallback
leave_cascade_sick_half: list[str] = ["半薪病假"]
leave_cascade_wfh: list[str] = ["異地辦公(8hr一週)"]
weekend_ot_default_location: str = "在外地"
```

`config.json` 沿用既有 overlay 機制。新增 `.env` 支援(fhr 目前無):用 `python-dotenv` 或自寫小 loader 從專案根目錄讀 `.env`。

### State schema 擴充

`lib/state.py` `AttendanceStateManager` 加 per-user field:

```jsonc
{
  "users": {
    "JimmyChen": {
      "processed_date_ranges": [...],         // 既有
      "forget_punch_usage": {...},            // 既有
      "applied_forms": {                      // 新增
        "overtime": [
          {"date": "2026/04/20", "start_time": "1830", "end_time": "2030", "hours": 2, "status": "已核准", "synced_at": "..."}
        ],
        "leave": [
          {"date": "2026/04/24", "start_time": "0930", "end_time": "1830", "hours": 9, "leave_type": "異地辦公(8hr一週)", "status": "已核准", "synced_at": "..."}
        ],
        "last_full_sync": "2026/05/20T10:00:00"
      }
    }
  }
}
```

dedup key: `(form_type, date, start_time, end_time)`. `fhr portal sync` 寫入這結構, `fhr portal apply` 跑前讀 + 主動 sync(若 last_full_sync > N 小時前)。

### Reason 收集 + Agent Skill

`fhr reasons` subcommand:
1. 吃 `<analysis>.json` (或 --for 指定日期)
2. 對每個 OT entry:
   - 用 Slack MCP 查 `from:<@${slack_user_id}> on:YYYY-MM-DD`
   - 用 `git log --author=... --since=DATE_schedule_end --until=DATE+1 02:00` 掃 `git_repo_roots` 下每 repo
   - 過濾掉 schedule_end 之前的訊息 (從 config 動態讀,不寫死 18:30)
3. 對每個遲到/早退 entry:
   - 查當日上午 (schedule_start ± 1h) Slack → 找「睡過頭/身體不適」keyword
4. 輸出 `tmp/reasons-evidence.json`:

```jsonc
{
  "2026/04/20": {
    "overtime": {
      "slack": [{"time": "18:47", "channel": "#team-devops", "text": "..."}, ...],
      "git": [{"repo": "jenkins-operations-toolkit", "time": "...", "subject": "feat(versions): add history subcommand"}]
    },
    "leave": {
      "slack_morning": [{"time": "10:36", "text": "睡過頭 晚點進公司"}]
    }
  },
  ...
}
```

5. 配套 `.claude/skills/fhr-reason-abstract/SKILL.md` (Claude Code skill): 描述「給 raw evidence,產出概念化加班事由 (HR-friendly,不流水帳)」的 prompt + 規範。User 跑 `fhr reasons` 後在 Claude Code 喚 `/fhr-reason-abstract`,模型自己讀 evidence 寫回 analysis.json `reason` field。Skill 不綁定特定 model。

### Cascade 自動分配 (`lib/cascade.py`)

輸入: leave entries (有 type_hint: late/sick/WFH) + balances dict + config 的 cascade order。

演算法:
1. 對每個 entry,依 type_hint 找對應 cascade 順序 (late → leave_cascade_late, sick → sick_paid 用完 fallback sick_half, WFH → wfh)
2. 依時序 (chronological) iterate entries,當前 cascade 列表 head 還有額度就用,不夠就 fall to next
3. 異地辦公(8hr一週) 有 **40h/月** 限制 → 按月分桶
4. 輸出每筆 entry 的 `leave_type` 決策

Edge case 提示給 user:
- 補休不足且要橫跨多 entry 時 (e.g. 補休 1h 想吃 2h late) → 整筆 fallback (不切),提示「補休剩 Xh 不足 Yh,改用特休」

### 週末/假日 OT 偵測 (`lib/weekend_ot.py`)

`fhr portal fetch` 跑完後執行:
1. 掃涵蓋期間內所有 Sat/Sun + 國定假日 (從 holiday provider 取)
2. 對每個日期: 查 Slack `from:<@user> on:DATE` → 若有 ≥ N 筆訊息 (config) 視為候選
3. 推出 OT 起訖: 第一/最後一筆 Slack 訊息時間,round 到整點
4. location 預設 `weekend_ot_default_location` = "在外地"
5. 寫進 analysis.json 的 `overtime[]`,標記 `source: "weekend_detected"` 讓 user 在 `fhr portal apply` 確認

### 早到日 OT 提示

`fhr portal apply` 互動 Phase 1 顯示 OT entry 時,若該日 `actual_checkin < latest_checkin`:
```
[N/M] 2026/04/22 18:05-20:05 (2h)  | 實際 上班 09:05  下班 21:03
  💡 早到 25 分鐘 → 預期下班 18:05 (非 18:30)
  申請? (y=送出 / s=跳過) [y]:
```

實作: `lib/commands/apply.py` `format_entry()` 新增 early-arrival annotation。

### 實際打卡時間顯示

本 session patch 已驗證可用,直接 port `apply_forms.py:467-491` (`load_attendance_map` + `format_entry` 改寫) 進 `lib/commands/apply.py`。

## Pre-Phase — 把本 plan 收進 fhr repo

第一個動作: `cp /Users/jimmychen/.claude/plans/code-agent-hr-fhr-code-agent-hr-state-s-goofy-feigenbaum.md /Users/jimmychen/github/fhr/docs/PLAN.md` (檔名簡化),作為 fhr 後續實作的 single source of truth。同 branch 一起 commit 進 Phase 0。

## Phased Delivery (suggested PR 切分)

每 phase 獨立 PR,可分次合進 main。每 phase 末尾 fhr 仍可正常運作。

### Phase 0 — Schemas + Converters (fhr ↔ code_agent_hr 橋接)
**Branch**: `feat/interop-schemas`

定義 versioned schema (放 `docs/schema/`),fhr 端統一負責 export/import,後續任一邊改格式就 bump schema version + 改一個地方。

新增 schema 文件:
- `docs/schema/attendance-analysis-v1.md` — fhr 分析結果的對外格式。匹配 code_agent_hr `analysis.json`:
  ```jsonc
  {
    "schema_version": "attendance-analysis/v1",
    "cutoff_date": "YYYY/MM/DD" | null,
    "overtime": [{"date","start_time","end_time","hours","location","reason"}],
    "leave": [{"date","start_time","end_time","hours","type_hint","reason"}],
    "skipped": [...],
    "summary": {"overtime_count","overtime_hours","leave_count","leave_hours"}
  }
  ```
- `docs/schema/portal-attendance-snapshot-v1.md` — agent-browser 直接 eval 抓出來的出勤紀錄:
  ```jsonc
  {
    "schema_version": "portal-attendance-snapshot/v1",
    "totalPages": int,
    "recordCount": int,
    "records": [{"scheduledTime":"YYYY/MM/DD HH:mm","actualTime":"...","type":"上班/下班","status":"遲到/曠職/..."}]
  }
  ```

新增模組:
- `lib/exporters/__init__.py`
- `lib/exporters/code_agent_hr.py` — `export_analysis(issues, config) -> dict (v1 schema)` + `write(path)`
- `lib/importers/__init__.py`
- `lib/importers/portal_json.py` — `import_snapshot(path) -> list[AttendanceRecord]` 或 `-> bytes (fhr 9-col txt)`,讀 portal-attendance-snapshot-v1
- `lib/schema.py` — schema_version 驗證 helper (raise on mismatch with friendly message)

CLI:
```
fhr export --to=code-agent-hr [--out=tmp/analysis.json] <attendance-file>
fhr import --from=portal-json <snapshot.json> --out=tmp/202604-User-出勤資料.txt
```

決策:
- **Schema 版本管理**: `schema_version` 字串必填,讀檔時驗證;不同 major version → 拒絕讀,提示升級
- **fhr 是 single source**: code_agent_hr 那端不寫新 importer/exporter,所有轉換在 fhr 跑 (即 user 想送 form 仍可暫時用 code_agent_hr,但要先 `fhr export` 產 JSON)
- **過渡性**: 一旦 Phase C (`fhr portal apply`) 上線,exporter 仍保留(對外契約),但 code_agent_hr `apply_forms.py` 可標 deprecated。code_agent_hr 端不主動修改

測試:
- `test/test_exporters_code_agent_hr.py` — fhr issues fixture → 驗 schema v1 output 一致
- `test/test_importers_portal_json.py` — sample snapshot JSON → 驗 records 數量 + AttendanceRecord 欄位
- `test/test_schema_version.py` — 故意給錯 schema_version → 預期 raise

**End-to-end**: 本 session 的 `fhr_to_analysis.py` (in code_agent_hr) 可整個移除,改成 `fhr export --to=code-agent-hr ./202604-202605-JimmyChen-出勤資料.txt --out=tmp/analysis.json` 一句達成。

---

### Phase A — Portal 抓出勤 (取代手動 CSV 匯出)
**Branch**: `feat/portal-fetch-attendance`
- `lib/env.py` `.env` loader
- `lib/portal/client.py` agent-browser wrapper (login, navigate, eval)
- `lib/portal/attendance.py` 含 `--export-txt` 直接產 fhr 吃的 9 欄格式
- `lib/cli.py` subparser 重構 + 既有 `analyze` 包裝
- `lib/commands/portal_fetch.py`
- 文件 `docs/portal.md` + README 章節
- 測試: mock subprocess(agent-browser) 驗 attendance parsing
- **End-to-end**: `fhr portal fetch --date-s ... --date-e ...` → 立刻可 `fhr analyze`

### Phase B — Portal sync + 已申請單 dedup
**Branch**: `feat/portal-sync-dedup`
- `lib/portal/approvals.py` (含分頁)
- `lib/portal/dedup.py`
- `lib/state.py` 擴 `applied_forms`
- `lib/commands/portal_sync.py`
- 測試: mock approvals response → 驗 state schema 寫入 + idempotent
- **End-to-end**: `fhr portal sync` 後 `attendance_state.json` 出現 `applied_forms` block

### Phase C — Portal 餘額 + 申請 (互動模式)
**Branch**: `feat/portal-apply`
- `lib/portal/balances.py`
- `lib/portal/apply_forms.py` (submit_overtime, submit_leave)
- `lib/commands/portal_balances.py`
- `lib/commands/portal_apply.py` 含 3-phase 互動 (plan/result file)
- **早到日 OT 提示** 在 `format_entry` 加註 (本 phase 順便)
- **實際打卡時間顯示** port 自本 session apply_forms.py patch
- 測試: mock eval response → 驗 balance dict + submit verification
- **End-to-end**: `fhr portal apply --interactive` 跑 13 OT + 12 leave 完整 flow

### Phase D — Cascade 自動分配
**Branch**: `feat/cascade-allocation`
- `lib/cascade.py`
- `lib/config.py` 加 cascade 設定 (`leave_cascade_late/sick_paid/sick_half/wfh`)
- `lib/commands/portal_apply.py` 整合: Phase 1 顯示建議假別 (cascade 結果) + 餘額 (剩 Xh) + 月限提示
- 測試: 給定 balance + entries → 驗分配符合 config 順序
- **End-to-end**: 互動 prompt 顯示「補休剩 5h, 建議 30 補休」自動帶

### Phase E — Reason 收集 (raw evidence) + Agent Skill
**Branch**: `feat/reasons-collector`
- `lib/reasons.py` git log harvester (用 `git_repo_roots` config + `schedule_end` 動態時間窗)
- `lib/commands/reasons.py`
- `.claude/skills/fhr-reason-abstract/SKILL.md`: 描述 prompt + 規範
- 測試: mock git subprocess → 驗 evidence schema
- **End-to-end**: `fhr reasons` 產 evidence.json,Claude Code `/fhr-reason-abstract` 寫回 analysis.json

### Phase F — 週末/假日 OT 偵測
**Branch**: `feat/weekend-ot`
- `lib/weekend_ot.py`
- `lib/commands/portal_fetch.py` 收尾呼叫 weekend_ot
- 測試: mock Slack evidence + 國定假日列表 → 驗 OT entry 出現含 location=在外地
- **End-to-end**: 04/25 案例 (六, 14:00-15:00 Slack 活動) → analysis.json overtime[] 自動出現

每 phase 順序可調,但 A → B → C 建議依序 (C 依賴 B 的 dedup, B 依賴 A 的 client)。D/E/F 互相獨立,可平行做。

## Files To Modify / Create

### Create

- `lib/cli.py` — 改寫成 subparsers
- `lib/commands/__init__.py`
- `lib/commands/analyze.py` — 包裝既有 main 流程
- `lib/commands/export.py` (Phase 0)
- `lib/commands/import_.py` (Phase 0)
- `lib/exporters/__init__.py` + `code_agent_hr.py` (Phase 0)
- `lib/importers/__init__.py` + `portal_json.py` (Phase 0)
- `lib/schema.py` (Phase 0)
- `docs/schema/attendance-analysis-v1.md` (Phase 0)
- `docs/schema/portal-attendance-snapshot-v1.md` (Phase 0)
- `lib/commands/portal_fetch.py`
- `lib/commands/portal_apply.py`
- `lib/commands/portal_balances.py`
- `lib/commands/portal_sync.py`
- `lib/commands/reasons.py`
- `lib/portal/__init__.py`
- `lib/portal/client.py`
- `lib/portal/attendance.py`
- `lib/portal/approvals.py`
- `lib/portal/balances.py`
- `lib/portal/apply_forms.py`
- `lib/portal/dedup.py`
- `lib/cascade.py`
- `lib/reasons.py`
- `lib/weekend_ot.py`
- `lib/env.py` — .env loader
- `.claude/skills/fhr-reason-abstract/SKILL.md`
- `docs/portal.md` — usage + 安全政策 (no password storage)
- `docs/cascade.md`
- `docs/reasons.md`
- `test/test_portal_*.py` (各模組對應 unit test, mock urlopen/subprocess)
- `test/test_cascade.py`
- `test/test_weekend_ot.py`

### Modify

- `attendance_analyzer.py` — `__main__` 從直接 `run()` 改成 dispatch 到 subcommand router (向後相容: 若第一個 arg 不是 known subcommand 且像檔名,fall through 到 `analyze`)
- `lib/cli.py` — 拆分既有 logic 到 `commands/analyze.py`
- `lib/config.py` — 加新 fields
- `lib/state.py` — 加 `applied_forms` 操作 (add_applied_form, list_applied_forms, find_duplicate, mark_synced)
- `pyproject.toml` 或 `requirements*.txt` — 加 optional `agent-browser` (npm) 安裝指引;不加 Python deps (agent-browser 是 CLI tool 透過 subprocess 呼叫)
- `README.md` — 新增 Portal 用法章節
- `CLAUDE.md` — 補 Portal 模組 + .env 安全政策
- `AGENTS.md` — 加新模組架構說明
- `Taskfile.yml` / `Makefile` — 補新 task (e.g. `task portal-apply`)

### Reuse (no change)

- `lib/policy.py` (calculate_late_minutes, calculate_overtime_minutes, calculate_expected_checkout) — 既有邏輯正確,直接被 Portal 抓到的 records 餵入
- `lib/dates.py` (identify_complete_work_days)
- `lib/holidays.py` (PR #37 修好的 jsdelivr provider)
- `lib/csv_exporter.py` / `lib/excel_exporter.py`

## Verification

0. **Phase 0: 雙向 converter + schema 驗證**
   - `fhr export --to=code-agent-hr 202604-202605-JimmyChen-出勤資料.txt --out=tmp/analysis.json`
   - 預期 JSON 含 `schema_version: "attendance-analysis/v1"` + 與本 session `fhr_to_analysis.py` 產出 byte-equivalent
   - 故意改 schema_version 後 import → 預期 raise `SchemaVersionError`

1. **CSV-based analyze 向後相容**
   - `python3 attendance_analyzer.py 202604-202605-JimmyChen-出勤資料.txt`
   - 預期: 行為與 PR #37 後完全相同, 134 tests 全綠

2. **`fhr portal balances`** (需 agent-browser + 手動登入)
   - 開瀏覽器 → 自動導航請假單 → 抓 iframe → stdout 印出餘額表
   - 預期含: 補休 7h, 特休 81h, 事假 50h, 有薪病假 0h, 半薪病假 16h, 異地辦公(8hr一週) 40h/月

3. **`fhr portal sync`**
   - 抓 eWorkFlow 已申請單 → 寫進 state cache
   - 預期 `attendance_state.json` 出現 `users.JimmyChen.applied_forms.overtime/leave` array
   - 二次跑同指令 → idempotent (no diff)

4. **`fhr portal fetch --date-s YYYY/MM/DD --date-e YYYY/MM/DD`**
   - 自動翻頁抓出勤 → 產出 `tmp/202604-202605-JimmyChen-出勤資料.txt` (相容既有 analyzer 格式,**含 header line**)
   - 立刻可餵 `fhr analyze` 不需任何手動編輯

5. **`fhr reasons`**
   - 跑後產 `tmp/reasons-evidence.json`,每個 OT/leave 日期都有 slack + git 證據
   - 證據過濾條件: Slack `time > schedule_end` (從 config 動態讀)
   - 在 Claude Code 喚 `/fhr-reason-abstract`,讀 evidence + analysis.json → 寫回每筆的 `reason`

6. **`fhr portal apply --interactive`**
   - 跑前自動 sync (上次 sync > 1h)
   - Phase 1 顯示每筆 entry: 加班含「💡 早到 N min → 預期下班 HH:MM」提示 + 實際打卡時間;請假含建議假別 (cascade) + 餘額 (剩 Xh)
   - 已申請的自動標 ✅ 略過 (從 applied_forms cache)
   - Phase 3 送出後,結果寫回 applied_forms

7. **Cascade 單元測試** (`test/test_cascade.py`)
   - 給定 fake balances + late entries → 預期分配符合 `補休 > 特休 > 事假` 順序 + 月限
   - sick + sick_paid 用完 → fallback sick_half
   - 補休不足 fallback 整筆給特休 (不切)

8. **週末 OT 偵測** (`test/test_weekend_ot.py`)
   - mock Slack response (e.g. 04/25 有 2 訊息) → 預期 analysis.json 出現 04/25 OT entry 含 location=在外地

9. **Backward compat tests**
   - 既有 134 test 全綠
   - 新增 ~30 unit tests (mock subprocess.run for agent-browser, mock urllib for MCP, mock state file)

10. **Manual integration**
    - 跑完整 flow: `fhr portal fetch` → `fhr analyze` → `fhr reasons` + `/fhr-reason-abstract` → `fhr portal apply --interactive` → 確認 Portal 上單據都建好

## Risks

- agent-browser daemon session 跨 subcommand 共享: 多 subcommand 連續跑可能踩到 daemon stale state → `client.py` 提供 `with PortalSession(): ...` context manager 自動 cleanup
- Portal eWorkFlow 已申請單只回第一頁 (本 session 觀察 11 筆): 若 user 申請過超過 10 筆,sync 需翻頁 → `approvals.py` 要實作分頁 (參考 attendance 翻頁 pattern)
- 餘額抓取依賴特定 iframe DOM 結構: Portal 改版會壞 → `balances.py` 加 schema 驗證 + 友善錯誤
- Reason 收集 Slack 透過 MCP server 工具,fhr 是 standalone Python: 需先確認 user 在哪個 runtime 執行(Claude Code 內 OR 純 shell)。**結論**: `lib/reasons.py` 只負責 git log + 寫 evidence 檔, Slack 部分透過 SKILL.md 指示 Claude Code 自己用 MCP 抓並合併進 evidence 檔

## Out Of Scope (留作未來)

- 多公司/多 EHR-system 支援 (目前寫死 104 EHR Portal 結構)
- 主管功能 (簽核 / 部屬出勤) — code_agent_hr 有,fhr port 進來可後續
- TUI / 桌面 GUI 整合 portal subcommand
- 自動 sync cron / daemon

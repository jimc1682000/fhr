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

---

# v2.1: 測試強化 + E2E 自動化

## Context

v2 (Phase 0-F + dry-run/screenshot patches) 已上線,303 tests,但 explorer audit 發現 coverage 有死角:

1. **CLI command handlers 0% unit-tested**: `lib/commands/portal_apply.py` (726 LOC, 22 函數) 只有 1 個 subprocess E2E test (`test_export_state_independence.py`)。21 個 private helpers (`_load_completed` / `_is_early_arrival` / `_format_entry` / `_resolve_screenshot_dir` / plan I/O 等) 全沒覆蓋。
2. **Coverage 98% 是假象**: `tools/check_coverage_threshold.py --min 90` 只看 `lib.*` + `attendance_analyzer*`,glob 排除掉 `lib/commands/*` + `lib/portal/*`。新增 1,538 LOC 的 commands/ + 700 LOC 的 portal/ 完全沒進 metric。
3. **Pre-commit hook 沒跑 unittest**: 只 lint + black + mypy。drift 要等 CI 才知道。
4. **沒有 fake agent-browser**: Portal 流程除了 lib/portal/* 的 mock-Mock-based unit test,沒辦法跑真實 subprocess + DOM 互動的整合測試。CI 不能驗 `fhr portal-apply --dry-run` 完整 pipeline。
5. **沒 Portal UI drift 偵測**: dry-run 截圖目前是 ad-hoc。Portal 改版會默默壞掉, regression 等到 user 撞到才知道。

目標: 把 coverage metric 變誠實 + commands handler 拿到 unit 保護 + 整條 portal pipeline 拿到離線 E2E + Portal UI drift 早期 alarm。

## 涵蓋範圍 (user 選 Tier 1-4 全包)

### Tier 1 — CLI handler 純函數 unit test

優先攻 `lib/commands/portal_apply.py` 的 21 個 helpers,所有純函數 + 純 I/O,不需 agent-browser:

| Target | 測什麼 | 預估 tests |
|--------|-------|----------|
| `_load_completed` | dry_run filter (本次 session 修的 bug) + submitted 過濾 + 不存在檔案 | 4 |
| `_load_plan` / `_save_plan` | 來回 round-trip + 既有 entry override + bad JSON | 3 |
| `_load_attendance_map` | 9-col txt 解析 + 缺欄位 + 不存在檔案 | 3 |
| `_auto_detect_attendance` | glob 找最新 .txt | 2 |
| `_is_early_arrival` | 在 / 不在 latest_checkin 前 + 邊界 + 無打卡 | 4 |
| `_fmt_time` / `_format_entry` | early-arrival hint 顯示 + 有/無 attendance 資料 | 3 |
| `_resolve_screenshot_dir` | dry-run 預設路徑 / 空字串 / 顯式路徑 / non-dry-run None | 4 |
| `_plan_path` / `_result_path` / `_entry_key` | filename 變換 + key 結構 | 3 |
| `_wrap_submit_iter` | completed 跳過邏輯 | 2 |
| `_resolve_base_url` | env / arg / strip suffix | 3 |

同等 pattern 給 `portal_fetch.py` (`_default_range` / `_default_out` / `_parse_date` / `_resolve_base_url`)、`portal_sync.py` / `portal_balances.py` / `export.py` / `import_.py` / `reasons.py` 命令層的 `_resolve_base_url` 與 arg parser。

預計新增 ~50 tests,純 stdlib mock。

### Tier 2 — Coverage 範圍 + pre-commit unittest gate

#### 2a. 把 `lib/commands/*` + `lib/portal/*` 納入 coverage

修 `tools/run_coverage.py` + `tools/check_coverage_threshold.py`:
- 既有 glob 排除 `lib/commands/*`、`lib/portal/*` — 拿掉
- 新增 per-package threshold (避免一次到位太痛):
  ```
  --min 85 (overall)
  --per-package lib.commands=70 lib.portal=80
  ```
- 把目前數字當基準寫進 `tools/coverage_baseline.json` (locked-in floor),CI 比對「coverage 不能比 baseline 低」,新增功能只能更高
- README badge 仍 overall %

#### 2b. Pre-commit 加 unittest hook

`.pre-commit-config.yaml` 加 local hook:
```yaml
  - repo: local
    hooks:
      - id: unittest
        name: unittest discover
        entry: python3 -m unittest discover -s test -b
        language: system
        pass_filenames: false
        stages: [pre-commit]
```

`-b` (buffer) 把噪音壓掉。`pre-commit-hooks` 的 `SKIP_TESTS=1` 不要動 — 保留 escape hatch 給急 commit。

預計 commit time 從 ~1s → 3-5s。

### Tier 3 — Fake agent-browser shim + 錄製 fixtures

#### 3a. 寫 `tools/fake_agent_browser.py`

一個 Python script 模擬 `agent-browser` CLI 介面。讀環境變數 `FHR_FAKE_AB_FIXTURE_DIR` 指向錄製 JSON,根據傳入子命令 + 參數,從 fixture pool 回對應 stdout。子命令對應:

```
open <url>          → 'fake-fixture:open:<url>.txt' 內容
get url             → 上次 open 的 url
get title           → 'fake-fixture:get-title:<hash>.txt'
eval <js>           → 'fake-fixture:eval:<sha1(js)[:10]>.json'
screenshot <path>   → cp 'fake-fixture:screenshot/<name>.png' → <path>
snapshot [-i]       → 'fake-fixture:snapshot:<seq>.txt'
click @e1           → 純 noop,記到 'fake-fixture:trace.log'
select @e1 'val'    → noop + trace
wait <ms>           → sleep 0 (test 加速)
dialog accept       → noop
close               → reset session state
```

每個 fixture 用 sha1(js) 作 key,session-scoped。Session 名 stash 在 env `FHR_FAKE_AB_SESSION`。

#### 3b. 錄製腳本 `tools/record_portal_fixtures.py`

跑一次 `fhr portal-fetch` + `portal-sync` + `portal-balances` + `portal-apply --dry-run`,讓 `PortalSession._run()` 內建 hook 把每一次 (args, stdout) 寫進 `tests/fixtures/portal_replay_v1/`。User 跑一次,fixtures checked in。Portal 改版時 user 重跑該腳本更新。

需求: `PortalSession` 加 `_FHR_RECORD_FIXTURES` env 開關,subprocess 結果 dump 到指定路徑。Recorder 邏輯不影響 production code path。

#### 3c. E2E 測試 `test/e2e_portal_replay.py`

```python
def test_dry_run_e2e_with_recorded_fixtures():
    env = {**os.environ,
           "PATH": f"{REPO}/tools:{os.environ['PATH']}",  # use fake_agent_browser
           "AGENT_BROWSER_BIN": "fake_agent_browser",
           "FHR_FAKE_AB_FIXTURE_DIR": "tests/fixtures/portal_replay_v1"}
    result = subprocess.run([sys.executable, "attendance_analyzer.py",
                             "portal-apply", "--user", "Tester",
                             "--input", "tests/fixtures/analysis-v1.json",
                             "--auto", "--dry-run", "--dry-run-pause-secs", "0",
                             "--no-sync"], env=env, ...)
    # assert exit 0, stdout 包含 "DRY RUN 結果: 加班 1/1"
    # assert tmp/dry-run-screenshots/<>/001-overtime-*.png 存在 + 非 0 byte
    # assert tmp/apply_result*.json 包含 dry_run: true
```

預計加 ~5 E2E tests。CI 可跑,本機可跑。

### Tier 4 — Screenshot baseline diff

#### 4a. Baseline 結構

`tests/fixtures/screenshot_baselines/<form_type>/<entry_signature>.png`

Entry signature = `<date>-<start>-<end>-<leave_type-or-overtime>` (例 `20260420-1830-2030-overtime.png`)。

#### 4b. Diff 邏輯 `tools/diff_screenshots.py`

```python
def diff(new_png, baseline_png, *, max_pixel_diff_ratio=0.05):
    # 用 PIL ImageChops.difference → 算非零像素比例
    # 超過 threshold → return False, 帶 diff 位置 metadata
    ...
```

依賴: Pillow (已是 fhr 既有 transitive dep via openpyxl)。

#### 4c. 整合到 Tier 3 E2E test

```python
def test_dry_run_screenshots_match_baseline():
    # tier 3 跑完 → screenshot 存在 tmp/dry-run-screenshots/<ts>/
    # 對每張 → compare with baseline
    # 任一張 diff > threshold → fail + 寫 diff image 到 tmp/diff-screenshots/
```

更新 baseline workflow: `task screenshots:update` 把最新 dry-run 截圖複製成新 baseline,git commit 標 `chore(baselines)`。

### Implementation phases (建議實作順序)

| Phase | Tier | 範圍 | 預估 |
|-------|------|------|------|
| T1 | Tier 1 | 50+ unit tests on lib/commands handlers | small |
| T2 | Tier 2 | Coverage glob 擴充 + per-package threshold + pre-commit unittest hook + baseline lock | medium |
| T3 | Tier 3 | fake_agent_browser.py + recorder + E2E test + 1-2 fixtures (overtime + leave) | medium-large |
| T4 | Tier 4 | screenshot diff helper + baseline fixtures + integrate to T3 test | small (依賴 T3) |

每 phase 獨立 PR, branched off `docs/fhr-v2-plan` (or main if v2 已 merge 進去)。建議順序 T1 → T2 → T3 → T4,但 T2/T3 可並行。

## Files To Modify / Create

### Create

- `test/test_portal_apply_helpers.py` — Tier 1 主力 (`_load_completed` / `_is_early_arrival` / `_format_entry` / `_resolve_screenshot_dir` / plan/result I/O)
- `test/test_portal_fetch_helpers.py` — Tier 1 (`_default_range` / `_default_out` / `_parse_date` / `_resolve_base_url`)
- `test/test_portal_sync_helpers.py` — Tier 1
- `test/test_portal_balances_helpers.py` — Tier 1
- `test/test_export_helpers.py`, `test/test_import_helpers.py`, `test/test_reasons_cmd_helpers.py` — Tier 1
- `tools/fake_agent_browser.py` — Tier 3
- `tools/record_portal_fixtures.py` — Tier 3
- `tools/diff_screenshots.py` — Tier 4
- `tools/coverage_baseline.json` — Tier 2
- `tests/fixtures/portal_replay_v1/` — Tier 3 fixtures dir
- `tests/fixtures/screenshot_baselines/` — Tier 4 baselines
- `test/e2e_portal_replay.py` — Tier 3 + Tier 4 整合 E2E
- `docs/testing.md` 新增 / 擴充 — 「怎麼跑/更新 fixtures」「怎麼更新 baseline」

### Modify

- `tools/run_coverage.py` — 拿掉 lib/commands lib/portal 的 exclude
- `tools/check_coverage_threshold.py` — `--per-package` flag + 讀 `coverage_baseline.json`
- `.pre-commit-config.yaml` — 加 local unittest hook
- `.github/workflows/ci.yml` — coverage 改成跑 per-package check;新增 e2e_portal_replay job
- `lib/portal/client.py` — 加 `FHR_RECORD_FIXTURES` env hook (dump subprocess args+stdout)
- `Makefile` / `Taskfile.yml` — 新增 `task test:e2e`, `task fixtures:record`, `task screenshots:update`
- `README.md` — testing 章節補 E2E 用法

### Reuse (no change)

- 既有 lib/* 邏輯
- 既有 unit test 全部繼續 work

## Verification

1. **Tier 1**: `python3 -m unittest discover -s test` → 303 → ~360 tests 全綠;`_load_completed` 帶 dry_run filter 的 test 命中本 session 修的 bug;`_is_early_arrival` 4 個邊界皆對。
2. **Tier 2**:
   - `python3 tools/check_coverage_threshold.py --per-package lib.commands=70 lib.portal=80 --min 85` → exit 0
   - 故意刪一個 portal_apply 的 helper test → coverage drop → CI fail
   - `git commit` 跑 ~3-5s (含 unittest)
3. **Tier 3**: `FHR_FAKE_AB_FIXTURE_DIR=tests/fixtures/portal_replay_v1 ./run_e2e.sh` → exit 0 + log 含「DRY RUN 結果: 加班 1/1, 請假 1/1」+ 產生 screenshot 檔
4. **Tier 4**:
   - Baseline 一致 → pass
   - 手動改 baseline 1 像素 → fail + 寫 diff image
   - `task screenshots:update` 後 git status 顯示新 PNG
5. **CI**: `.github/workflows/ci.yml` 完整跑完 (lint + unittest + coverage gate + e2e_replay + screenshot diff)

## Risks

- **fake_agent_browser fixture brittleness**: Portal 改版 → fixture 過時 → user 必須重 record。Mitigation: 寫好「重 record」工具 + doc。Tier 4 baseline diff 會早期 alarm。
- **Pre-commit 變慢**: 3-5s 對部分使用者不爽 → 提供 `SKIP_TESTS=1` escape hatch (現已存在)。
- **Per-package coverage threshold 設太緊**: 新增的 commands handlers 一開始 coverage 不會 100%,Tier 2 應該設成「不能比 baseline 低」(從目前數字鎖定 floor),不是強逼 90%。
- **Screenshot diff false positives**: Chromium 渲染微差 / 字型 → noise。Threshold 5% pixel diff + 用 hash 比較大區塊而非 pixel-exact。
- **Fixture 個資**: 錄製的 fixture 含 user id / 員工姓名,要 scrub。Recorder 加 redact step。

## Out Of Scope (本 v2.1 不做)

- Playwright/Selenium 直接驅動 (放棄 agent-browser) — 太大改動
- Real Portal scheduled E2E (GH Actions 定期跑真 Portal) — 需 secret 機密,風險高
- 視覺 regression 工具如 Percy/Chromatic — 商業服務,過度
- 端對端整合到 reasons / weekend_ot subcommand 的 E2E (本 v2.1 只覆蓋 portal-apply,reasons/weekend_ot 已有純 unit test 覆蓋 git harvester / Slack 由 skill 接手不需 E2E)

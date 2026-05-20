---
name: fhr-reason-abstract
description: |
  Turn raw Slack + git evidence (produced by `fhr reasons`) into HR-friendly
  abstract `reason` strings on an attendance-analysis/v1 JSON file.

  Triggers on user requests like:
    - "把 reason 填一填"
    - "抽象化加班理由"
    - "用 evidence.json 寫 reason"
    - "/fhr-reason-abstract"
    - "幫我整理 fhr 的 reason 欄位"

  Skill is model-agnostic — the active Claude Code session model handles
  the abstraction; no external API key required.
---

# fhr Reason Abstractor

## Goal

Read raw activity evidence + an analysis-v1 payload, then **write back**
the `reason` field on each entry with an HR-friendly one-line summary.

`fhr` itself only collects evidence (no LLM call) so this skill is where
the abstraction lives. Slack and git are merged here; later HR review
sees a tidy concept-level description ("範例文件校對", not "ABC-123
docs(example): revise sample guide").

## Inputs

1. **`tmp/reasons-evidence.json`** — produced by `fhr reasons`:
   ```jsonc
   {
     "2030/03/12": {
       "date": "2030/03/12",
       "overtime": {
         "git": [
           {"repo": "...", "sha": "...", "time": "2030-03-12T19:15:00",
            "subject": "feat(versions): add history subcommand"}
         ]
       },
       "leave": {"git": [...]}
     },
     ...
   }
   ```

2. **`tmp/analysis.json`** — the attendance-analysis/v1 payload whose
   `reason` fields you'll update.

3. **Optional config** the user may pass inline ("我們公司班表 09:30 下班 18:30"
   or "OT reason 用短一點的版本") — honor it.

## Process

For each date present in `evidence-json`:

1. Gather the **git evidence** under `overtime.git` (commits ≥
   `schedule_end`) and `leave.git` (commits earlier in the day).

2. Use Slack MCP tools (`slack_search_public_and_private`) to fetch
   that day's messages **authored by the user**:
   - Overtime evidence: `from:<@SELF> on:YYYY-MM-DD` with a timestamp
     filter `≥ schedule_end` (default 18:30; check
     `config.schedule_end` if present)
   - Leave evidence: `from:<@SELF> on:YYYY-MM-DD` with `before` ≈
     `latest_checkin + 1h` (catch "睡過頭 / 身體不適" announcements)

3. Synthesize an **abstract** reason matching the company's tone
   (see "Tone" below). Aim for ≤ 30 characters, no flowery
   marketing language. Examples from this session:
   - "範例文件校對" — instead of "ABC-123 docs(example): revise sample guide"
   - "測試資料整理" — instead of "test(example): tidy fixtures"
   - "服務權限收斂 + K8s 部署設定"
   - "處理交辦事項" — explicit fallback when neither Slack nor git
     left a clear trail

4. **Write back** the `reason` field on the matching entry in
   `analysis.json`. Match by `(date, start_time, end_time)`.
   Preserve the rest of the entry.

5. For leave entries, do NOT rewrite reasons that are already meaningful
   (`身體不適`, `WFH`, `個人事務`). Only fill blanks or generic placeholders.

## Tone

The audience is HR — they need to see what *kind* of work happened,
not the technical detail. Manager already knows the substance. Aim
for:
- Concept-level ("範例文件校對") not project-level ("example-docs v2 guide revision")
- Continuous-noun phrases, no verbs ("環境建置作業" not "建置環境")
- Don't list multiple subprojects unless they're genuinely
  distinct categories of work
- Keep punctuation simple: `+` between concepts, no parentheses

## Output

After updating `analysis.json` in place:
- Print a one-line summary per entry: `2030/03/12  [overtime]  上線部署作業`
- Save a backup of the prior `analysis.json` to `analysis.json.bak` if
  the file existed.
- DO NOT re-run `fhr export` — the user manages that themselves.

## Constraints

- Don't fetch Slack data for days that already have a meaningful reason.
- Don't hallucinate — if both Slack and git are empty for a date,
  use "處理交辦事項" or leave the existing reason alone.
- Never claim work that didn't happen (e.g. don't write "上線" if no
  deployment evidence exists).
- Respect rate limits on the Slack MCP — batch by day, not by entry.

## Trigger phrasing for the user

After running `fhr reasons --input ... --out tmp/reasons-evidence.json
--author '...'`, the user can say any of:
- `/fhr-reason-abstract`
- "把 fhr reason 填好"
- "抽象化加班/請假事由"
- "用 evidence.json 改 reason"

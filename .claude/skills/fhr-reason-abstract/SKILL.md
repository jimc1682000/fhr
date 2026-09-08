---
name: fhr-reason-abstract
description: |
  Turn raw evidence (git from `fhr reasons`, plus Slack / PJM / Calendar
  pulled here via MCP) into HR-friendly abstract `reason` strings on an
  attendance-analysis/v1 JSON file.

  Triggers on user requests like:
    - "把 reason 填一填"
    - "抽象化加班理由"
    - "用 evidence.json 寫 reason"
    - "/fhr-reason-abstract"
    - "幫我整理 fhr 的 reason 欄位"
    - "確認請假/加班原因"

  Skill is model-agnostic — the active Claude Code session model handles
  the abstraction; no external API key required.
---

# fhr Reason Abstractor

## Goal

Read raw activity evidence + an analysis-v1 payload, then **write back**
the `reason` field on each entry with an HR-friendly one-line summary.

`fhr` itself collects only git evidence (no LLM, no MCP). Everything that
needs a model or an MCP connection lives here: Slack, PJM, Calendar, and
the judgement about which evidence is claimable at all.

## Inputs

1. **`tmp/reasons-evidence.json`** — produced by `fhr reasons`:
   ```jsonc
   {
     "2026/07/29": {
       "date": "2026/07/29",
       "overtime": {
         "git": [
           {"repo": "infra-tf", "sha": "14a5b5b",
            "time": "2026-07-29T18:37:00+08:00",
            "subject": "feat(uat): add pinned-IP test",
            "host": "git.example.com", "work": true}
         ]
       },
       "leave": {"git": [...]}
     },
     "2026/08/22": {
       "date": "2026/08/22",
       "overtime": {
         "candidate": true, "weekday": "六",
         "suggested": {"start_time": "2000", "end_time": "2100",
                       "hours": 1, "location": "在外地"},
         "git": [...]
       }
     }
   }
   ```
   - `work` marks commits from a company git host (`fhr reasons --work-host`).
     **Only `work: true` commits justify an overtime claim.**
   - `candidate: true` marks a weekend/holiday the analyzer never saw
     (`fhr reasons --weekend`). These are *suggestions for a human*, never
     auto-submittable.

2. **`tmp/analysis.json`** — the attendance-analysis/v1 payload whose
   `reason` fields you'll update.

3. **Optional config** the user may pass inline ("我們公司班表 09:30 下班 18:30"
   or "OT reason 用短一點的版本") — honor it.

## Evidence sources

`fhr reasons` covers git. This skill adds the rest. Query them **per date**,
batched by day, never per entry.

### Slack

Self user id appears in the Slack MCP tool description at runtime — read it
from there, never hardcode it.

| Purpose | Query |
|---|---|
| Overtime | `from:<@SELF> on:YYYY-MM-DD`, then keep messages ≥ `schedule_end` |
| Late arrival | same query, keep messages near the check-in time |
| Weekend work | `from:<@SELF> on:YYYY-MM-DD` for each Sat/Sun in range |

Slack search has **no time-of-day modifier** — fetch the whole day and filter
client-side. Use `sort=timestamp`, `include_context=false`,
`response_format=concise` to keep results small.

A single reply inside someone else's thread still counts as work — read the
parent thread (`slack_read_thread`) before deciding an incident was trivial.

### PJM

`list_tasks` with `activeSince=YYYY-MM-DD` (add `person` to scope to the
user). Timestamps come back **UTC** — add 8h for CST before comparing to
`schedule_end`.

⚠️ `lastActivityAt` is a `max()` across updates and comments. A task touched
again later hides an earlier evening comment, so PJM can only ever *confirm*
activity, never rule it out. Phrase a negative result as "查無佐證", not
"沒有工作".

### Calendar

`list_events` for the date. Catches evening meetings that leave no commit
and no message, and morning appointments that explain a late arrival.

Run it for **every** date, not only ones where git and Slack came back
empty. A 09:00 medical appointment or an 18:00 external meeting is exactly
the evidence the other sources structurally cannot hold — waiting until
they are both empty means never running it at all.

### Jira

Do **not** call a Jira API. Ticket IDs already ride in commit subjects
(`DO-2106 refactor(...)`) — read them out of the git evidence and use them
to name the work, then abstract the ID away in the final reason.

## Process

For each date in the evidence file:

1. **Gather git evidence** — `overtime.git` (commits ≥ `schedule_end`) and
   `leave.git` (earlier in the day). Split by the `work` flag.

2. **Pull Slack, PJM and Calendar** for that date — all three, every date.
   They fail in different directions: git misses meetings and discussion,
   Slack misses anything done outside chat, PJM misses evening work on a
   task that was touched again later, Calendar misses unscheduled work.
   Skipping one because another looked sufficient is how a date ends up
   with a reason resting on a single message.

   Track which sources you actually queried per date. **"查無佐證" is a
   claim about all four sources** — never write it having checked fewer,
   and name the ones you checked when you report it.

3. **Grade the evidence before writing anything:**

   | Situation | What to write |
   |---|---|
   | Work commits, Slack, or PJM activity after `schedule_end` | Abstract them into a reason |
   | Only personal-repo commits after `schedule_end` | **Not claimable.** Report "查無佐證" and ask the user what they were doing — do not invent a reason |
   | Activity only *outside* the claimed span (18:26 messages for an 18:53–19:53 form) | Doesn't back the claim. Treat the date as unbacked, and say which timestamps you rejected and why |
   | Nothing anywhere | Same — surface it, let the user decide whether to claim or drop the entry |

   Never fill a blank overtime reason with a generic placeholder. An
   overtime form is a pay claim; an unbacked one is the user's call to make,
   not yours.

4. **For leave entries**, look for the *stated* cause rather than inferring:
   - Late arrival — search that morning for the user's own explanation
     (睡過頭 / 晚點進 / 身體不適 / 肚子 / 不舒服 / 看醫生). Quote it back.
   - Full-day absence — a Slack message that morning usually says why.
   - Sick vs personal changes the leave type and the pay, so **report what
     the evidence says and let the user choose the 假別**. Don't upgrade
     "睡過頭" into "身體不適" on your own, and don't flatten a stated illness
     into "個人事務" either.

5. **Weekend candidates** (`candidate: true`) — present them as a list with
   the work evidence attached and ask whether to claim each. Confirm the
   hours with the user; the suggested span is derived from commit
   timestamps and is only a starting point.

6. **Write back** the `reason` field on the matching entry in
   `analysis.json`. Match by `(date, start_time, end_time)`.
   Preserve the rest of the entry.

7. For leave entries, do NOT rewrite reasons that are already meaningful
   (`身體不適`, `異地辦公`, `個人事務`). Only fill blanks or generic
   placeholders like `personal matter`.

## Tone

The audience is HR — they need to see what *kind* of work happened,
not the technical detail. Manager already knows the substance. Aim for:
- Concept-level ("資安權限收斂") not project-level ("GCP key leak SA")
- Continuous-noun phrases, no verbs ("環境建置作業" not "建置環境")
- Don't list multiple subprojects unless they're genuinely
  distinct categories of work
- One reason names one kind of work. Two unrelated activities fused into a
  single abstract phrase ("大型活動維運手冊 + 稽核摘要整理") reads as noise to
  everyone, the user included — keep the one the in-span evidence supports
- Keep punctuation simple: `+` between concepts, no parentheses
- ≤ 30 characters

| Raw evidence | HR-friendly abstract |
|--------------|----------------------|
| `DO-2106 refactor(global): migrate mysql passwords to aws_secret` ×8 | `DB 密碼移轉 AWS Secrets Manager` |
| Slack 19:02 "Redis 開始維護中" → 20:24 "更新完成" | `快取節點維護作業` |
| `feat(elasticache): complete HA migration` + probe repo | `快取 HA 移轉 + 連線監控建置` |

## Output

After updating `analysis.json` in place:
- Print a one-line summary per entry: `2026/07/30  [overtime]  DB 密碼移轉 AWS Secrets Manager`
- List separately: dates with no claimable evidence, and weekend candidates
- Save a backup of the prior `analysis.json` to `analysis.json.bak` if
  the file existed.
- DO NOT re-run `fhr export` — the user manages that themselves.

## Constraints

- Don't fetch Slack/PJM data for days that already have a meaningful reason.
- **Don't hallucinate.** No evidence → say so; never claim work that didn't
  happen (don't write "上線" without deployment evidence).
- Personal-repo activity is never overtime evidence, however late it runs.
- Respect rate limits: batch by day, not by entry.
- Treat every timestamp as local unless the source says otherwise; PJM is
  the exception (UTC).

## Cross-checking what was already submitted

When comparing analyzer entries against `state.applied_forms`, match on the
**full key** `(date, start_time, end_time)` — the same key `portal-apply`
uses. Date-only matching gives false "already submitted" hits: a form whose
submitted times were adjusted by hand (e.g. an early-leave entry filed as
忘刷忘帶卡 with rounded hours) shares the date but not the key, and will
still prompt during `portal-apply`.

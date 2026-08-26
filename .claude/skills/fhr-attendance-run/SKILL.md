---
name: fhr-attendance-run
description: |
  Run one full attendance-filing wave end to end: pre-flight the Portal,
  fetch punches, analyze, collect evidence (git + Slack/PJM/Calendar),
  correct what the analyzer gets wrong, then submit the batch and verify.

  Triggers on requests like:
    - "看看 X~Y 月有什麼假勤/加班要請的"
    - "處理這個月的假勤"
    - "之前的請假申請狀況如何"
    - "幫我送這波假單"
    - "/fhr-attendance-run"

  Every judgement that costs money or credibility — leave type, whether to
  claim an unbacked overtime hour, weekend hours — stops and asks the user.
---

# fhr Attendance Run

One wave, six phases. Phases 0–3 are read-only and can run unattended.
**Phase 5 submits real HR forms and is not reversible — never enter it
without an explicit go-ahead on the exact list.**

## Prerequisites

- `agent-browser` installed; every `portal-*` call opens a **headed**
  Chromium and waits for the user to type their password. They must be at
  the keyboard and on the office network/VPN.
- All `portal-*` calls share one browser session, so sequence them in one
  sitting — one login covers the run.
- ⚠️ **`--base-url` is used as-is** (only `/` is stripped). Only the
  `EHR_URL` env path auto-strips `/LoginFOrginal.asp`. In a worktree with
  no env file, pass the *base* (`http://<host>/ehrPortal`). Passing the
  full login URL produces `.../LoginFOrginal.asp/eWorkFlow...` and a
  misleading error: 「找不到 eWorkFlow 查詢表單 refs — Portal 版本可能不相容」.

## Phase 0 — Pre-flight (read-only)

```bash
fhr portal-check --base-url <base>
```

Lists 已駁回 (decide whether to re-file) and 未處理 (still in someone's
queue — don't stack a new wave on top). Exits `1` when it finds anything;
**that is the finding, not a failure.**

Run it with no `--since` when the user asks "之前的申請狀況如何" — they
mean history, not just this wave. Use `--since YYYY/MM` only for gating.

Also pull `fhr portal-balances` here. The leave-type decisions in Phase 4
are arithmetic against these numbers, not preferences.

## Phase 1 — Fetch and analyze

```bash
fhr portal-fetch --user <user> --date-s YYYY/MM/DD --date-e YYYY/MM/DD --base-url <base>
fhr portal-sync  --user <user> --base-url <base>
fhr export --to=code-agent-hr <fetched.txt> --out tmp/analysis.json --today <today>
```

`--today` drops future auto-suggestions. Omit `--cutoff` — the
already-submitted dedup in Phase 4 is more precise than a date cutoff.

## Phase 2 — Evidence

```bash
fhr reasons --input tmp/analysis.json --out tmp/reasons-evidence.json \
    --author '<name>' --author '<work email>' --author '<personal email>' \
    --root <each repo root> \
    --work-host <company git host> --weekend
```

`--work-host` tags every commit `work: true/false`; `--weekend` surfaces
Saturdays/holidays the analyzer skips entirely. Both matter — see
`docs/reasons.md`.

Then follow **`fhr-reason-abstract`** for the MCP-only sources (Slack,
PJM, Calendar) and the evidence-grading rules. Do not duplicate that
skill's logic here.

## Phase 3 — Correct the analyzer

The analyzer works from punch records alone and gets these wrong every
month. Check each against `tmp/<fetched>.txt` before showing the user
anything.

| Check | Why | Fix |
|---|---|---|
| **Every Friday marked WFH** | It recommends WFH for *all* Fridays, including ones with punches | Punched in → not WFH. Delete if arrival is inside the flex window; convert to a late-arrival leave if not |
| **WFH hours** | Analyzer emits 9h; the submitted 異地辦公 forms are 8h, and the leave type has a monthly cap | Set 8h and check the month's total against the cap |
| **A WFH Friday inside a block of absences** | Someone on vacation is not working from home | Convert to ordinary leave |
| **A Friday's late arrival is missing** | Emitting WFH suppresses the same-day late entry | After removing a wrong WFH, re-derive the late hours from the punch |
| **early_leave** | A mid-day punch recorded as checkout looks like leaving early | If Slack/git show activity for hours *after* that timestamp, it is a missed checkout → forget-punch form, not leave |

Forget-punch is a scarce yearly allowance — check the remaining count in
the balances before spending one, and say what it saves.

## Phase 4 — Present and decide

Build one list: date, weekday, span, hours, type, reason, evidence. Mark
each already-submitted entry — **match on the full key
`(date, start_time, end_time)`**, never date alone. A form filed with
hand-adjusted times shares the date but not the key.

Then state the arithmetic and stop. Things that are the user's call:

1. Leave type per entry (paid vs unpaid vs sick changes the money)
2. Any overtime hour with no work evidence — offer to drop it
3. Weekend candidate hours
4. Anything needing an attachment (see Phase 5 limits)

Give a recommendation with each, but do not proceed on inference. When
the user answers only part of the list, apply those and re-ask the rest.

## Phase 5 — Submit

⚠️ Real HR forms. Requires explicit approval of the final list.

`portal-apply` prompts per entry via `input()`. Rather than answering
prompts, **pre-write the plan file** — it is keyed by
`{form_type}|{date}|{start}|{end}`, so order does not matter, and every
planned entry replays as「↩️ 沿用」with zero prompts:

```
tmp/analysis.json  →  tmp/apply_plan.json
{"overtime": [{"action":"submit","key":"...","reason":"..."}],
 "leave":    [{"action":"submit","key":"...","leave_type":"...",
               "reason":"...","proxy":"<name or null>"}]}
```

Rules for the plan:

- **Leave type names must match the Portal dropdown exactly.** A partial
  name that matches two options (e.g. a WFH type with 8-hour and 12-hour
  variants) makes `submit_leave` skip that entry. Take the exact strings
  from `portal-balances` output.
- `proxy` is `null` for WFH types (the form skips that field) and the
  職務代理人 for everything else.
- Add an explicit `{"action":"skip","key":...}` for any already-submitted
  entry whose times don't match — otherwise it prompts and derails the run.

Dry-run first; dry-run results are filtered out of the completed set, so
they cannot poison a later real run:

```bash
fhr portal-apply --user <user> --input tmp/analysis.json --base-url <base> \
    --proxy '<name>' --dry-run --dry-run-pause-secs 1 --no-sync
```

Then the real run. If the harness blocks the submitting call, hand the
command to the user to run themselves rather than working around it.

**Not supported: attachments.** `lib/portal/apply_forms.py` fills fields
and submits; there is no file-input handling. Any leave type the company
requires a document for (training certificates and the like) must be
filed manually — pull it out of the batch and say so.

## Phase 6 — Verify

```bash
fhr portal-sync --user <user> --base-url <base>
```

Portal is the source of truth, not the local result file. Confirm:

- Form counts rose by exactly the number submitted
- Every entry matches on type, span, hours, and reason
- No duplicates on the submitted dates, and nothing unexpected appeared

Report the approval state each form landed in, and remind the user to
re-run Phase 0 in a few days to catch rejections.

## Boundaries

- Never invent a reason to fill a blank overtime form.
- Never upgrade a stated cause into a different leave type on the user's
  behalf.
- Never submit, re-file, or withdraw anything the user has not seen.

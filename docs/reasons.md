# Reason collector + abstractor

Two-step pipeline that fills the `reason` field on each entry of an `attendance-analysis/v1` payload:

1. **`fhr reasons`** — pure Python, harvests git commit evidence per date from the configured repo roots. No LLM, no MCP, no API keys.
2. **`/fhr-reason-abstract`** — Claude Code agent skill that reads the evidence file, pulls the MCP-only sources (Slack / PJM / Calendar), then writes back an HR-friendly one-line `reason`.

The split exists because we want fhr itself to stay LLM-free and dep-light, but the abstraction step really does want a model.

## Step 1 — collect evidence

```bash
fhr reasons --input tmp/analysis.json \
    --author 'Jimmy Chen' --author 'jimmychen' \
    --out tmp/reasons-evidence.json \
    --schedule-end 18:30
```

Optional flags:

| Flag | Purpose |
|------|---------|
| `--root PATH`        | git repo root (repeatable; defaults `~/git ~/workdir ~/github`) |
| `--schedule-end HH:MM` | Threshold for splitting commits into "overtime" vs "morning leave" buckets. Match the analyzer's `AttendanceConfig.schedule_end`. |
| `--exclude-repo NAME` | Skip a repo by directory name (repeatable) |
| `--work-host HOST`   | Company git remote host (repeatable). Tags each commit `work: true/false`. |
| `--weekend`          | Also scan weekends/holidays for work-repo commits and emit overtime candidates |

The output is `{ "YYYY/MM/DD": { date, overtime: { git: [...] }, leave: { git: [...] } } }`. Commits with timestamps ≥ `schedule_end` count as overtime evidence; earlier commits count toward leave evidence (e.g. an early-morning 睡過頭 message landing as a leave reason).

### Why `--work-host` matters

Every commit carries `host` (the repo's `origin` host) and `work` (whether that host is one of `--work-host`). Personal side-project commits at 21:00 are *not* overtime evidence, and without the flag there is no way for the skill to tell them apart — it would have to re-derive the split from repo names every month.

Commit scanning uses `git log --all`, so work parked on a non-default branch still shows up; commits reachable from several refs are de-duplicated by SHA.

### Weekend / holiday candidates (`--weekend`)

The analyzer skips Saturdays, Sundays and national holidays outright — no scheduled hours means no overtime calculation — so a weekend spent on an incident leaves no trace in the payload. `--weekend` enumerates those dates inside the analysis' span and emits a candidate for any that has a work-repo commit:

```jsonc
"2026/08/22": {
  "date": "2026/08/22",
  "overtime": {
    "candidate": true,
    "weekday": "六",
    "suggested": {"start_time": "2000", "end_time": "2100", "hours": 1, "location": "在外地"},
    "git": [ ... ]
  }
}
```

Pair it with `--work-host`; without one, personal weekend hacking gets listed too (the command warns). The suggested span is derived from the first and last commit and capped at 12h — it is a starting point for a human, never an auto-submittable entry.

```bash
fhr reasons --input tmp/analysis.json --out tmp/reasons-evidence.json \
    --author 'Your Name' \
    --root ~/src/git.example.com --root ~/workdir \
    --work-host git.example.com --weekend
```

## Step 2 — agent skill

The skill at `.claude/skills/fhr-reason-abstract/SKILL.md` documents the prompt + tone rules. Trigger phrases:

- `/fhr-reason-abstract`
- "把 fhr reason 填好"
- "抽象化加班/請假事由"

The skill:

1. Reads the evidence file + the analysis file.
2. For each date, queries the MCP-only sources — Slack (`from:<@SELF> on:YYYY-MM-DD`, filtered by the same schedule_end threshold), PJM (`list_tasks activeSince=...`, remembering its timestamps are UTC), and Calendar (evening meetings that leave no commit and no message). Jira needs no API call: ticket IDs already ride in commit subjects.
3. Synthesizes a ≤ 30-char concept-level summary (`"上線部署作業"`, `"資安權限收斂與 secrets 治理"`, etc.).
4. Updates `analysis.json` in place, preserving any non-blank reason already there (`身體不適`, `WFH`).
5. Writes a `.bak` of the prior file.

## Tone reminder

The audience is HR, not engineering. The skill keeps reasons concept-level, not project-level:

| Raw evidence | HR-friendly abstract |
|--------------|----------------------|
| `DO-2562 remove geo block 上線確認` | `上線部署作業` |
| `RDS 8.4 utf8mb4 parameter group 建立` | `RDS 升版準備` |
| `GCP key leak SA 權限收斂 + gitleaks pre-commit hook` | `資安權限收斂與 secrets 治理` |

## No evidence is an answer

If no source shows work after `schedule_end` — or the only activity is in personal repos — the skill reports **查無佐證** and asks the user. It does not fill in a generic placeholder: an overtime form is a pay claim, and whether to file an unbacked one is the user's decision.

The same restraint applies to leave: report the stated cause found in Slack (睡過頭 / 身體不適 / …) and let the user pick the 假別. Sick versus personal changes both the leave type and the pay.

Note on PJM as a negative signal: `lastActivityAt` is a `max()` across a task's updates and comments, so a task touched again later hides an earlier evening comment. PJM can confirm activity, never rule it out.

# Reason collector + abstractor

Two-step pipeline that fills the `reason` field on each entry of an `attendance-analysis/v1` payload:

1. **`fhr reasons`** — pure Python, harvests git commit evidence per date from the configured repo roots. No LLM, no MCP, no API keys.
2. **`/fhr-reason-abstract`** — Claude Code agent skill that reads the evidence file, queries Slack via MCP for that day's user-authored messages, then writes back an HR-friendly one-line `reason`.

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

The output is `{ "YYYY/MM/DD": { date, overtime: { git: [...] }, leave: { git: [...] } } }`. Commits with timestamps ≥ `schedule_end` count as overtime evidence; earlier commits count toward leave evidence (e.g. an early-morning 睡過頭 message landing as a leave reason).

## Step 2 — agent skill

The skill at `.claude/skills/fhr-reason-abstract/SKILL.md` documents the prompt + tone rules. Trigger phrases:

- `/fhr-reason-abstract`
- "把 fhr reason 填好"
- "抽象化加班/請假事由"

The skill:

1. Reads the evidence file + the analysis file.
2. For each date, queries Slack via `mcp__claude_ai_Slack__slack_search_public_and_private` with `from:<@SELF> on:YYYY-MM-DD` (then filters by the schedule_end threshold same as git evidence).
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

If neither Slack nor git left evidence, the skill leaves `"處理交辦事項"` as the fallback. Never invent work.

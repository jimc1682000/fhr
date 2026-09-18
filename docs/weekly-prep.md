# Weekly prep (`tools/weekly-prep.sh`)

Stages an attendance wave on a schedule so the interactive part is short.

## What it does

Phases 0–2 of [`.claude/skills/fhr-attendance-run`](../.claude/skills/fhr-attendance-run/SKILL.md), in order:

| Step | Command | Output |
|---|---|---|
| Pre-flight | `portal-check` | `portal-check.txt` (rejected / pending forms) |
| Balances | `portal-balances` | `balances.txt` |
| Fetch | `portal-fetch` | `YYYYMM-YYYYMM-<user>-出勤資料.txt` |
| Sync | `portal-sync` | updates `applied_forms` in the state file |
| Export | `export --to=analysis-v1` | `analysis.json` |
| Evidence | `reasons --work-host … --weekend` | `reasons-evidence.json` |

Everything lands in `tmp/<YYYYMM>/` unless `--out-dir` says otherwise. The window runs from the 1st of the previous month to today, so a run early in the month still covers the tail of the last one; `portal-apply` dedups on `(date, start_time, end_time)` regardless.

## What it does not do

Phases 3–5 — correcting the analyzer's false positives, grading Slack/任務系統/Calendar evidence, writing HR-facing reasons, choosing 假別, submitting — need judgement, so they stay in a Claude Code session. Run `/fhr-attendance-run` and point it at the staged directory.

It also never logs in for you. The first `portal-*` call opens a headed Chromium and waits up to 600s for a password; the script fires a notification first so you know to go type it.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Staged, or skipped because EHR was unreachable (off the office network is normal, not a failure) |
| 2 | `EHR_URL` unset, or a bad argument |

## Environment

| Variable | Default |
|---|---|
| `EHR_URL` | read from `./.env` if unset; the `/LoginFOrginal.asp` suffix is stripped |
| `FHR_USER` | `JimmyChen` |
| `FHR_AUTHORS` | none — comma-separated `git --author` strings. Empty skips evidence collection |
| `FHR_WORK_HOST` | none — company git host, so commits get tagged `work: true/false` |

Authors and the company git host name a workplace, so they stay in the environment rather than in this repo.

## Submitting (`tools/apply-wave.sh`)

`portal-apply` takes enough flags that the one-liner soft-wraps in a terminal, and copying wrapped text turns the wrap points into real newlines. This wrapper keeps the command short:

```bash
tools/apply-wave.sh tmp/203306/analysis-wave2.json --dry-run
tools/apply-wave.sh tmp/203306/analysis-wave2.json
```

`FHR_PROXY` supplies the 職務代理人 (a colleague's name, so not in the repo); WFH leave types skip that field anyway. Everything after the analysis path passes through to `portal-apply`.

## Scheduling it (macOS launchd)

Point it at a **stable clone**, not a git worktree — worktrees get deleted.

`~/Library/LaunchAgents/com.jimc1682000.fhr-weekly-prep.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jimc1682000.fhr-weekly-prep</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>&lt;checkout&gt;/tools/weekly-prep.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>1</integer>
    <key>Hour</key><integer>11</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/fhr-weekly-prep.log</string>
  <key>StandardErrorPath</key><string>/tmp/fhr-weekly-prep.log</string>
</dict>
</plist>
```

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.jimc1682000.fhr-weekly-prep.plist
launchctl kickstart -k gui/$(id -u)/com.jimc1682000.fhr-weekly-prep   # test now
```

If the machine is asleep at the scheduled time, launchd runs the job when it next wakes — so a Monday spent away still gets staged, just later.

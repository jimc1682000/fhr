"""`fhr reasons` — write a per-date raw-evidence JSON file.

Reads an analysis-v1 payload, scans every git repo under the configured
roots for commits authored by the user on each date, and writes a
file suitable for the `.claude/skills/fhr-reason-abstract` agent skill
to merge with Slack evidence.

We deliberately stop short of doing the abstraction here — that step
wants an LLM, and the project's policy is to keep `fhr` LLM-free so
the skill can use whatever the user prefers (Sonnet, Haiku, Codex,
local ollama, etc.).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "reasons",
        help="收集每筆 OT/leave 的 git commit 證據 (Slack 部分由 agent skill 補)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  fhr reasons --input tmp/analysis.json --author 'Jimmy Chen' \\
      --exclude-repo hackthon --exclude-repo film-brain \\
      --out tmp/reasons-evidence.json

之後在 Claude Code 喚 /fhr-reason-abstract,skill 會讀 evidence.json
+ Slack MCP 補上整理過後的 HR-friendly reason 寫回 analysis.json。
        """,
    )
    parser.add_argument("--input", required=True, help="analysis-v1 JSON 路徑")
    parser.add_argument("--out", required=True, help="輸出證據 JSON")
    parser.add_argument(
        "--author",
        action="append",
        required=True,
        help="git --author 比對字串 (可重複指定多個 alias)",
    )
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        help="git repo 根目錄 (可重複,預設 ~/git ~/workdir ~/github)",
    )
    parser.add_argument(
        "--schedule-end",
        default="18:30",
        help="判斷 commit 屬於『加班』(>= 此時間) 還是『日間』(<) 的門檻",
    )
    parser.add_argument(
        "--exclude-repo",
        action="append",
        dest="exclude_repos",
        metavar="REPO_NAME",
        help="排除的 repo 目錄名 (可重複,大小寫不敏感);把個人側專案排除在工作理由證據外",
    )
    parser.add_argument(
        "--work-host",
        action="append",
        dest="work_hosts",
        metavar="HOST",
        help=(
            "公司 git remote 的 host (可重複)。每筆 commit 會標上 work=true/false，"
            "讓 skill 判斷加班理由能不能採信；也決定 --weekend 掃哪些 repo。"
        ),
    )
    parser.add_argument(
        "--weekend",
        action="store_true",
        help=(
            "另外掃描週末/假日有無公司 repo 的 commit，列為加班候選寫進證據檔。"
            "候選僅供人工判斷,不會自動變成可送的單。需搭配 --work-host。"
        ),
    )
    parser.add_argument("--debug", action="store_true", help="啟用 debug 日誌")
    return parser


def run(args: argparse.Namespace) -> None:
    from attendance_analyzer import logger
    from lib.reasons import DEFAULT_GIT_REPO_ROOTS, evidence_for_analysis
    from lib.schema import load_payload

    if args.debug:
        logger.setLevel(logging.DEBUG)

    try:
        analysis = load_payload(args.input, "attendance-analysis/v1")
    except Exception as e:
        logger.error("❌ 無法載入 analysis-v1 JSON: %s", e)
        sys.exit(2)

    roots = tuple(args.roots) if args.roots else DEFAULT_GIT_REPO_ROOTS
    exclude_repos = tuple(args.exclude_repos) if args.exclude_repos else ()
    work_hosts = tuple(args.work_hosts) if args.work_hosts else ()
    logger.info("🔍 掃描 git repos: %s", ", ".join(roots))
    logger.info("🔍 作者比對: %s", ", ".join(args.author))
    if exclude_repos:
        logger.info("🚫 排除個人 repo: %s", ", ".join(exclude_repos))
    if work_hosts:
        logger.info("🏢 公司 repo host: %s", ", ".join(work_hosts))
    elif args.weekend:
        logger.warning("⚠️ --weekend 未搭配 --work-host,個人 repo 的週末活動也會被列為候選")

    evidence = evidence_for_analysis(
        analysis,
        args.author,
        roots=roots,
        schedule_end=args.schedule_end,
        exclude_repos=exclude_repos,
        work_hosts=work_hosts,
    )

    if args.weekend:
        found = _add_weekend_candidates(
            evidence,
            analysis,
            args.author,
            roots=roots,
            exclude_repos=exclude_repos,
            work_hosts=work_hosts,
        )
        logger.info("🗓️ 週末/假日加班候選: %d 日 (僅供人工判斷,未自動列入送單)", found)

    Path(args.out).write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    total = sum(
        len(d.get("overtime", {}).get("git", [])) + len(d.get("leave", {}).get("git", []))
        for d in evidence.values()
    )
    logger.info("✅ %s (%d 日 / %d commits)", args.out, len(evidence), total)
    logger.info("ℹ️ Slack 部分由 .claude/skills/fhr-reason-abstract 自行抓 + 合併到 reason 欄位")


def _add_weekend_candidates(
    evidence: dict,
    analysis: dict,
    authors: list[str],
    *,
    roots: tuple[str, ...],
    exclude_repos: tuple[str, ...],
    work_hosts: tuple[str, ...],
) -> int:
    """Scan weekends/holidays inside the analysis' date span for work-repo
    commits and add them to `evidence` as overtime candidates.

    The analyzer skips non-working days entirely (no scheduled hours → no
    overtime calc), so a Saturday spent on an incident leaves no trace in
    the payload. These entries are flagged `candidate: True` — a human
    decides whether to claim them; nothing here is auto-submittable.

    Returns the number of candidate dates added.
    """
    from datetime import datetime

    from lib.reasons import discover_repos, is_work_repo
    from lib.weekend_ot import detect_candidates

    dates = [e["date"] for e in analysis.get("overtime", [])]
    dates += [e["date"] for e in analysis.get("leave", [])]
    if not dates:
        return 0
    parsed = sorted(datetime.strptime(d, "%Y/%m/%d").date() for d in dates)
    start, end = parsed[0], parsed[-1]
    # The analyzer emits nothing for a weekend, so the last flagged entry is
    # usually earlier than the end of the analysed period — a Sunday incident
    # after the final weekday entry would fall outside the span entirely.
    # `analysis_end` (the exporter's `--today`) is that real end when present.
    analysis_end = analysis.get("analysis_end")
    if analysis_end:
        end = max(end, datetime.strptime(analysis_end, "%Y/%m/%d").date())

    repos = discover_repos(list(roots), exclude=exclude_repos)
    if work_hosts:
        repos = [r for r in repos if is_work_repo(r, work_hosts)]

    added = 0
    for cand in detect_candidates(start, end, authors, repos=repos):
        entry = evidence.setdefault(cand["date"], {"date": cand["date"]})
        entry["overtime"] = {
            "git": cand["evidence"]["git"],
            "candidate": True,
            "weekday": cand["weekday"],
            "suggested": {
                "start_time": cand["start_time"],
                "end_time": cand["end_time"],
                "hours": cand["hours"],
                "location": cand["location"],
            },
        }
        added += 1
    return added

"""Harvest raw evidence for analyzer entries from the user's git activity.

Scans every git repo under the configured roots (default
`~/git`, `~/workdir`, `~/github`) for commits authored by the
current user on a given date. The output is consumed by a
Claude Code agent skill (`.claude/skills/fhr-reason-abstract`)
that turns the raw evidence into an HR-friendly abstracted
"reason" string.

Slack evidence is NOT collected here on purpose — `fhr` is a
standalone Python tool with no MCP runtime, and pulling Slack
data via the user's REST tokens would mean shipping a secrets
mechanism we explicitly DON'T want. Instead, the agent skill
queries Slack via its own MCP tools and merges the two
sources at write time.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_GIT_REPO_ROOTS: tuple[str, ...] = ("~/git", "~/workdir", "~/github")
DEFAULT_AUTHORS: tuple[str, ...] = ()  # caller must supply


def discover_repos(roots: Iterable[str], *, exclude: Iterable[str] = ()) -> list[Path]:
    """Return every immediate subdir of `roots` that looks like a git repo.

    We look two levels deep (`<root>/*/.git` and `<root>/*/*/.git`) — that
    matches how the user organizes work (`~/git/<repo>`, `~/github/<owner>/<repo>`).

    `exclude` is a set of repo *directory names* (basename, case-insensitive)
    to skip — used to keep personal side-projects out of work reason evidence.
    """
    excluded = {e.lower() for e in exclude}
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        root = Path(os.path.expanduser(r))
        if not root.is_dir():
            continue
        for candidate in (*root.glob("*/.git"), *root.glob("*/*/.git")):
            repo = candidate.parent.resolve()
            if repo.name.lower() in excluded:
                continue
            key = str(repo)
            if key in seen:
                continue
            seen.add(key)
            out.append(repo)
    return sorted(out)


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def commits_on(
    repo: Path,
    target: date,
    authors: Iterable[str],
    *,
    since_time: str = "00:00",
    until_offset_hours: int = 26,
) -> list[dict]:
    """Return commits in `repo` authored on `target` (local time) by any of
    `authors`. Time window: target@since_time → next-day+2h (covers late-
    night sessions that bleed past midnight).
    """
    since = f"{target.strftime('%Y-%m-%d')} {since_time}"
    end_dt = datetime.combine(target, datetime.min.time()) + timedelta(
        hours=until_offset_hours,
    )
    until = end_dt.strftime("%Y-%m-%d %H:%M")
    author_flags: list[str] = []
    for a in authors:
        author_flags.extend(["--author", a])
    if not author_flags:
        return []
    raw = _git(
        repo,
        "log",
        *author_flags,
        f"--since={since}",
        f"--until={until}",
        "--pretty=format:%H%x00%aI%x00%s",
    )
    out: list[dict] = []
    for line in raw.splitlines():
        parts = line.split("\x00")
        if len(parts) != 3:
            continue
        sha, iso, subject = parts
        out.append({"repo": repo.name, "sha": sha[:10], "time": iso, "subject": subject})
    return out


def harvest_dates(
    dates: Iterable[date],
    authors: Iterable[str],
    *,
    roots: Iterable[str] = DEFAULT_GIT_REPO_ROOTS,
    after_time: str = "00:00",
    exclude_repos: Iterable[str] = (),
) -> dict[str, list[dict]]:
    """For each date, scan every repo and collect commits.

    `after_time` is "HH:MM" — used to filter commits earlier than the user's
    schedule_end when only evening overtime evidence is wanted. Default 00:00
    (no time filter) so callers explicitly opt in.

    `exclude_repos` skips repos by directory name (e.g. personal side-projects).
    """
    repos = discover_repos(list(roots), exclude=exclude_repos)
    out: dict[str, list[dict]] = {}
    for d in dates:
        rows: list[dict] = []
        for repo in repos:
            rows.extend(commits_on(repo, d, authors, since_time=after_time))
        rows.sort(key=lambda r: r["time"])
        out[d.strftime("%Y-%m-%d")] = rows
    return out


def evidence_for_analysis(
    analysis: dict,
    authors: Iterable[str],
    *,
    roots: Iterable[str] = DEFAULT_GIT_REPO_ROOTS,
    schedule_end: str = "18:30",
    exclude_repos: Iterable[str] = (),
) -> dict[str, dict]:
    """Build a per-date evidence dict from an attendance-analysis/v1 payload.

    For each date that appears in `overtime` or `leave` we attach:
      - git: list of commits (overtime → after schedule_end, leave → morning)
      - dates_seen: where this entry came from (overtime / leave / both)
    """
    overtime_dates = {e["date"] for e in analysis.get("overtime", [])}
    leave_dates = {e["date"] for e in analysis.get("leave", [])}
    all_dates = sorted(overtime_dates | leave_dates)
    parsed_dates = [datetime.strptime(d, "%Y/%m/%d").date() for d in all_dates]

    # Two harvests: one window for overtime (≥ schedule_end), one for leave
    # (whole day). We avoid double-scanning by gathering everything once.
    raw = harvest_dates(parsed_dates, authors, roots=roots, exclude_repos=exclude_repos)

    sh, sm = (int(x) for x in schedule_end.split(":"))
    threshold_minutes = sh * 60 + sm

    out: dict[str, dict] = {}
    for d_str, slash_str in zip(
        (d.strftime("%Y-%m-%d") for d in parsed_dates),
        all_dates,
        strict=True,
    ):
        commits = raw.get(d_str, [])
        overtime_commits = [c for c in commits if _commit_minutes_local(c) >= threshold_minutes]
        leave_commits = [c for c in commits if _commit_minutes_local(c) < threshold_minutes]
        entry = {"date": slash_str}
        if slash_str in overtime_dates:
            entry["overtime"] = {"git": overtime_commits}
        if slash_str in leave_dates:
            entry["leave"] = {"git": leave_commits}
        out[slash_str] = entry
    return out


def _commit_minutes_local(commit: dict) -> int:
    """Convert the commit's local-time ISO timestamp to (h*60+m). Fall back
    to a sentinel that always classifies as "leave" when parsing fails."""
    iso = commit.get("time", "")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return -1
    return dt.hour * 60 + dt.minute

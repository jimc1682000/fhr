"""Tests for `lib/reasons.py`."""

import os
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from lib.reasons import (
    _commit_minutes_local,
    commits_on,
    discover_repos,
    evidence_for_analysis,
)


def _make_repo(path: Path) -> None:
    """Init a minimal git repo. Author is supplied per-commit via env vars
    so pre-commit's stashed environment can't shadow it via global gitconfig."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


def _commit(
    path: Path,
    subject: str,
    when: str,
    *,
    author_name: str = "Tester McTest",
    author_email: str = "tester@example.com",
) -> None:
    f = path / "x"
    f.write_text(subject)
    subprocess.run(["git", "add", "x"], cwd=path, check=True)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    subprocess.run(
        ["git", "commit", "-q", "-m", subject], cwd=path, env=env, check=True
    )


class TestDiscoverRepos(unittest.TestCase):
    def test_finds_one_and_two_levels_deep(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root / "alpha")
            _make_repo(root / "owner" / "beta")
            repos = discover_repos([str(root)])
            names = sorted(r.name for r in repos)
            self.assertEqual(names, ["alpha", "beta"])

    def test_missing_root_is_skipped(self):
        self.assertEqual(discover_repos(["/no/such/path/__missing__"]), [])

    def test_exclude_skips_named_repos_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root / "deployer-tf")
            _make_repo(root / "hackthon")
            _make_repo(root / "owner" / "Film-Brain")
            repos = discover_repos([str(root)], exclude=["hackthon", "film-brain"])
            names = sorted(r.name for r in repos)
            self.assertEqual(names, ["deployer-tf"])


class TestCommitsOn(unittest.TestCase):
    def test_returns_matching_author_only(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            _make_repo(repo)
            _commit(repo, "mine", "2026-04-20T18:50:00")
            # Change author for the next commit
            _commit(
                repo,
                "not mine",
                "2026-04-20T19:00:00",
                author_name="Other Person",
                author_email="other@example.com",
            )

            rows = commits_on(repo, date(2026, 4, 20), authors=["Tester McTest"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["subject"], "mine")

    def test_filters_by_date(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            _make_repo(repo)
            _commit(repo, "today", "2026-04-20T18:50:00")
            _commit(repo, "tomorrow", "2026-04-21T09:00:00")
            rows = commits_on(repo, date(2026, 4, 20), authors=["Tester McTest"])
            subjects = [r["subject"] for r in rows]
            self.assertIn("today", subjects)
            self.assertNotIn("tomorrow", subjects)

    def test_no_authors_no_query(self):
        # Empty authors → empty result, no git invocation
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(commits_on(Path(d), date(2026, 4, 20), authors=[]), [])


class TestCommitMinutesLocal(unittest.TestCase):
    def test_parses_iso(self):
        self.assertEqual(
            _commit_minutes_local({"time": "2026-04-20T18:30:00"}), 18 * 60 + 30
        )

    def test_handles_garbage(self):
        self.assertEqual(_commit_minutes_local({"time": "bad"}), -1)
        self.assertEqual(_commit_minutes_local({}), -1)


class TestEvidenceForAnalysis(unittest.TestCase):
    def test_split_by_schedule_end(self):
        analysis = {
            "schema_version": "attendance-analysis/v1",
            "overtime": [
                {
                    "date": "2026/04/20",
                    "start_time": "1830",
                    "end_time": "2030",
                    "hours": 2,
                    "location": "在辦公室",
                    "reason": "x",
                }
            ],
            "leave": [
                {
                    "date": "2026/04/20",
                    "start_time": "0930",
                    "end_time": "1130",
                    "hours": 2,
                    "type_hint": "late",
                    "reason": "x",
                }
            ],
        }
        fake = {
            "2026-04-20": [
                {
                    "repo": "x",
                    "sha": "abc",
                    "time": "2026-04-20T10:36:00",
                    "subject": "睡過頭 — should land in leave bucket",
                },
                {
                    "repo": "y",
                    "sha": "def",
                    "time": "2026-04-20T19:00:00",
                    "subject": "DO-2562 remove geo block — should land in overtime",
                },
            ]
        }
        with mock.patch("lib.reasons.harvest_dates", return_value=fake):
            out = evidence_for_analysis(analysis, ["Tester"], schedule_end="18:30")
        e = out["2026/04/20"]
        ot_subjects = [c["subject"] for c in e["overtime"]["git"]]
        lv_subjects = [c["subject"] for c in e["leave"]["git"]]
        self.assertIn("DO-2562 remove geo block — should land in overtime", ot_subjects)
        self.assertIn("睡過頭 — should land in leave bucket", lv_subjects)

    def test_no_authors_returns_empty(self):
        analysis = {
            "schema_version": "attendance-analysis/v1",
            "overtime": [],
            "leave": [],
        }
        out = evidence_for_analysis(analysis, [])
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()

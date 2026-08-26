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
    is_work_repo,
    remote_host,
)
from lib.weekend_ot import detect_candidates

# git exports these to hooks. When the suite runs from a pre-commit hook
# inside a worktree they point at the REAL repo, so an un-scrubbed subprocess
# env makes `git init` flip the shared config and `git commit` land on the
# live branch. Strip them from every git call this module makes.
_GIT_ENV_LEAKS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")


def _clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_LEAKS}
    env.update(extra)
    return env


def _make_repo(path: Path) -> None:
    """Init a minimal git repo. Author is supplied per-commit via env vars
    so pre-commit's stashed environment can't shadow it via global gitconfig."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, env=_clean_env())


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
    env = _clean_env(
        **{
            "GIT_AUTHOR_NAME": author_name,
            "GIT_AUTHOR_EMAIL": author_email,
            "GIT_COMMITTER_NAME": author_name,
            "GIT_COMMITTER_EMAIL": author_email,
            "GIT_AUTHOR_DATE": when,
            "GIT_COMMITTER_DATE": when,
        }
    )
    subprocess.run(["git", "add", "x"], cwd=path, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", subject], cwd=path, env=env, check=True)


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
        self.assertEqual(_commit_minutes_local({"time": "2026-04-20T18:30:00"}), 18 * 60 + 30)

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


class TestRemoteHost(unittest.TestCase):
    def setUp(self):
        remote_host.cache_clear()

    def _repo_with_remote(self, tmp: str, url: str) -> Path:
        repo = Path(tmp) / "r"
        _make_repo(repo)
        subprocess.run(
            ["git", "remote", "add", "origin", url],
            cwd=repo,
            check=True,
            env=_clean_env(),
        )
        return repo

    def test_parses_scp_style_ssh_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(tmp, "git@git.example.com:devops/deployer.git")
            self.assertEqual(remote_host(str(repo)), "git.example.com")

    def test_parses_https_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(tmp, "https://github.com/owner/repo.git")
            self.assertEqual(remote_host(str(repo)), "github.com")

    def test_no_remote_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            self.assertEqual(remote_host(str(repo)), "")

    def test_is_work_repo_matches_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(tmp, "git@git.example.com:devops/x.git")
            self.assertTrue(is_work_repo(repo, ["git.example.com"]))
            self.assertFalse(is_work_repo(repo, ["other.host"]))

    def test_empty_work_hosts_means_everything_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo_with_remote(tmp, "https://github.com/owner/repo.git")
            self.assertTrue(is_work_repo(repo, []))


class TestCommitsOnBranchCoverage(unittest.TestCase):
    """`git log` without --all only walks HEAD — commits parked on another
    branch were silently missing from the evidence file."""

    def setUp(self):
        remote_host.cache_clear()

    def test_finds_commit_on_non_head_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "on main", "2026-07-29T10:00:00+08:00")
            subprocess.run(
                ["git", "checkout", "-q", "-b", "side"], cwd=repo, check=True, env=_clean_env()
            )
            _commit(repo, "on side branch", "2026-07-29T18:37:00+08:00")
            subprocess.run(["git", "checkout", "-q", "-"], cwd=repo, check=True, env=_clean_env())

            got = commits_on(repo, date(2026, 7, 29), ["Tester McTest"])
            subjects = sorted(c["subject"] for c in got)
            self.assertEqual(subjects, ["on main", "on side branch"])

    def test_commit_reachable_from_two_refs_appears_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "shared", "2026-07-29T18:37:00+08:00")
            subprocess.run(["git", "branch", "dup"], cwd=repo, check=True, env=_clean_env())
            got = commits_on(repo, date(2026, 7, 29), ["Tester McTest"])
            self.assertEqual(len(got), 1)

    def test_tags_host_and_work_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            subprocess.run(
                ["git", "remote", "add", "origin", "git@git.example.com:devops/x.git"],
                cwd=repo,
                check=True,
                env=_clean_env(),
            )
            _commit(repo, "work thing", "2026-07-29T18:37:00+08:00")

            work = commits_on(
                repo, date(2026, 7, 29), ["Tester McTest"], work_hosts=["git.example.com"]
            )
            self.assertEqual(work[0]["host"], "git.example.com")
            self.assertTrue(work[0]["work"])

            remote_host.cache_clear()
            personal = commits_on(
                repo, date(2026, 7, 29), ["Tester McTest"], work_hosts=["elsewhere.com"]
            )
            self.assertFalse(personal[0]["work"])


class TestWeekendCandidateClamp(unittest.TestCase):
    def test_all_day_span_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "early", "2026-08-22T00:02:00+08:00")
            _commit(repo, "late", "2026-08-22T23:50:00+08:00")

            got = detect_candidates(
                date(2026, 8, 22), date(2026, 8, 22), ["Tester McTest"], repos=[repo]
            )
            self.assertEqual(len(got), 1)
            self.assertLessEqual(got[0]["hours"], 12)
            self.assertEqual(got[0]["weekday"], "六")

    def test_weekday_with_commits_is_not_a_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "weekday work", "2026-08-19T19:00:00+08:00")
            got = detect_candidates(
                date(2026, 8, 19), date(2026, 8, 19), ["Tester McTest"], repos=[repo]
            )
            self.assertEqual(got, [])

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


def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _clean_env(**extra: str) -> dict[str, str]:
    """`_git_env()` plus per-call overrides."""
    return {**_git_env(), **extra}


def _make_repo(path: Path) -> None:
    """Init a minimal git repo. Author is supplied per-commit via env vars
    so pre-commit's stashed environment can't shadow it via global gitconfig."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, env=_git_env(), check=True)


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
    subprocess.run(["git", "add", "x"], cwd=path, env=_git_env(), check=True)
    env = {
        **_git_env(),
        "GIT_AUTHOR_NAME": author_name,
        "GIT_AUTHOR_EMAIL": author_email,
        "GIT_COMMITTER_NAME": author_name,
        "GIT_COMMITTER_EMAIL": author_email,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
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

    def test_finds_ghq_layout_three_levels_deep(self):
        # ghq clones land at <root>/<host>/<owner>/<repo>.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root / "git.example.com" / "team" / "example-repo")
            repos = discover_repos([str(root)])
            self.assertEqual([r.name for r in repos], ["example-repo"])

    def test_does_not_recurse_past_the_scan_depth(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root / "a" / "b" / "c" / "too-deep")
            self.assertEqual(discover_repos([str(root)]), [])

    def test_missing_root_is_skipped(self):
        self.assertEqual(discover_repos(["/no/such/path/__missing__"]), [])

    def test_exclude_skips_named_repos_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_repo(root / "example-repo")
            _make_repo(root / "scratch-repo")
            _make_repo(root / "owner" / "Example-Side-Project")
            repos = discover_repos([str(root)], exclude=["scratch-repo", "example-side-project"])
            names = sorted(r.name for r in repos)
            self.assertEqual(names, ["example-repo"])


class TestCommitsOn(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, _git_env(), clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fixture_git_does_not_modify_inherited_repo(self):
        with tempfile.TemporaryDirectory() as d:
            sentinel = Path(d) / "sentinel"
            _make_repo(sentinel)
            _commit(sentinel, "sentinel", "2033-06-20T18:00:00")
            env = _git_env()
            worktree = Path(d) / "wt"
            subprocess.run(
                ["git", "worktree", "add", "-q", "-b", "wt", str(worktree)],
                cwd=sentinel,
                env=env,
                check=True,
            )
            git_dir = sentinel / ".git" / "worktrees" / "wt"
            self.assertTrue(git_dir.is_dir())

            def snapshot():
                return {
                    "config": (sentinel / ".git" / "config").read_bytes(),
                    "core.bare": subprocess.check_output(
                        ["git", "config", "--get", "core.bare"], cwd=sentinel, env=env
                    ).strip(),
                    "refs": subprocess.check_output(
                        ["git", "for-each-ref", "--format=%(refname) %(objectname)"],
                        cwd=sentinel,
                        env=env,
                    ),
                    "commit_count": subprocess.check_output(
                        ["git", "rev-list", "--all", "--count"], cwd=sentinel, env=env
                    ).strip(),
                }

            before = snapshot()
            self.assertEqual(before["core.bare"], b"false")
            self.assertEqual(before["commit_count"], b"1")
            repo = Path(d) / "fixture"
            try:
                # linked worktree 的 GIT_DIR 才能重現主 repo 被改成 bare 的事故。
                with mock.patch.dict(
                    os.environ,
                    {"GIT_DIR": str(git_dir)},
                ):
                    _make_repo(repo)
                    _commit(repo, "fixture", "2033-06-20T18:50:00")
            finally:
                after = snapshot()
                for key in before:
                    with self.subTest(invariant=key):
                        self.assertEqual(after[key], before[key])
            rows = commits_on(repo, date(2033, 6, 20), authors=["Tester McTest"])
            self.assertEqual([r["subject"] for r in rows], ["fixture"])

    def test_returns_matching_author_only(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            _make_repo(repo)
            _commit(repo, "mine", "2033-06-20T18:50:00")
            # Change author for the next commit
            _commit(
                repo,
                "not mine",
                "2033-06-20T19:00:00",
                author_name="Other Person",
                author_email="other@example.com",
            )

            rows = commits_on(repo, date(2033, 6, 20), authors=["Tester McTest"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["subject"], "mine")

    def test_filters_by_date(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d) / "r"
            _make_repo(repo)
            _commit(repo, "today", "2033-06-20T18:50:00")
            _commit(repo, "tomorrow", "2033-06-21T09:00:00")
            rows = commits_on(repo, date(2033, 6, 20), authors=["Tester McTest"])
            subjects = [r["subject"] for r in rows]
            self.assertIn("today", subjects)
            self.assertNotIn("tomorrow", subjects)

    def test_no_authors_no_query(self):
        # Empty authors → empty result, no git invocation
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(commits_on(Path(d), date(2033, 6, 20), authors=[]), [])


class TestCommitsOnEnvironment(unittest.TestCase):
    def test_setup_isolates_queries_and_restores_inherited_environment(self):
        with tempfile.TemporaryDirectory() as d:
            inherited = {"GIT_DIR": str(Path(d) / "outer.git")}
            with mock.patch.dict(os.environ, inherited):
                case = TestCommitsOn("test_returns_matching_author_only")
                result = unittest.TestResult()
                case.run(result)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)
                self.assertEqual(os.environ["GIT_DIR"], inherited["GIT_DIR"])


class TestCommitMinutesLocal(unittest.TestCase):
    def test_parses_iso(self):
        self.assertEqual(_commit_minutes_local({"time": "2033-06-20T18:30:00"}), 18 * 60 + 30)

    def test_handles_garbage(self):
        self.assertEqual(_commit_minutes_local({"time": "bad"}), -1)
        self.assertEqual(_commit_minutes_local({}), -1)


class TestEvidenceForAnalysis(unittest.TestCase):
    def test_split_by_schedule_end(self):
        analysis = {
            "schema_version": "attendance-analysis/v1",
            "overtime": [
                {
                    "date": "2033/06/20",
                    "start_time": "1830",
                    "end_time": "2030",
                    "hours": 2,
                    "location": "在辦公室",
                    "reason": "x",
                }
            ],
            "leave": [
                {
                    "date": "2033/06/20",
                    "start_time": "0930",
                    "end_time": "1130",
                    "hours": 2,
                    "type_hint": "late",
                    "reason": "x",
                }
            ],
        }
        fake = {
            "2033-06-20": [
                {
                    "repo": "x",
                    "sha": "abc",
                    "time": "2033-06-20T10:36:00",
                    "subject": "睡過頭 — should land in leave bucket",
                },
                {
                    "repo": "y",
                    "sha": "def",
                    "time": "2033-06-20T19:00:00",
                    "subject": "ABC-123 docs(example): revise sample guide — should land in overtime",
                },
            ]
        }
        with mock.patch("lib.reasons.harvest_dates", return_value=fake):
            out = evidence_for_analysis(analysis, ["Tester"], schedule_end="18:30")
        e = out["2033/06/20"]
        ot_subjects = [c["subject"] for c in e["overtime"]["git"]]
        lv_subjects = [c["subject"] for c in e["leave"]["git"]]
        self.assertIn(
            "ABC-123 docs(example): revise sample guide — should land in overtime", ot_subjects
        )
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
            repo = self._repo_with_remote(tmp, "git@git.example.com:devops/app.git")
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
            _commit(repo, "on main", "2030-03-12T10:00:00+08:00")
            subprocess.run(
                ["git", "checkout", "-q", "-b", "side"], cwd=repo, check=True, env=_clean_env()
            )
            _commit(repo, "on side branch", "2030-03-12T19:15:00+08:00")
            subprocess.run(["git", "checkout", "-q", "-"], cwd=repo, check=True, env=_clean_env())

            got = commits_on(repo, date(2030, 3, 12), ["Tester McTest"])
            subjects = sorted(c["subject"] for c in got)
            self.assertEqual(subjects, ["on main", "on side branch"])

    def test_commit_reachable_from_two_refs_appears_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "shared", "2030-03-12T19:15:00+08:00")
            subprocess.run(["git", "branch", "dup"], cwd=repo, check=True, env=_clean_env())
            got = commits_on(repo, date(2030, 3, 12), ["Tester McTest"])
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
            _commit(repo, "work thing", "2030-03-12T19:15:00+08:00")

            work = commits_on(
                repo, date(2030, 3, 12), ["Tester McTest"], work_hosts=["git.example.com"]
            )
            self.assertEqual(work[0]["host"], "git.example.com")
            self.assertTrue(work[0]["work"])

            remote_host.cache_clear()
            personal = commits_on(
                repo, date(2030, 3, 12), ["Tester McTest"], work_hosts=["elsewhere.com"]
            )
            self.assertFalse(personal[0]["work"])


class TestWeekendCandidateClamp(unittest.TestCase):
    def test_all_day_span_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "early", "2030-03-16T00:02:00+08:00")
            _commit(repo, "late", "2030-03-16T23:50:00+08:00")

            got = detect_candidates(
                date(2030, 3, 16), date(2030, 3, 16), ["Tester McTest"], repos=[repo]
            )
            self.assertEqual(len(got), 1)
            self.assertLessEqual(got[0]["hours"], 12)
            self.assertEqual(got[0]["weekday"], "六")

    def test_weekday_with_commits_is_not_a_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            _make_repo(repo)
            _commit(repo, "weekday work", "2030-03-13T19:00:00+08:00")
            got = detect_candidates(
                date(2030, 3, 13), date(2030, 3, 13), ["Tester McTest"], repos=[repo]
            )
            self.assertEqual(got, [])

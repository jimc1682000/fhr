"""End-to-end Portal-apply pipeline via fake agent-browser shim (Tier 3).

Exercises the full subprocess invocation of `attendance_analyzer.py
portal-apply --auto --dry-run` against `tools/fake_agent_browser.py`,
which replays canned responses from `tests/fixtures/portal_replay_v1/`.

This catches CLI/wiring regressions that mock-based unit tests miss —
e.g. arg-parser drift, env-var loading, JSON I/O edges, the integration
between PortalSession + apply_forms + state cache.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FAKE_AB = REPO_ROOT / "tools" / "fake_agent_browser.py"
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "portal_replay_v1"
ANALYSIS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "analysis-e2e-v1.json"


class TestPortalApplyDryRunReplay(unittest.TestCase):
    """`fhr portal-apply --auto --dry-run --no-sync --overtime-only` E2E."""

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.analysis = Path(self.workdir) / "tmp" / "analysis.json"
        self.analysis.parent.mkdir(parents=True)
        shutil.copyfile(ANALYSIS_FIXTURE, self.analysis)
        # Custom state file path so we don't touch the dev's real one
        self.state_path = Path(self.workdir) / "state.json"
        # Reset fake-AB session state for this run
        for state_file in FIXTURE_DIR.glob("state/*.json"):
            state_file.unlink()

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def _env(self) -> dict:
        return {
            **os.environ,
            "AGENT_BROWSER_BIN": str(FAKE_AB),
            "FHR_FAKE_AB_FIXTURE_DIR": str(FIXTURE_DIR),
            "FHR_FAKE_AB_TRACE": "1",
            "FHR_FAKE_AB_LOG_DIR": self.workdir,
            "FHR_STATE_FILE": str(self.state_path),
            # The .env file in the repo has the real Portal URL — pass it
            # explicitly so we don't depend on .env being present
            "EHR_URL": "http://fake.local/ehrPortal",
        }

    def _run(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "attendance_analyzer.py",
             "portal-apply",
             "--user", "Tester",
             "--input", str(self.analysis),
             "--auto", "--dry-run", "--dry-run-pause-secs", "0",
             "--no-sync", "--overtime-only",
             *extra],
            cwd=REPO_ROOT, env=self._env(),
            capture_output=True, text=True, check=False,
        )

    def test_dry_run_overtime_succeeds(self):
        result = self._run()
        # Exit 0 + DRY RUN result line
        self.assertEqual(
            result.returncode, 0,
            msg=f"stderr: {result.stderr}\nstdout: {result.stdout}",
        )
        self.assertIn("DRY RUN", result.stdout + result.stderr)
        self.assertIn("加班 1/1", result.stdout + result.stderr)

    def test_result_file_marks_dry_run(self):
        self._run()
        result_path = Path(self.workdir) / "tmp" / "apply_result.json"
        self.assertTrue(result_path.is_file(), "apply_result.json missing")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["overtime"]), 1)
        entry = payload["overtime"][0]
        self.assertTrue(entry["submitted"])
        self.assertTrue(entry["dry_run"])

    def test_state_cache_not_polluted(self):
        self._run()
        # Either no state file written, or applied_forms is empty.
        if not self.state_path.exists():
            return
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        applied = state.get("users", {}).get("Tester", {}).get("applied_forms", {})
        # OT list should be empty / missing — dry-run must NOT write here.
        self.assertFalse(applied.get("overtime"),
                         "applied_forms.overtime polluted by dry-run")

    def test_screenshot_emitted(self):
        # Screenshots default under cwd/tmp/dry-run-screenshots/<ts>/
        self._run(
            "--screenshot-dir", str(Path(self.workdir) / "shots"),
        )
        shots = list((Path(self.workdir) / "shots").glob("*.png"))
        self.assertGreaterEqual(len(shots), 1, "no screenshot copied")
        # Canned PNG was 263KB; just check non-zero.
        self.assertGreater(shots[0].stat().st_size, 0)

    def test_screenshot_opt_out(self):
        self._run("--screenshot-dir", "")
        shots = list((Path(self.workdir) / "shots").glob("*.png"))
        self.assertEqual(shots, [], "screenshot dir should be disabled")


try:
    from PIL import Image  # noqa: F401
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


BASELINE_DIR = REPO_ROOT / "tests" / "fixtures" / "screenshot_baselines" / "dry-run"


@unittest.skipUnless(_HAS_PIL, "Pillow not installed")
class TestPortalApplyScreenshotsMatchBaseline(unittest.TestCase):
    """Tier 4 integration: dry-run screenshots stay within threshold of baseline.

    Today the canned PNG is the same as the baseline (fake_agent_browser
    just copies it back), so the diff is 0. Once we have a recorder + real
    Portal screenshots, drift will surface here.
    """

    def setUp(self):
        self.workdir = tempfile.mkdtemp()
        self.analysis = Path(self.workdir) / "tmp" / "analysis.json"
        self.analysis.parent.mkdir(parents=True)
        shutil.copyfile(ANALYSIS_FIXTURE, self.analysis)
        self.shot_dir = Path(self.workdir) / "shots"
        for state_file in FIXTURE_DIR.glob("state/*.json"):
            state_file.unlink()

    def tearDown(self):
        shutil.rmtree(self.workdir, ignore_errors=True)

    def test_baseline_diff_under_threshold(self):
        env = {
            **os.environ,
            "AGENT_BROWSER_BIN": str(FAKE_AB),
            "FHR_FAKE_AB_FIXTURE_DIR": str(FIXTURE_DIR),
            "FHR_STATE_FILE": str(Path(self.workdir) / "state.json"),
            "EHR_URL": "http://fake.local/ehrPortal",
        }
        subprocess.run(
            [sys.executable, "attendance_analyzer.py", "portal-apply",
             "--user", "Tester", "--input", str(self.analysis),
             "--auto", "--dry-run", "--dry-run-pause-secs", "0",
             "--no-sync", "--overtime-only",
             "--screenshot-dir", str(self.shot_dir)],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=True,
        )
        from tools.diff_screenshots import diff
        shots = sorted(self.shot_dir.glob("*-overtime-*.png"))
        self.assertEqual(len(shots), 1, "expected exactly one overtime screenshot")
        baseline = BASELINE_DIR / "overtime-20260420-1830-2030.png"
        self.assertTrue(baseline.is_file(),
                        f"missing baseline: {baseline}")
        res = diff(str(shots[0]), str(baseline))
        self.assertTrue(
            res.is_within(0.05),
            f"screenshot drift beyond 5%: diff_ratio={res.diff_ratio}, "
            f"size_mismatch={res.size_mismatch}",
        )


if __name__ == "__main__":
    unittest.main()

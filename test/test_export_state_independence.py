"""Regression for Codex review P2: `fhr export` should ignore the
analyzer's processed-date state cache by default.

Before the fix, calling `export` on a file whose date range was already
recorded in `attendance_state.json` (e.g. by a prior `analyze` run)
returned an empty payload — the analyzer treated the records as
already-processed and emitted zero issues. portal-apply downstream
then had nothing to act on.

The fix: export defaults to full analysis. Users who want incremental
behavior pass `--incremental` explicitly.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SAMPLE = (
    "應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n"
    "2026/04/20 09:30\t2026/04/20 11:26\t上班\t1\t刷卡匯入\t遲到\t\t\t\n"
    "2026/04/20 18:30\t2026/04/20 21:05\t下班\t1\t刷卡匯入\t\t\t\t\n"
)


class TestExportStateIndependence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.workdir = Path(self.tmpdir)
        # Use a named file so the analyzer's filename parser identifies the user
        self.attendance = self.workdir / "202604-Tester-出勤資料.txt"
        self.attendance.write_text(SAMPLE, encoding="utf-8")
        self.out = self.workdir / "analysis.json"
        # Custom state file so we don't touch the dev's real one
        self.state = self.workdir / "state.json"
        self.env = {**os.environ, "FHR_STATE_FILE": str(self.state)}

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args: str) -> str:
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "attendance_analyzer.py", *args],
            cwd=repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(f"command failed: {' '.join(args)}\nstderr: {result.stderr}")
        return result.stdout

    def test_export_emits_entries_even_after_analyze_marked_dates(self):
        # 1. Pre-run analyze (the legacy form) to populate the state cache
        self._run(str(self.attendance), "csv")

        # 2. Now export — should still emit the 04/20 OT + leave entries
        self._run(
            "export",
            "--to=code-agent-hr",
            str(self.attendance),
            "--out",
            str(self.out),
        )
        payload = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "attendance-analysis/v1")
        self.assertGreaterEqual(
            len(payload["overtime"]), 1, "export must emit OT despite state cache"
        )
        # 04/20 11:26 上班 is a clear 遲到 → leave with type_hint=late
        self.assertTrue(any(e.get("type_hint") == "late" for e in payload["leave"]))


if __name__ == "__main__":
    unittest.main()

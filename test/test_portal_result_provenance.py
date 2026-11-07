"""結果來源與原子寫入驗收，所有送單走 FakePortal。"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.commands import portal_apply as apply
from lib.portal import apply_forms as af
from lib.portal.client import AgentBrowserMissing, LoginTimeout
from test import test_portal_apply_helpers as auto_helpers
from test.test_portal_submit_reliability import ENTRY, FakePortal

RUN_ID = "12345678-1234-4234-8234-123456789abc"


class TestResultProvenance(unittest.TestCase):
    def setUp(self):
        self.fixture = auto_helpers.TestRunAutoMode()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.directory = Path(self.fixture.tmp.name)
        self.path = apply._result_path(str(self.fixture.analysis_path))
        self.result = {
            "run_id": RUN_ID,
            "completed": True,
            "overtime": [],
            "leave": [{"entry": ENTRY, "status": "confirmed", "submitted": True, "dry_run": False}],
        }
        self.path.write_text(json.dumps(self.result))
        self.home = mock.patch.dict(os.environ, {"HOME": str(self.directory)})
        self.home.start()
        self.addCleanup(self.home.stop)

    def run_apply(self, args, **patches):
        output = io.StringIO()
        forms = []
        real_batch = af.batch_submit

        def fake_batch(_portal, base, ot, lv, **kwargs):
            return real_batch(FakePortal(forms), base, ot, lv, **kwargs)

        with contextlib.ExitStack() as stack:
            for target, value in patches.items():
                stack.enter_context(mock.patch(target, **value))
            stack.enter_context(contextlib.redirect_stdout(output))
            try:
                self.fixture._run_patched(args, fake_batch)
                rc = 0
            except SystemExit as error:
                rc = error.code
        return rc, output.getvalue(), forms

    def test_old_result_exit_2(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{
                "lib.commands.portal_apply._resolve_base_url": {
                    "side_effect": RuntimeError("bad args")
                }
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (2, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_old_result_exit_3(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{
                "lib.commands.portal_apply._maybe_sync": {
                    "side_effect": AgentBrowserMissing("missing")
                }
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (3, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_old_result_exit_4(self):
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            self.fixture._args(),
            **{"lib.commands.portal_apply._maybe_sync": {"side_effect": LoginTimeout("timeout")}},
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (4, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_old_result_exit_5_never_reads_or_writes_result(self):
        before = self.path.read_bytes()
        with apply._apply_lock():
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("不得讀結果")):
                rc, stdout, forms = self.run_apply(self.fixture._args())
        self.assertEqual((rc, forms, self.path.read_bytes()), (5, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_no_items_keeps_old_result_untrusted(self):
        self.fixture.analysis_path.write_text(
            json.dumps({"schema_version": "attendance-analysis/v1", "overtime": [], "leave": []})
        )
        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(self.fixture._args())
        self.assertEqual((rc, forms, self.path.read_bytes()), (0, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_cancel_keeps_old_result_untrusted(self):
        args = self.fixture._args()
        args.auto = False

        def choose(*, plan, **kwargs):
            plan["overtime"].append({"entry": ENTRY, "action": "submit", "reason": "test"})

        before = self.path.read_bytes()
        rc, stdout, forms = self.run_apply(
            args,
            **{
                "lib.commands.portal_apply._interactive_overtime": {"side_effect": choose},
                "lib.commands.portal_apply._interactive_leave": {},
                "builtins.input": {"return_value": "n"},
            },
        )
        self.assertEqual((rc, forms, self.path.read_bytes()), (0, [], before))
        self.assertNotIn("結果寫入：", stdout)

    def test_normal_completion_receipt_matches_finalized_result(self):
        args = self.fixture._args()
        args.leave_only = True
        rc, stdout, forms = self.run_apply(args)
        self.assertEqual(rc, 0)
        self.assertEqual(len(forms), 1)
        data = json.loads(self.path.read_text())
        self.assertIs(data.get("completed"), True)
        self.assertNotEqual(data.get("run_id"), RUN_ID)
        self.assertIn(f"結果寫入：{self.path.resolve()}（run_id={data['run_id']}）", stdout)

    def test_interrupted_submission_finalizes_only_observed_entries(self):
        args = self.fixture._args()
        args.leave_only = True
        portal = FakePortal([], timeout_after_commit=True)
        real_batch = af.batch_submit

        def interrupted(_portal, base, ot, lv, **kwargs):
            return real_batch(portal, base, ot, lv, **kwargs)

        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
            self.fixture._run_patched(args, interrupted)
        self.assertEqual(stopped.exception.code, 5)
        data = json.loads(self.path.read_text())
        self.assertIs(data.get("completed"), True)
        self.assertEqual(data["leave"][0]["status"], "confirmed")
        self.assertIn(data["run_id"], output.getvalue())

    def test_progress_writes_are_incomplete_without_receipt(self):
        snapshots = []
        real_save = apply._save_results
        output = io.StringIO()

        def save(path, data):
            snapshots.append(json.loads(json.dumps(data)))
            self.assertEqual(output.getvalue(), "")
            real_save(path, data)

        args = self.fixture._args()
        with mock.patch.object(apply, "_save_results", side_effect=save):
            with contextlib.redirect_stdout(output):
                self.fixture._run_patched(args, self.fixture._fake_batch_submit("confirmed"))
        self.assertEqual([s.get("completed") for s in snapshots], [False, False, True])
        self.assertEqual(len({s["run_id"] for s in snapshots}), 1)


class TestAtomicResults(unittest.TestCase):
    def test_replacement_only_exposes_complete_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            path.write_text('{"old": true}')
            real_replace = os.replace
            observed = []

            def replace(source, destination):
                observed.append((path.read_text(), json.loads(Path(source).read_text())))
                self.assertEqual(Path(source).parent, path.parent)
                real_replace(source, destination)

            with mock.patch.object(apply.os, "replace", side_effect=replace):
                apply._save_results(path, {"completed": True})
            self.assertEqual(observed, [('{"old": true}', {"completed": True})])
            self.assertEqual(json.loads(path.read_text()), {"completed": True})

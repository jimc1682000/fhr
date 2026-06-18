"""Unit tests for `lib/commands/portal_apply.py` private helpers.

Tier 1 of the v2.1 testing plan. These functions are pure (or pure I/O
on temp files) — no agent-browser dependency. They were previously
untested despite being 600+ LOC of business logic.
"""

import argparse
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.commands.portal_apply import (
    _auto_detect_attendance,
    _entry_key,
    _fmt_time,
    _format_entry,
    _is_early_arrival,
    _load_analysis,
    _load_attendance_map,
    _load_completed,
    _load_plan,
    _plan_path,
    _resolve_base_url,
    _resolve_screenshot_dir,
    _result_path,
    _save_plan,
    _save_results,
    _should_fetch_balances,
    _wrap_submit_iter,
    run,
)


def _ns(**kw):
    """Build a fake argparse.Namespace with sensible defaults."""
    defaults = {
        "dry_run": False,
        "screenshot_dir": None,
        "base_url": None,
    }
    return argparse.Namespace(**{**defaults, **kw})


# -------- _entry_key / _plan_path / _result_path / _fmt_time --------


class TestEntryKey(unittest.TestCase):
    def test_format(self):
        e = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        self.assertEqual(_entry_key(e, "overtime"), "overtime|2026/04/20|1830|2030")

    def test_different_form_type_different_key(self):
        e = {"date": "2026/04/20", "start_time": "0930", "end_time": "1130"}
        self.assertNotEqual(_entry_key(e, "leave"), _entry_key(e, "overtime"))


class TestPathHelpers(unittest.TestCase):
    def test_plan_path_renames_analysis_to_apply_plan(self):
        out = _plan_path("/tmp/hr_personal_analysis_20260519.json")
        self.assertEqual(out.name, "hr_personal_apply_plan_20260519.json")

    def test_result_path_renames_analysis_to_apply_result(self):
        out = _result_path("/tmp/hr_personal_analysis_20260519.json")
        self.assertEqual(out.name, "hr_personal_apply_result_20260519.json")

    def test_paths_share_directory(self):
        plan = _plan_path("/var/foo/analysis.json")
        result = _result_path("/var/foo/analysis.json")
        self.assertEqual(plan.parent, result.parent)


class TestFmtTime(unittest.TestCase):
    def test_4_digit_to_colon(self):
        self.assertEqual(_fmt_time("0930"), "09:30")
        self.assertEqual(_fmt_time("1830"), "18:30")


# -------- _is_early_arrival --------


class TestIsEarlyArrival(unittest.TestCase):
    def _att(self, in_time: str | None) -> dict:
        rec = {}
        if in_time is not None:
            rec["上班"] = in_time
        return {"2026/04/22": rec}

    def test_early_arrival_returns_delta_minutes(self):
        # actual 09:05, schedule_start 09:30, latest 10:00 → early=25min before schedule
        is_early, delta = _is_early_arrival(
            "2026/04/22",
            "09:30",
            "10:00",
            self._att("09:05"),
        )
        self.assertTrue(is_early)
        self.assertEqual(delta, 25)

    def test_on_time_not_early(self):
        is_early, delta = _is_early_arrival(
            "2026/04/22",
            "09:30",
            "10:00",
            self._att("10:00"),
        )
        self.assertFalse(is_early)
        self.assertEqual(delta, 0)

    def test_late_not_early(self):
        is_early, delta = _is_early_arrival(
            "2026/04/22",
            "09:30",
            "10:00",
            self._att("11:26"),
        )
        self.assertFalse(is_early)

    def test_missing_punch(self):
        is_early, delta = _is_early_arrival(
            "2026/04/22",
            "09:30",
            "10:00",
            self._att(None),
        )
        self.assertFalse(is_early)

    def test_empty_punch_marker(self):
        is_early, _ = _is_early_arrival(
            "2026/04/22",
            "09:30",
            "10:00",
            self._att("—"),
        )
        self.assertFalse(is_early)


# -------- _format_entry --------


class TestFormatEntry(unittest.TestCase):
    ENTRY = {"date": "2026/04/22", "start_time": "1805", "end_time": "2005", "hours": 2}

    def test_includes_actual_punches(self):
        att = {"2026/04/22": {"上班": "09:05", "下班": "21:03"}}
        out = _format_entry(
            self.ENTRY, att, schedule_start="09:30", latest_checkin="10:00"
        )
        self.assertIn("實際 上班 09:05", out)
        self.assertIn("下班 21:03", out)

    def test_includes_early_arrival_hint(self):
        att = {"2026/04/22": {"上班": "09:05", "下班": "21:03"}}
        out = _format_entry(
            self.ENTRY,
            att,
            schedule_start="09:30",
            latest_checkin="10:00",
            expected_checkout="18:05",
        )
        self.assertIn("💡 早到 → 預期下班 18:05", out)

    def test_no_attendance_data(self):
        out = _format_entry(
            self.ENTRY, {}, schedule_start="09:30", latest_checkin="10:00"
        )
        self.assertIn("2026/04/22", out)
        self.assertNotIn("實際", out)


# -------- _load_plan / _save_plan --------


class TestPlanFileRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_missing_file_returns_empty_dict(self):
        if self.path.exists():
            self.path.unlink()
        self.assertEqual(_load_plan(self.path), {})

    def test_bad_json_returns_empty_dict(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(_load_plan(self.path), {})

    def test_round_trip_keys_by_entry_key(self):
        entry = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        plan = {
            "overtime": [
                {
                    "entry": entry,
                    "action": "submit",
                    "key": _entry_key(entry, "overtime"),
                    "reason": "x",
                }
            ],
            "leave": [],
        }
        _save_plan(self.path, plan)
        loaded = _load_plan(self.path)
        self.assertIn(_entry_key(entry, "overtime"), loaded)
        # entry not persisted (caller re-attaches)
        self.assertNotIn("entry", loaded[_entry_key(entry, "overtime")])
        self.assertEqual(loaded[_entry_key(entry, "overtime")]["reason"], "x")


# -------- _load_completed --------


class TestLoadCompleted(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        self.tmp.close()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def _write(self, payload):
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def test_missing_file_empty_set(self):
        if self.path.exists():
            self.path.unlink()
        self.assertEqual(_load_completed(self.path), set())

    def test_bad_json_empty_set(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(_load_completed(self.path), set())

    def test_collects_submitted_entries(self):
        e1 = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        e2 = {"date": "2026/04/24", "start_time": "0930", "end_time": "1830"}
        self._write(
            {
                "overtime": [{"entry": e1, "submitted": True}],
                "leave": [{"entry": e2, "submitted": True}],
            }
        )
        out = _load_completed(self.path)
        self.assertIn(_entry_key(e1, "overtime"), out)
        self.assertIn(_entry_key(e2, "leave"), out)

    def test_dry_run_entries_excluded(self):
        # Regression: previously dry_run=true entries were treated as
        # completed (since submitted:true). Now they must NOT count.
        e1 = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        self._write(
            {
                "overtime": [{"entry": e1, "submitted": True, "dry_run": True}],
                "leave": [],
            }
        )
        self.assertEqual(_load_completed(self.path), set())

    def test_skipped_entries_excluded(self):
        e1 = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        self._write(
            {
                "overtime": [{"entry": e1, "submitted": False, "skipped": True}],
                "leave": [],
            }
        )
        self.assertEqual(_load_completed(self.path), set())


# -------- _save_results --------


class TestSaveResults(unittest.TestCase):
    def test_writes_pretty_utf8(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            path = Path(f.name)
        try:
            _save_results(path, {"overtime": [{"x": "中文"}], "leave": []})
            content = path.read_text(encoding="utf-8")
            self.assertIn("中文", content)
            self.assertIn("\n", content)  # pretty printed
        finally:
            path.unlink()


# -------- _should_fetch_balances --------


class TestShouldFetchBalances(unittest.TestCase):
    def test_fetches_for_leave_even_when_no_sync(self):
        leave = [{"date": "2026/04/24", "start_time": "0930", "end_time": "1830"}]
        self.assertTrue(_should_fetch_balances(leave, no_sync=True))

    def test_skips_when_no_leave_entries(self):
        self.assertFalse(_should_fetch_balances([], no_sync=False))
        self.assertFalse(_should_fetch_balances([], no_sync=True))


# -------- run orchestration --------


class _FakePortalSession:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStateManager:
    instances = []

    def __init__(self, *args, **kwargs):
        self.applied = {"overtime": [], "leave": []}
        self.recorded = []
        self.saved = 0
        self.instances.append(self)

    def get_applied_forms(self, user, kind=None):
        if kind is None:
            return self.applied
        return self.applied.get(kind, [])

    def record_applied_form(self, user, kind, entry, recorded_at):
        self.recorded.append((user, kind, entry, recorded_at))
        self.applied.setdefault(kind, []).append(entry)

    def save_state(self):
        self.saved += 1


class TestRunAutoMode(unittest.TestCase):
    def setUp(self):
        _FakeStateManager.instances = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.analysis_path = Path(self.tmp.name) / "hr_personal_analysis_20260519.json"
        self.analysis_path.write_text(
            json.dumps(
                {
                    "schema_version": "attendance-analysis/v1",
                    "overtime": [
                        {
                            "date": "2026/04/20",
                            "start_time": "1830",
                            "end_time": "2030",
                            "hours": 2,
                            "reason": "deploy",
                        }
                    ],
                    "leave": [
                        {
                            "date": "2026/04/24",
                            "start_time": "0930",
                            "end_time": "1830",
                            "hours": 9,
                            "type_hint": "WFH",
                            "reason": "WFH",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _args(self):
        return _ns(
            user="JimmyChen",
            input=str(self.analysis_path),
            attendance=None,
            proxy="Proxy User",
            auto=True,
            dry_run=False,
            dry_run_pause_secs=0,
            screenshot_dir=None,
            overtime_only=False,
            leave_only=False,
            base_url="https://ehr.example/ehrPortal",
            session="test-session",
            no_sync=True,
            sync_max_age_hours=4,
            debug=False,
        )

    def test_auto_mode_fetches_balances_and_records_local_submits(self):
        def fake_batch_submit(
            portal,
            base_url,
            overtime_iter,
            leave_iter,
            *,
            on_overtime_done,
            on_leave_done,
            **kwargs,
        ):
            overtime = list(overtime_iter)
            leave = list(leave_iter)
            for item in overtime:
                on_overtime_done(item, True)
            for item in leave:
                on_leave_done(item, True)
            return len(overtime), len(overtime), len(leave), len(leave)

        balances = {
            "items": {
                "異地辦公(8hr一週)": {"remaining": None},
                "補休假": {"remaining": 8},
                "事假(含家庭照顧假)": {"remaining": None},
            },
            "annual_leave": {"remaining_hours": 80},
        }

        with (
            mock.patch("lib.env.load"),
            mock.patch("lib.state.AttendanceStateManager", _FakeStateManager),
            mock.patch("lib.portal.client.PortalSession", _FakePortalSession),
            mock.patch("lib.portal.client.ensure_login") as ensure_login,
            mock.patch(
                "lib.portal.balances.fetch_balances", return_value=balances
            ) as fetch_balances,
            mock.patch(
                "lib.portal.apply_forms.batch_submit", side_effect=fake_batch_submit
            ),
        ):
            run(self._args())

        ensure_login.assert_called()
        fetch_balances.assert_called_once()
        state = _FakeStateManager.instances[-1]
        recorded_kinds = [item[1] for item in state.recorded]
        self.assertEqual(recorded_kinds, ["overtime", "leave"])
        self.assertNotIn("last_full_sync", state.applied)
        self.assertEqual(state.saved, 2)


# -------- _load_analysis --------


class TestLoadAnalysis(unittest.TestCase):
    def test_validates_schema_version(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "schema_version": "attendance-analysis/v1",
                    "overtime": [],
                    "leave": [],
                    "summary": {},
                    "cutoff_date": None,
                    "skipped": [],
                },
                f,
            )
            path = f.name
        try:
            payload = _load_analysis(path)
            self.assertEqual(payload["schema_version"], "attendance-analysis/v1")
        finally:
            os.remove(path)

    def test_wrong_schema_raises(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"schema_version": "other/v9"}, f)
            path = f.name
        try:
            from lib.schema import SchemaVersionError

            with self.assertRaises(SchemaVersionError):
                _load_analysis(path)
        finally:
            os.remove(path)


# -------- _load_attendance_map --------


class TestLoadAttendanceMap(unittest.TestCase):
    HEADER = (
        "\t".join(
            [
                "應刷卡時段",
                "當日卡鐘資料",
                "刷卡別",
                "卡鐘編號",
                "資料來源",
                "異常狀態",
                "處理狀態",
                "異常處理作業",
                "備註",
            ]
        )
        + "\n"
    )

    def _write(self, body: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        Path(path).write_text(self.HEADER + body, encoding="utf-8")
        return path

    def test_parses_checkin_and_checkout(self):
        body = (
            "2026/04/20 09:30\t2026/04/20 11:26\t上班\t1\t刷卡匯入\t遲到\t\t\t\n"
            "2026/04/20 18:30\t2026/04/20 21:05\t下班\t1\t刷卡匯入\t\t\t\t\n"
        )
        path = self._write(body)
        try:
            out = _load_attendance_map(path)
            self.assertEqual(out["2026/04/20"]["上班"], "11:26")
            self.assertEqual(out["2026/04/20"]["下班"], "21:05")
        finally:
            os.remove(path)

    def test_missing_punch_yields_em_dash(self):
        body = "2026/04/24 09:30\t\t上班\t1\t\t曠職\t\t\t\n"
        path = self._write(body)
        try:
            out = _load_attendance_map(path)
            self.assertEqual(out["2026/04/24"]["上班"], "—")
        finally:
            os.remove(path)

    def test_no_path_returns_empty(self):
        self.assertEqual(_load_attendance_map(None), {})

    def test_missing_file_returns_empty(self):
        self.assertEqual(_load_attendance_map("/no/such/path.txt"), {})


# -------- _auto_detect_attendance --------


class TestAutoDetectAttendance(unittest.TestCase):
    def test_finds_出勤資料_next_to_analysis(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "202604-X-出勤資料.txt").touch()
            (Path(d) / "analysis.json").touch()
            found = _auto_detect_attendance(str(Path(d) / "analysis.json"))
            self.assertTrue(found.endswith("出勤資料.txt"))

    def test_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(_auto_detect_attendance(str(Path(d) / "analysis.json")))


# -------- _resolve_base_url --------


class TestResolveBaseUrl(unittest.TestCase):
    def setUp(self):
        self._saved = dict(os.environ)
        os.environ.pop("EHR_URL", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_from_cli_arg(self):
        out = _resolve_base_url(_ns(base_url="http://x.example/ehrPortal/"))
        self.assertEqual(out, "http://x.example/ehrPortal")

    def test_from_env(self):
        os.environ["EHR_URL"] = "http://y.example/ehrPortal/"
        self.assertEqual(_resolve_base_url(_ns()), "http://y.example/ehrPortal")

    def test_strips_login_suffix(self):
        os.environ["EHR_URL"] = "http://x.example/ehrPortal/LoginFOrginal.asp"
        self.assertEqual(_resolve_base_url(_ns()), "http://x.example/ehrPortal")

    def test_strips_loginfopen_suffix(self):
        os.environ["EHR_URL"] = "http://x.example/ehrPortal/LoginFOpen.asp"
        self.assertEqual(_resolve_base_url(_ns()), "http://x.example/ehrPortal")

    def test_missing_raises(self):
        with self.assertRaises(RuntimeError):
            _resolve_base_url(_ns())


# -------- _resolve_screenshot_dir --------


class TestResolveScreenshotDir(unittest.TestCase):
    def test_non_dry_run_returns_none(self):
        self.assertIsNone(_resolve_screenshot_dir(_ns(dry_run=False)))

    def test_explicit_empty_string_opts_out(self):
        self.assertIsNone(_resolve_screenshot_dir(_ns(dry_run=True, screenshot_dir="")))

    def test_explicit_path(self):
        out = _resolve_screenshot_dir(_ns(dry_run=True, screenshot_dir="my/dir"))
        self.assertEqual(out, Path("my/dir"))

    def test_default_under_tmp(self):
        out = _resolve_screenshot_dir(_ns(dry_run=True))
        self.assertIsNotNone(out)
        parts = out.parts
        self.assertEqual(parts[0], "tmp")
        self.assertEqual(parts[1], "dry-run-screenshots")
        # Last segment looks like YYYYMMDD-HHMMSS
        self.assertRegex(parts[2], r"^\d{8}-\d{6}$")


# -------- _wrap_submit_iter --------


class TestWrapSubmitIter(unittest.TestCase):
    def test_skips_completed(self):
        e1 = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        e2 = {"date": "2026/04/22", "start_time": "1805", "end_time": "2005"}
        plans = [{"entry": e1}, {"entry": e2}]
        completed = {_entry_key(e1, "overtime")}
        out = list(_wrap_submit_iter(plans, completed, "overtime"))
        self.assertEqual(len(out), 1)
        self.assertIs(out[0]["entry"], e2)

    def test_empty_completed_yields_all(self):
        e = {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"}
        out = list(_wrap_submit_iter([{"entry": e}], set(), "overtime"))
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()

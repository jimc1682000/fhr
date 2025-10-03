import os
import sys
import tempfile
import threading
import types
import unittest
from datetime import datetime
from unittest.mock import patch

from attendance_analyzer import Issue, IssueType
from lib.service import (
    AnalysisResult,
    ExportedFile,
    IncrementalStatus,
    IssuePreview,
    ResetStateError,
)
from tui.app import AnalysisForm, AttendanceAnalyzerApp, run_app


class AttendanceAnalyzerAppUITest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.sample_path = os.path.join(self.tmp.name, "sample.txt")
        with open(self.sample_path, "w", encoding="utf-8") as fh:
            fh.write("dummy")

    def _fake_result(self) -> AnalysisResult:
        issues = [
            Issue(
                date=datetime(2025, 7, 1),
                type=IssueType.OVERTIME,
                duration_minutes=120,
                description="加班2小時",
                time_range="19:00~21:00",
                calculation="預期下班: 19:00, 實際: 21:00",
            ),
            Issue(
                date=datetime(2025, 7, 2),
                type=IssueType.LATE,
                duration_minutes=30,
                description="遲到30分鐘",
                is_new=False,
            ),
        ]
        previews = [
            IssuePreview(
                date="2025/07/01",
                type="加班",
                duration_minutes=120,
                description="加班2小時",
                time_range="19:00~21:00",
                calculation="預期下班: 19:00, 實際: 21:00",
                status="[NEW] 本次新發現",
            ),
            IssuePreview(
                date="2025/07/02",
                type="遲到",
                duration_minutes=30,
                description="遲到30分鐘",
                status="已存在",
            ),
        ]
        exports = [
            ExportedFile(
                requested_path=os.path.join(self.tmp.name, "out.xlsx"),
                actual_path=os.path.join(self.tmp.name, "out.xlsx"),
                requested_format="excel",
                actual_format="excel",
            )
        ]
        status = IncrementalStatus(
            last_date="2025-07-02",
            complete_days=2,
            last_analysis_time="2025-07-02T10:00:00",
        )
        return AnalysisResult(
            requested_mode="incremental",
            effective_mode="incremental",
            requested_format="excel",
            actual_format="excel",
            user_name="王小明",
            start_date="2025-07-01",
            end_date="2025-07-02",
            reset_applied=False,
            first_time_user=False,
            outputs=exports,
            issues=issues,
            issues_preview=previews,
            report_text="",
            totals={"TOTAL": 2, "OVERTIME": 1, "LATE": 1},
            status=status,
            debug_mode=False,
        )

    async def test_form_submission_renders_summary(self) -> None:
        fake_result = self._fake_result()
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.source_input.value = self.sample_path
            form.output_input.value = self.tmp.name
            form.preview_input.value = "2"

            def fake_worker(work, *args, **kwargs):
                result = work()
                app._handle_success(result)

                class _Worker:
                    def __init__(self, result: AnalysisResult) -> None:
                        self.result = result
                        self.error = None
                        self.is_running = False

                    def cancel(self) -> None:
                        self.is_running = False

                return _Worker(result)

            with patch.object(app, "_run_analysis", return_value=fake_result):
                with patch.object(app, "run_worker", side_effect=fake_worker):
                    form.submit()
                    await pilot.pause()

            self.assertFalse(form.busy)
            self.assertGreater(app.preview_table.row_count, 0)
            self.assertIn("王小明", app.summary_panel.renderable.plain)
            self.assertIn("✅", app.progress_stage.renderable.plain)

    async def test_cancel_action_sets_event(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.set_busy(True)
            cancel_event = threading.Event()

            class _Worker:
                def __init__(self) -> None:
                    self.is_running = True
                    self.cancel_called = False

                def cancel(self) -> None:
                    self.cancel_called = True
                    self.is_running = False

            worker = _Worker()
            app._cancel_event = cancel_event
            app._analysis_worker = worker
            app.action_cancel_analysis()
            await pilot.pause()

            self.assertTrue(cancel_event.is_set())
            self.assertTrue(worker.cancel_called)
            self.assertIn("🛑", form.status_message.renderable.plain)

    async def test_language_toggle_updates_stage(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            original = app.progress_stage.renderable.plain
            self.assertIn("等待", original)
            app.action_toggle_language()
            await pilot.pause()
            toggled = app.progress_stage.renderable.plain
            self.assertIn("Waiting", toggled)

    async def test_invalid_preview_limit_shows_error(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.source_input.value = self.sample_path
            form.preview_input.value = "abc"

            with patch.object(app, "run_worker") as mock_run_worker:
                form.submit()
                await pilot.pause()

            self.assertFalse(mock_run_worker.called)
            self.assertIn("預覽筆數需為整數", form.status_message.renderable.plain)
            self.assertFalse(form.busy)

    async def test_missing_source_path_shows_error(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.source_input.value = ""

            with patch.object(app, "run_worker") as mock_run_worker:
                form.submit()
                await pilot.pause()

            self.assertFalse(mock_run_worker.called)
            self.assertIn("請先輸入考勤檔案路徑", form.status_message.renderable.plain)
            self.assertFalse(form.busy)

    async def test_reset_state_error_shows_warning(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.source_input.value = self.sample_path

            def fake_worker(work, *args, **kwargs):
                app._handle_error(ResetStateError("需要重置狀態"))

                class _Worker:
                    def __init__(self) -> None:
                        self.is_running = False
                        self.error = ResetStateError("需要重置狀態")

                    def cancel(self) -> None:  # pragma: no cover - interface
                        self.is_running = False

                return _Worker()

            with patch.object(app, "run_worker", side_effect=fake_worker):
                form.submit()
                await pilot.pause()

            self.assertIn("⚠️", form.status_message.renderable.plain)
            self.assertIn("需要重置狀態", form.status_message.renderable.plain)
            self.assertFalse(form.busy)

    async def test_unexpected_error_shows_generic_message(self) -> None:
        async with AttendanceAnalyzerApp().run_test() as pilot:
            app = pilot.app
            form = app.query_one(AnalysisForm)
            form.source_input.value = self.sample_path

            def fake_worker(work, *args, **kwargs):
                app._handle_error(RuntimeError("boom"))

                class _Worker:
                    def __init__(self) -> None:
                        self.is_running = False
                        self.error = RuntimeError("boom")

                    def cancel(self) -> None:  # pragma: no cover - interface
                        self.is_running = False

                return _Worker()

            with patch.object(app, "run_worker", side_effect=fake_worker):
                form.submit()
                await pilot.pause()

            self.assertIn("未預期錯誤", form.status_message.renderable.plain)
            self.assertFalse(form.busy)
            self.assertIn("❌", app.progress_stage.renderable.plain)


class RunAppSmokeTest(unittest.TestCase):
    def tearDown(self) -> None:
        sys.modules.pop("textual_web", None)

    def test_webview_launch_invokes_textual_web(self) -> None:
        sys.modules["textual_web"] = types.ModuleType("textual_web")
        with patch("subprocess.run") as mock_run:
            run_app(webview=True, dark=True)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("--web-interface", args)
        self.assertIn("--run", args)
        self.assertIn("--dark", args[5])

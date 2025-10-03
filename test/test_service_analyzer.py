import json
import os
import shutil
import tempfile
import unittest

from lib.service import (
    AnalysisOptions,
    AnalyzerService,
    OutputRequest,
    ResetStateError,
)


class TestAnalyzerService(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_state = os.environ.get("FHR_STATE_FILE")
        self.state_path = os.path.join(self.tmp.name, "attendance_state.json")
        os.environ["FHR_STATE_FILE"] = self.state_path
        os.environ.setdefault("HOLIDAY_API_MAX_RETRIES", "0")
        os.environ.setdefault("HOLIDAY_API_BACKOFF_BASE", "0.1")

    def tearDown(self) -> None:
        if self.old_state is None:
            os.environ.pop("FHR_STATE_FILE", None)
        else:
            os.environ["FHR_STATE_FILE"] = self.old_state

    def _copy_sample(self, filename: str = "sample-attendance-data.txt") -> str:
        src = os.path.join(os.getcwd(), filename)
        dst = os.path.join(self.tmp.name, filename)
        shutil.copy(src, dst)
        return dst

    def test_incremental_csv_export(self) -> None:
        sample = self._copy_sample()
        output = os.path.join(self.tmp.name, "result_analysis.csv")
        service = AnalyzerService()
        options = AnalysisOptions(
            source_path=sample,
            requested_format="csv",
            mode="incremental",
            output=OutputRequest(path=output, format="csv"),
            extra_outputs=tuple(),
            add_recent=False,
        )
        result = service.run(options)
        self.assertTrue(os.path.exists(output))
        self.assertEqual(result.actual_format, "csv")
        self.assertEqual(result.outputs[0].actual_path, output)
        self.assertEqual(result.requested_mode, "incremental")

    def test_reset_state_requires_user(self) -> None:
        sample = self._copy_sample("sample-attendance-data.txt")
        service = AnalyzerService()
        options = AnalysisOptions(
            source_path=sample,
            requested_format="csv",
            mode="full",
            reset_state=True,
            output=OutputRequest(path=os.path.join(self.tmp.name, "out.csv"), format="csv"),
            add_recent=False,
        )
        with self.assertRaises(ResetStateError):
            service.run(options)

    def test_reset_state_applies_and_marks_first_time(self) -> None:
        filename = "202508-阿明-出勤資料.txt"
        sample_path = os.path.join(self.tmp.name, filename)
        with open(sample_path, "w", encoding="utf-8") as fh:
            fh.write("應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n")
        state_data = {
            "users": {
                "阿明": {
                    "processed_date_ranges": [
                        {
                            "start_date": "2025-07-01",
                            "end_date": "2025-07-02",
                            "source_file": filename,
                            "last_analysis_time": "2025-07-02T00:00:00",
                        }
                    ],
                    "forget_punch_usage": {},
                }
            }
        }
        with open(self.state_path, "w", encoding="utf-8") as fh:
            json.dump(state_data, fh)

        service = AnalyzerService()
        options = AnalysisOptions(
            source_path=sample_path,
            requested_format="csv",
            mode="incremental",
            reset_state=True,
            output=OutputRequest(path=os.path.join(self.tmp.name, "reset.csv"), format="csv"),
            add_recent=False,
        )
        result = service.run(options)
        self.assertTrue(result.reset_applied)
        self.assertTrue(result.first_time_user)
        with open(self.state_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertNotIn("阿明", data.get("users", {}))


if __name__ == '__main__':
    unittest.main()
"""Category: Service
Purpose: AnalyzerService high-level orchestration and reset behavior."""

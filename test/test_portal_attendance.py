"""Tests for `lib/portal/attendance.py`.

We mock the PortalSession + subprocess primitives — no real
agent-browser invocation.
"""
import os
import tempfile
import unittest
from unittest import mock

from lib.portal.attendance import (
    _extract_form_refs,
    fetch_snapshot,
    fetch_to_txt,
)

SAMPLE_SNAPSHOT = """\
- cell "一般假勤 特休假勤 異常刷卡" [ref=e1]
- cell " 出勤刷卡期間 2026 年 5 月 到 2026 年 5 月  資料類型 異常刷卡資料  異常狀態 請選擇" [ref=e2]
  - textbox [ref=e6]: 2026
  - combobox [expanded=false, ref=e7]: 5
  - textbox [ref=e8]: 2026
  - combobox [expanded=false, ref=e9]: 5
  - combobox [expanded=false, ref=e10]: 異常刷卡資料
  - combobox [expanded=false, ref=e11]: 請選擇
  - link [ref=e12]
"""


class TestExtractFormRefs(unittest.TestCase):
    def test_happy_path(self):
        refs = _extract_form_refs(SAMPLE_SNAPSHOT)
        self.assertEqual(refs["start_year"], "@e6")
        self.assertEqual(refs["start_month"], "@e7")
        self.assertEqual(refs["end_year"], "@e8")
        self.assertEqual(refs["end_month"], "@e9")
        self.assertEqual(refs["data_type"], "@e10")
        self.assertEqual(refs["search"], "@e12")

    def test_missing_section_returns_empty(self):
        # No "出勤刷卡期間" anchor at all
        self.assertEqual(_extract_form_refs("- cell foo"), {})


class TestFetchSnapshot(unittest.TestCase):
    def _portal(self):
        return mock.Mock()

    def _wire_form_refs(self, portal):
        portal._run.return_value = SAMPLE_SNAPSHOT

    def test_returns_v1_payload(self):
        portal = self._portal()
        self._wire_form_refs(portal)
        portal.eval_json.return_value = {
            "totalPages": 2,
            "recordCount": 3,
            "records": [
                {"scheduledTime": "2026/05/01 09:30", "actualTime": "",
                 "type": "上班", "status": "曠職"},
                {"scheduledTime": "2026/05/02 09:30", "actualTime": "2026/05/02 09:32",
                 "type": "上班", "status": ""},
                {"scheduledTime": "2026/05/02 18:30", "actualTime": "2026/05/02 19:10",
                 "type": "下班", "status": ""},
            ],
        }
        out = fetch_snapshot(portal, "http://x",
                             start_year=2026, start_month=4, end_year=2026, end_month=5)
        self.assertEqual(out["schema_version"], "portal-attendance-snapshot/v1")
        self.assertEqual(out["totalPages"], 2)
        self.assertEqual(out["recordCount"], 3)
        self.assertEqual(len(out["records"]), 3)
        portal.open.assert_called_once()
        portal.eval_json.assert_called_once()

    def test_eval_error_propagates(self):
        portal = self._portal()
        self._wire_form_refs(portal)
        portal.eval_json.return_value = {"error": "mainFrame not found"}
        with self.assertRaises(RuntimeError):
            fetch_snapshot(portal, "http://x",
                           start_year=2026, start_month=5, end_year=2026, end_month=5)

    def test_unexpected_shape_raises(self):
        portal = self._portal()
        self._wire_form_refs(portal)
        portal.eval_json.return_value = "not a dict"
        with self.assertRaises(RuntimeError):
            fetch_snapshot(portal, "http://x",
                           start_year=2026, start_month=5, end_year=2026, end_month=5)


class TestFetchToTxt(unittest.TestCase):
    def test_writes_9col_txt(self):
        portal = mock.Mock()
        portal._run.return_value = SAMPLE_SNAPSHOT
        portal.eval_json.return_value = {
            "totalPages": 1,
            "recordCount": 1,
            "records": [
                {"scheduledTime": "2026/05/02 09:30", "actualTime": "2026/05/02 09:32",
                 "type": "上班", "status": ""},
            ],
        }
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            n = fetch_to_txt(portal, "http://x", path,
                             start_year=2026, start_month=5, end_year=2026, end_month=5)
            self.assertEqual(n, 1)
            content = open(path, encoding="utf-8").read()
            # header + 1 data row + trailing \n = 2 newlines
            self.assertEqual(content.count("\n"), 2)
            self.assertTrue(content.startswith("應刷卡時段\t當日卡鐘資料"))
            self.assertIn("上班\t1\t刷卡匯入", content)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()

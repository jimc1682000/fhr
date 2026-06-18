"""Tests for `lib/portal/approvals.py`."""

import unittest
from unittest import mock

from lib.portal.approvals import (
    _extract_filter_refs,
    fetch_all_applied_forms,
    fetch_form_entries,
    parse_wsdinfotext,
)

SAMPLE_WSD_OT = """員工編號：546
員工姓名：陳建豪(Jimmy Chen)
部門名稱：技術(TECH)
加班日期：(開始時間 StartDate) 2026/04/20 18:30(結束時間 EndDate) 2026/04/20 20:30
加班地點：在辦公室
合計時數：2 小時
加班原因：上線部署作業
目前狀態：已核准"""

SAMPLE_WSD_LEAVE = """員工編號：546
員工姓名：陳建豪(Jimmy Chen)
職務代理人挑選：297  賴菁甫
假勤日期：(開始時間 StartDate) 2026/04/24 09:30(結束時間 EndDate) 2026/04/24 18:30
可申請假勤項目：異地辦公(8hr一週)
合計時數：8 小時
請假原因：WFH"""

FILTER_SNAPSHOT = """\
- textbox [ref=e3]
- combobox [expanded=false, ref=e4]: 未處理
- combobox [expanded=false, ref=e5]: 全部
- textbox [disabled, ref=e6]: 陳建豪
- button "Export" [ref=e7]
- button "提交" [ref=e10]
- generic "無資料" [ref=e1]
"""


class TestParseWsdinfotext(unittest.TestCase):
    def test_overtime(self):
        out = parse_wsdinfotext(SAMPLE_WSD_OT)
        self.assertEqual(out["date"], "2026/04/20")
        self.assertEqual(out["start_time"], "1830")
        self.assertEqual(out["end_time"], "2030")
        self.assertEqual(out["hours"], 2)
        self.assertEqual(out["location"], "在辦公室")
        self.assertEqual(out["reason"], "上線部署作業")
        self.assertEqual(out["status"], "已核准")

    def test_leave(self):
        out = parse_wsdinfotext(SAMPLE_WSD_LEAVE)
        self.assertEqual(out["date"], "2026/04/24")
        self.assertEqual(out["start_time"], "0930")
        self.assertEqual(out["end_time"], "1830")
        self.assertEqual(out["hours"], 8)
        self.assertEqual(out["leave_type"], "異地辦公(8hr一週)")
        self.assertEqual(out["reason"], "WFH")

    def test_missing_date_returns_none(self):
        self.assertIsNone(parse_wsdinfotext(""))
        self.assertIsNone(parse_wsdinfotext("無有效資料"))

    def test_partial_record_falls_back(self):
        # End date missing → end_date falls back to start_date
        partial = "假勤日期：(開始時間 StartDate) 2026/05/15 09:30"
        out = parse_wsdinfotext(partial)
        self.assertEqual(out["date"], "2026/05/15")
        self.assertEqual(out["end_date"], "2026/05/15")
        self.assertEqual(out["end_time"], "")


class TestExtractFilterRefs(unittest.TestCase):
    def test_happy_path(self):
        refs = _extract_filter_refs(FILTER_SNAPSHOT)
        self.assertEqual(refs["status"], "@e4")
        self.assertEqual(refs["form"], "@e5")
        self.assertEqual(refs["submit"], "@e10")

    def test_missing_returns_empty(self):
        self.assertEqual(_extract_filter_refs("- cell foo"), {})


class TestFetchFormEntries(unittest.TestCase):
    def test_returns_parsed_entries(self):
        portal = mock.Mock()
        portal._run.return_value = FILTER_SNAPSHOT
        portal.eval_json.return_value = {
            "totalPages": 1,
            "rows": [
                {"id": "tbWorkSheetDataList_1", "wsdinfotext": SAMPLE_WSD_OT},
                {
                    "id": "tbWorkSheetDataList_2",
                    "wsdinfotext": "",
                },  # malformed → skipped
            ],
        }
        entries = fetch_form_entries(portal, "http://x", "加班單")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["date"], "2026/04/20")
        self.assertEqual(entries[0]["row_id"], "tbWorkSheetDataList_1")

    def test_paginates_one_eval_per_page(self):
        # 3 頁 → 逐頁讀，各自一次 eval（不再單一超長 eval）
        portal = mock.Mock()
        portal._run.return_value = FILTER_SNAPSHOT
        pages = [
            {
                "totalPages": 3,
                "page": 0,
                "rows": [{"id": "r0", "wsdinfotext": SAMPLE_WSD_OT}],
            },
            {
                "totalPages": 3,
                "page": 1,
                "rows": [{"id": "r1", "wsdinfotext": SAMPLE_WSD_OT}],
            },
            {
                "totalPages": 3,
                "page": 2,
                "rows": [
                    {"id": "r2", "wsdinfotext": SAMPLE_WSD_OT},
                    {"id": "r1", "wsdinfotext": SAMPLE_WSD_OT},
                ],
            },  # 重複 id 去重
        ]
        portal.eval_json.side_effect = pages
        entries = fetch_form_entries(portal, "http://x", "加班單")
        self.assertEqual(portal.eval_json.call_count, 3)
        self.assertEqual(len(entries), 3)  # r0,r1,r2（重複的 r1 去重）

    def test_eval_error_raises(self):
        portal = mock.Mock()
        portal._run.return_value = FILTER_SNAPSHOT
        portal.eval_json.return_value = {"error": "boom"}
        with self.assertRaises(RuntimeError):
            fetch_form_entries(portal, "http://x", "加班單")

    def test_malformed_eval_raises(self):
        # 回傳 dict 但缺 rows 且非 error → 格式異常
        portal = mock.Mock()
        portal._run.return_value = FILTER_SNAPSHOT
        portal.eval_json.return_value = {"totalPages": 1}
        with self.assertRaises(RuntimeError):
            fetch_form_entries(portal, "http://x", "加班單")

    def test_missing_filter_refs_raises(self):
        portal = mock.Mock()
        portal._run.return_value = "- cell foo"  # no filter refs
        with self.assertRaises(RuntimeError):
            fetch_form_entries(portal, "http://x", "加班單")


class TestFetchAllAppliedForms(unittest.TestCase):
    def test_iterates_kinds(self):
        portal = mock.Mock()
        portal._run.return_value = FILTER_SNAPSHOT
        seq = [
            {"totalPages": 1, "rows": [{"id": "a", "wsdinfotext": SAMPLE_WSD_OT}]},
            {"totalPages": 1, "rows": [{"id": "b", "wsdinfotext": SAMPLE_WSD_LEAVE}]},
        ]
        portal.eval_json.side_effect = seq
        out = fetch_all_applied_forms(portal, "http://x")
        self.assertEqual(set(out), {"overtime", "leave"})
        self.assertEqual(out["overtime"][0]["date"], "2026/04/20")
        self.assertEqual(out["leave"][0]["leave_type"], "異地辦公(8hr一週)")

    def test_rejects_unknown_kind(self):
        portal = mock.Mock()
        with self.assertRaises(ValueError):
            fetch_all_applied_forms(portal, "http://x", kinds=("nope",))


if __name__ == "__main__":
    unittest.main()

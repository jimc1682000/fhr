"""Tests for the new `applied_forms` block on AttendanceStateManager."""

import json
import os
import tempfile
import unittest

from lib.state import AttendanceStateManager


class TestAppliedForms(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        # Start with an empty state file
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f)
        self.sm = AttendanceStateManager(state_file=self.path)

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)

    def _ot(self, date_str: str, start: str, end: str) -> dict:
        return {
            "date": date_str,
            "start_time": start,
            "end_time": end,
            "hours": 2,
            "location": "在辦公室",
            "reason": "上線部署",
            "status": "已核准",
        }

    def test_replace_writes_synced_at_and_persists(self):
        self.sm.replace_applied_forms(
            "JimmyChen",
            {"overtime": [self._ot("2026/04/20", "1830", "2030")], "leave": []},
            synced_at="2026-05-20T10:00:00",
        )
        self.sm.save_state()

        # Re-read from disk
        sm2 = AttendanceStateManager(state_file=self.path)
        applied = sm2.get_applied_forms("JimmyChen")
        self.assertEqual(applied["overtime"][0]["date"], "2026/04/20")
        self.assertEqual(applied["overtime"][0]["synced_at"], "2026-05-20T10:00:00")
        self.assertEqual(applied["last_full_sync"], "2026-05-20T10:00:00")
        self.assertEqual(applied["leave"], [])

    def test_is_form_already_applied(self):
        self.sm.replace_applied_forms(
            "JimmyChen",
            {"overtime": [self._ot("2026/04/20", "1830", "2030")], "leave": []},
            synced_at="now",
        )
        # exact match
        self.assertTrue(
            self.sm.is_form_already_applied(
                "JimmyChen",
                "overtime",
                {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"},
            )
        )
        # different end time → not applied
        self.assertFalse(
            self.sm.is_form_already_applied(
                "JimmyChen",
                "overtime",
                {"date": "2026/04/20", "start_time": "1830", "end_time": "2130"},
            )
        )
        # different date
        self.assertFalse(
            self.sm.is_form_already_applied(
                "JimmyChen",
                "overtime",
                {"date": "2026/04/21", "start_time": "1830", "end_time": "2030"},
            )
        )

    def test_get_applied_forms_by_kind(self):
        self.sm.replace_applied_forms(
            "JimmyChen",
            {
                "overtime": [self._ot("2026/04/20", "1830", "2030")],
                "leave": [
                    {
                        "date": "2026/04/24",
                        "start_time": "0930",
                        "end_time": "1830",
                        "hours": 8,
                        "leave_type": "異地辦公(8hr一週)",
                        "status": "已核准",
                    }
                ],
            },
            synced_at="now",
        )
        overtime = self.sm.get_applied_forms("JimmyChen", "overtime")
        self.assertEqual(len(overtime), 1)
        leave = self.sm.get_applied_forms("JimmyChen", "leave")
        self.assertEqual(leave[0]["leave_type"], "異地辦公(8hr一週)")

    def test_replace_is_idempotent(self):
        entries = {"overtime": [self._ot("2026/04/20", "1830", "2030")], "leave": []}
        self.sm.replace_applied_forms("JimmyChen", entries, "t1")
        self.sm.replace_applied_forms("JimmyChen", entries, "t2")
        applied = self.sm.get_applied_forms("JimmyChen")
        self.assertEqual(len(applied["overtime"]), 1)
        self.assertEqual(applied["last_full_sync"], "t2")

    def test_preserves_existing_synced_at_when_provided(self):
        self.sm.replace_applied_forms(
            "JimmyChen",
            {
                "overtime": [{**self._ot("2026/04/20", "1830", "2030"), "synced_at": "earlier"}],
                "leave": [],
            },
            synced_at="now",
        )
        applied = self.sm.get_applied_forms("JimmyChen", "overtime")
        self.assertEqual(applied[0]["synced_at"], "earlier")

    def test_record_applied_form_preserves_last_full_sync(self):
        self.sm.replace_applied_forms(
            "JimmyChen",
            {"overtime": [self._ot("2026/04/20", "1830", "2030")], "leave": []},
            synced_at="full-sync",
        )

        self.sm.record_applied_form(
            "JimmyChen",
            "overtime",
            {**self._ot("2026/04/21", "1830", "2030"), "status": "已送出 (本機新增)"},
            recorded_at="local-submit",
        )

        applied = self.sm.get_applied_forms("JimmyChen")
        self.assertEqual(applied["last_full_sync"], "full-sync")
        self.assertEqual(len(applied["overtime"]), 2)
        self.assertEqual(applied["overtime"][1]["synced_at"], "local-submit")

    def test_record_applied_form_updates_matching_entry(self):
        self.sm.record_applied_form(
            "JimmyChen",
            "leave",
            {
                "date": "2026/04/24",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 8,
                "leave_type": "補休假",
                "status": "已送出 (本機新增)",
            },
            recorded_at="first",
        )
        self.sm.record_applied_form(
            "JimmyChen",
            "leave",
            {
                "date": "2026/04/24",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 8,
                "leave_type": "異地辦公",
                "status": "已送出 (本機新增)",
            },
            recorded_at="second",
        )

        applied = self.sm.get_applied_forms("JimmyChen")
        self.assertNotIn("last_full_sync", applied)
        self.assertEqual(len(applied["leave"]), 1)
        self.assertEqual(applied["leave"][0]["leave_type"], "異地辦公")

    def test_unknown_user_returns_empty(self):
        self.assertEqual(self.sm.get_applied_forms("Nobody"), {})
        self.assertEqual(self.sm.get_applied_forms("Nobody", "overtime"), [])
        self.assertFalse(
            self.sm.is_form_already_applied(
                "Nobody",
                "overtime",
                {"date": "2026/04/20", "start_time": "1830", "end_time": "2030"},
            )
        )


if __name__ == "__main__":
    unittest.main()

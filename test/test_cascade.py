"""Tests for `lib/cascade.py` allocation logic."""

import unittest
from decimal import Decimal

from lib.cascade import (
    DEFAULT_CASCADES,
    MONTHLY_CAPS_HOURS,
    AllocationDecision,
    allocate,
)


def _balances(*, bukyu=5, tehuei=60, sick_paid=3, sick_half=None):
    """Build a balances dict matching `lib/portal/balances.fetch_balances()`."""
    items = {
        "補休假": {"remaining": bukyu},
        "事假(含家庭照顧假)": {"remaining": None},  # 法定上限,not capped here
    }
    if sick_paid is not None:
        items["有薪病假"] = {"remaining": sick_paid}
    if sick_half is not None:
        items["半薪病假"] = {"remaining": sick_half}
    items["異地辦公(8hr一週)"] = {"remaining": None}  # monthly-capped, see MONTHLY_CAPS_HOURS
    return {"items": items, "annual_leave": {"remaining_hours": tehuei}}


def _late(date_str: str, hours: int) -> dict:
    return {
        "date": date_str,
        "start_time": "0930",
        "end_time": f"{9 + hours:02d}30",
        "hours": hours,
        "type_hint": "late",
    }


def _wfh(date_str: str) -> dict:
    return {
        "date": date_str,
        "start_time": "0930",
        "end_time": "1830",
        "hours": 9,
        "type_hint": "WFH",
    }


def _sick(date_str: str, hours: int) -> dict:
    return {**_late(date_str, hours), "type_hint": "sick"}


class TestCascadeLate(unittest.TestCase):
    def test_bukyu_first_then_tehuei(self):
        # 補休 5h, 6 late entries totaling 6h → 5h compensated, 1h to 特休
        entries = [_late(f"2033/07/{n:02d}", 1) for n in range(4, 10)]
        out = allocate(entries, _balances())
        bukyu = [d for d in out.decisions if d.leave_type == "補休假"]
        tehuei = [d for d in out.decisions if d.leave_type == "特休假"]
        self.assertEqual(len(bukyu), 5)
        self.assertEqual(len(tehuei), 1)
        self.assertEqual(out.remaining["補休假"], 0)
        self.assertEqual(out.remaining["特休假"], 59)

    def test_entry_too_big_for_bukyu_falls_to_tehuei(self):
        # 補休 1h left, entry needs 2h → falls to 特休 (not split)
        entries = [_late("2033/07/05", 2)]
        out = allocate(entries, _balances(bukyu=1))
        self.assertEqual(out.decisions[0].leave_type, "特休假")
        # 補休 unchanged (entry never charged)
        self.assertEqual(out.remaining["補休假"], 1)
        self.assertEqual(out.remaining["特休假"], 58)

    def test_chronological_order_respected(self):
        # Plan should pick the cascade in date order so total balances reflect
        # the same path the user would take manually
        entries = [_late("2033/07/12", 1), _late("2033/07/06", 1)]
        out = allocate(entries, _balances(bukyu=1))
        # 7/06 picks 補休 (earlier date), 7/12 falls to 特休
        by_date = {d.entry["date"]: d.leave_type for d in out.decisions}
        self.assertEqual(by_date["2033/07/06"], "補休假")
        self.assertEqual(by_date["2033/07/12"], "特休假")


class TestCascadeSick(unittest.TestCase):
    def test_paid_first_then_half(self):
        entries = [_sick("2033/07/13", 3)]
        out = allocate(entries, _balances(sick_paid=3, sick_half=16))
        self.assertEqual(out.decisions[0].leave_type, "有薪病假")

    def test_falls_back_to_half_when_paid_exhausted(self):
        entries = [_sick("2033/07/13", 3)]
        out = allocate(entries, _balances(sick_paid=0, sick_half=16))
        self.assertEqual(out.decisions[0].leave_type, "半薪病假")


class TestCascadeWFH(unittest.TestCase):
    def test_monthly_cap_split_across_months(self):
        # 40h/month cap on 異地辦公(8hr一週). Five 9h Fridays in July = 45h —
        # exceeds the cap; 5th request should be insufficient.
        entries = [
            _wfh(d)
            for d in (
                "2033/07/01",
                "2033/07/08",
                "2033/07/15",
                "2033/07/22",
                "2033/07/29",
            )
        ]
        out = allocate(entries, _balances())
        wfh_assigned = [d for d in out.decisions if d.leave_type == "異地辦公(8hr一週)"]
        # 4 × 9h = 36h <= 40h ✓; 5th overflows
        self.assertEqual(len(wfh_assigned), 4)
        self.assertTrue(any(d.insufficient for d in out.decisions))
        # Month tracker reflects what was actually charged
        self.assertEqual(out.monthly_used.get(("異地辦公(8hr一週)", "2033-07")), 36)


class TestAlreadyApplied(unittest.TestCase):
    def test_already_applied_does_not_double_count_balance(self):
        # Portal's 剩餘時數 already reflects approved forms, so feeding
        # the same 補休 entry back via `already_applied` MUST NOT decrement
        # `remaining` again. (Bukyu balance still reads 5h after the
        # synced 1h applied form.)
        applied = [
            {
                "date": "2033/06/16",
                "start_time": "0930",
                "end_time": "1030",
                "hours": 1,
                "leave_type": "補休假",
            }
        ]
        entries = [_late("2033/07/06", 5)]
        out = allocate(entries, _balances(bukyu=5), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "補休假")
        self.assertEqual(out.remaining["補休假"], 0)

    def test_already_applied_balance_passthrough_regression(self):
        # Regression: Codex review P1. Cascade used to subtract applied
        # 補休 hours from `remaining` even though the Portal balance
        # already reflects them, double-counting and forcing fallback
        # tiers. Verify a 1h applied form does NOT eat into the 5h
        # remaining that came from the Portal.
        applied = [
            {
                "date": "2033/06/16",
                "start_time": "0930",
                "end_time": "1030",
                "hours": 1,
                "leave_type": "補休假",
            }
        ]
        entries = [_late("2033/07/06", 1)]
        out_with = allocate(entries, _balances(bukyu=5), already_applied=applied)
        out_without = allocate(entries, _balances(bukyu=5))
        self.assertEqual(out_with.remaining["補休假"], out_without.remaining["補休假"])
        # Both pick 補休 — applied form shouldn't change cascade outcome
        self.assertEqual(out_with.decisions[0].leave_type, "補休假")

    def test_already_applied_wfh_decreases_monthly_budget(self):
        # 06 月 already used 18h (06/10 + 06/17 WFH). Adding 06/24 leaves 27h
        # used <= 40h, so still fits.
        applied = [
            {
                "date": "2033/06/10",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 9,
                "leave_type": "異地辦公(8hr一週)",
            },
            {
                "date": "2033/06/17",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 9,
                "leave_type": "異地辦公(8hr一週)",
            },
        ]
        entries = [_wfh("2033/06/24")]
        out = allocate(entries, _balances(), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "異地辦公(8hr一週)")
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], 27)

    def test_decimal_hours_do_not_drift_past_the_cap(self):
        # 7.7 + 7.9 + 7.8 + 7.9 + 7.7 is 39.00000000000001 in floats.
        applied = [
            {"date": f"2033/06/{d:02d}", "hours": h, "leave_type": "異地辦公(8hr一週)"}
            for d, h in ((2, 7.7), (9, 7.9), (16, 7.8), (23, 7.9), (27, 7.7))
        ]
        entry = {**_wfh("2033/06/30"), "hours": 1, "end_time": "1030"}
        out = allocate([entry], _balances(), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "異地辦公(8hr一週)")
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], 40)

    def _wfh_with_used(self, used_hours, request_hours):
        applied = [
            {"date": f"2033/06/{i + 1:02d}", "hours": h, "leave_type": "異地辦公(8hr一週)"}
            for i, h in enumerate(used_hours)
        ]
        entry = {**_wfh("2033/06/30"), "hours": request_hours}
        return allocate([entry], _balances(), already_applied=applied)

    def test_exact_fit_after_decimal_hours_accepted(self):
        # 7.667 + 7.667 + 7.666 + 8 + 8 is exactly 39h; 1h more fills the cap.
        out = self._wfh_with_used([7.667, 7.667, 7.666, 8, 8], 1)
        self.assertEqual(out.decisions[0].leave_type, "異地辦公(8hr一週)")
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], 40)

    def test_over_cap_after_decimal_hours_rejected(self):
        # 7.334 × 3 + 8 + 8 is 38.002h; 2h more would be 40.002h.
        out = self._wfh_with_used([7.334, 7.334, 7.334, 8, 8], 2)
        self.assertIsNone(out.decisions[0].leave_type)
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], Decimal("38.002"))
        # Rounded for display only.
        self.assertIn("已用 38h", out.decisions[0].reason)

    def test_already_applied_decimal_hours_not_truncated(self):
        applied = [
            {
                "date": "2033/06/10",
                "start_time": "0930",
                "end_time": "1100",
                "hours": 1.5,
                "leave_type": "異地辦公(8hr一週)",
            }
        ]
        out = allocate([], _balances(), already_applied=applied)
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], 1.5)

    def test_dead_already_applied_forms_do_not_use_monthly_budget(self):
        # 31h approved + a withdrawn 1.5h form; a new 9h WFH still fits in 40h.
        def wfh(day, hours, status):
            return {
                "date": day,
                "start_time": "0930",
                "end_time": "1830",
                "hours": hours,
                "leave_type": "異地辦公(8hr一週)",
                "status": status,
            }

        applied = [
            wfh("2033/06/03", 9, "已核准"),
            wfh("2033/06/10", 9, "已核准"),
            wfh("2033/06/17", 9, "已核准"),
            wfh("2033/06/20", 4, "已核准"),
            wfh("2033/06/21", 1.5, "已撤回"),
            wfh("2033/06/22", 8, "流程停止（抽單）"),
            wfh("2033/06/23", 8, "主管駁回"),
        ]
        out = allocate([_wfh("2033/06/24")], _balances(), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "異地辦公(8hr一週)")
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2033-06")], 40)


class TestDecisionShape(unittest.TestCase):
    def test_decision_carries_entry_reference(self):
        e = _late("2033/07/06", 1)
        out = allocate([e], _balances())
        d = out.decisions[0]
        self.assertIs(d.entry, e)
        self.assertIsInstance(d, AllocationDecision)

    def test_default_cascades_have_known_keys(self):
        self.assertIn("leave_cascade_late", DEFAULT_CASCADES)
        self.assertEqual(DEFAULT_CASCADES["leave_cascade_late"][0], "補休假")
        self.assertIn("異地辦公(8hr一週)", MONTHLY_CAPS_HOURS)


if __name__ == "__main__":
    unittest.main()

"""Tests for `lib/cascade.py` allocation logic."""

import unittest

from lib.cascade import (
    DEFAULT_CASCADES,
    MONTHLY_CAPS_HOURS,
    AllocationDecision,
    allocate,
)


def _balances(*, bukyu=7, tehuei=81, sick_paid=0, sick_half=None):
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
        # 補休 7h, 8 late entries totaling 8h → 7h compensated, 1h to 特休
        entries = [_late(f"2026/05/{n:02d}", 1) for n in range(4, 12)]
        out = allocate(entries, _balances())
        bukyu = [d for d in out.decisions if d.leave_type == "補休假"]
        tehuei = [d for d in out.decisions if d.leave_type == "特休假"]
        self.assertEqual(len(bukyu), 7)
        self.assertEqual(len(tehuei), 1)
        self.assertEqual(out.remaining["補休假"], 0)
        self.assertEqual(out.remaining["特休假"], 80)

    def test_entry_too_big_for_bukyu_falls_to_tehuei(self):
        # 補休 1h left, entry needs 2h → falls to 特休 (not split)
        entries = [_late("2026/05/05", 2)]
        out = allocate(entries, _balances(bukyu=1))
        self.assertEqual(out.decisions[0].leave_type, "特休假")
        # 補休 unchanged (entry never charged)
        self.assertEqual(out.remaining["補休假"], 1)
        self.assertEqual(out.remaining["特休假"], 79)

    def test_chronological_order_respected(self):
        # Plan should pick the cascade in date order so total balances reflect
        # the same path the user would take manually
        entries = [_late("2026/05/12", 1), _late("2026/05/06", 1)]
        out = allocate(entries, _balances(bukyu=1))
        # 5/06 picks 補休 (earlier date), 5/12 falls to 特休
        by_date = {d.entry["date"]: d.leave_type for d in out.decisions}
        self.assertEqual(by_date["2026/05/06"], "補休假")
        self.assertEqual(by_date["2026/05/12"], "特休假")


class TestCascadeSick(unittest.TestCase):
    def test_paid_first_then_half(self):
        entries = [_sick("2026/05/04", 4)]
        out = allocate(entries, _balances(sick_paid=4, sick_half=16))
        self.assertEqual(out.decisions[0].leave_type, "有薪病假")

    def test_falls_back_to_half_when_paid_exhausted(self):
        entries = [_sick("2026/05/04", 4)]
        out = allocate(entries, _balances(sick_paid=0, sick_half=16))
        self.assertEqual(out.decisions[0].leave_type, "半薪病假")


class TestCascadeWFH(unittest.TestCase):
    def test_monthly_cap_split_across_months(self):
        # 40h/month cap on 異地辦公(8hr一週). Five 9h Fridays in May = 45h —
        # exceeds the cap; 5th request should be insufficient.
        entries = [
            _wfh(d)
            for d in (
                "2026/05/01",
                "2026/05/08",
                "2026/05/15",
                "2026/05/22",
                "2026/05/29",
            )
        ]
        out = allocate(entries, _balances())
        wfh_assigned = [d for d in out.decisions if d.leave_type == "異地辦公(8hr一週)"]
        # 4 × 9h = 36h <= 40h ✓; 5th overflows
        self.assertEqual(len(wfh_assigned), 4)
        self.assertTrue(any(d.insufficient for d in out.decisions))
        # Month tracker reflects what was actually charged
        self.assertEqual(out.monthly_used.get(("異地辦公(8hr一週)", "2026-05")), 36)


class TestAlreadyApplied(unittest.TestCase):
    def test_already_applied_does_not_double_count_balance(self):
        # Portal's 剩餘時數 already reflects approved forms, so feeding
        # the same 補休 entry back via `already_applied` MUST NOT decrement
        # `remaining` again. (Bukyu balance still reads 7h after the
        # synced 1h applied form.)
        applied = [
            {
                "date": "2026/04/16",
                "start_time": "0930",
                "end_time": "1030",
                "hours": 1,
                "leave_type": "補休假",
            }
        ]
        entries = [_late("2026/05/06", 7)]
        out = allocate(entries, _balances(bukyu=7), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "補休假")
        self.assertEqual(out.remaining["補休假"], 0)

    def test_already_applied_balance_passthrough_regression(self):
        # Regression: Codex review P1. Cascade used to subtract applied
        # 補休 hours from `remaining` even though the Portal balance
        # already reflects them, double-counting and forcing fallback
        # tiers. Verify a 1h applied form does NOT eat into the 7h
        # remaining that came from the Portal.
        applied = [
            {
                "date": "2026/04/16",
                "start_time": "0930",
                "end_time": "1030",
                "hours": 1,
                "leave_type": "補休假",
            }
        ]
        entries = [_late("2026/05/06", 1)]
        out_with = allocate(entries, _balances(bukyu=7), already_applied=applied)
        out_without = allocate(entries, _balances(bukyu=7))
        self.assertEqual(out_with.remaining["補休假"], out_without.remaining["補休假"])
        # Both pick 補休 — applied form shouldn't change cascade outcome
        self.assertEqual(out_with.decisions[0].leave_type, "補休假")

    def test_already_applied_wfh_decreases_monthly_budget(self):
        # 04 月 already used 18h (04/10 + 04/17 WFH). Adding 04/24 leaves 27h
        # used <= 40h, so still fits.
        applied = [
            {
                "date": "2026/04/10",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 9,
                "leave_type": "異地辦公(8hr一週)",
            },
            {
                "date": "2026/04/17",
                "start_time": "0930",
                "end_time": "1830",
                "hours": 9,
                "leave_type": "異地辦公(8hr一週)",
            },
        ]
        entries = [_wfh("2026/04/24")]
        out = allocate(entries, _balances(), already_applied=applied)
        self.assertEqual(out.decisions[0].leave_type, "異地辦公(8hr一週)")
        self.assertEqual(out.monthly_used[("異地辦公(8hr一週)", "2026-04")], 27)


class TestDecisionShape(unittest.TestCase):
    def test_decision_carries_entry_reference(self):
        e = _late("2026/05/06", 1)
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

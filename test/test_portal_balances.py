"""Tests for `lib/portal/balances.py`."""

import unittest
from unittest import mock

from lib.portal.balances import (
    _parse_hours,
    fetch_balances,
    format_balance_table,
    open_leave_form,
    parse_annual_panel,
    parse_items_panel,
)

# Real layout captured live 2026-06: the Portal wraps the grid in nested
# tables, so eval returns noise rows (a flattened blob + the four metric
# labels each on their own single-cell row) followed by the clean grid.
# The grid header has NO leading label cell and the metric rows carry NO
# label — order is the only anchor (可休總 / 目前可休 / 已休 / 剩餘).
ITEMS_ROWS = [
    # Decoy: the real Portal emits a wide flattened blob row that ALSO carries
    # a standalone "補休假" cell. Header detection must skip it (r[0] != 加班).
    [
        "可休總時數\n\n目前可休時數",
        "",
        "可休總時數",
        "已休(加班)時數",
        "剩餘時數",
        "",
        "補休假",
        "事假",
        "x",
        "y",
    ],
    ["可休總時數"],
    ["目前可休時數"],
    ["已休(加班)時數"],
    ["剩餘時數"],
    [""],
    [
        "加班",
        "補休假",
        "事假(含家庭照顧假)",
        "半薪病假",
        "有薪病假",
        "公假-公出",
        "忘刷忘帶卡",
        "榮譽假",
        "異地辦公(12hr一週)",
        "異地辦公(8hr一週)",
        "生日假",
    ],
    # 可休總時數
    [
        "",
        "28 小時",
        "",
        "",
        "40 小時 / 1 年",
        "",
        "2 工作天 或 4 次 / 1 年",
        "0小時 / 自訂期間",
        "60 小時 / 1 月",
        "40 小時 / 1 月",
        "1 工作天 / 1 年",
    ],
    # 目前可休時數 (blank in this capture)
    ["", "", "", "", "", "", "", "", "", "", ""],
    # 已休(加班)時數
    [
        "43 小時",
        "0 小時",
        "50 小時",
        "19 小時",
        "40 小時",
        "7 小時",
        "0.5 工作天 / 1次",
        "",
        "",
        "",
        "0 工作天",
    ],
    # 剩餘時數
    ["", "28 小時", "", "", "0 小時", "", "1.5 工作天 / 3次", "", "", "", "1 工作天"],
]

ANNUAL_ROWS = [
    ["特休假統計"],
    ["公司給假", "已休天數", "剩餘天數"],
    ["上期結轉", "結轉截止日", "本年度", "合計"],
    [
        "0 天又 1 小時 (1 小時)",
        "2027/4/14",
        "10 天(80 小時)",
        "10 天又 1 小時 (81 小時)",
        "0 天(0 小時)",
        "10 天又 1 小時 (81 小時)",
    ],
]


class TestParseHours(unittest.TestCase):
    def test_h_suffix(self):
        self.assertEqual(_parse_hours("8 小時"), 8)

    def test_bare_int(self):
        self.assertEqual(_parse_hours("8"), 8)

    def test_none_for_workdays(self):
        self.assertIsNone(_parse_hours("0 工作天"))
        self.assertIsNone(_parse_hours(""))


class TestParseItemsPanel(unittest.TestCase):
    def test_full_matrix(self):
        out = parse_items_panel(ITEMS_ROWS)
        # 補休假: total 28h, used 0h, remaining 28h (←真實值，先前解析器讀成全 None)
        bukyu = out["補休假"]
        self.assertEqual(bukyu["total"], 28)
        self.assertEqual(bukyu["used"], 0)
        self.assertEqual(bukyu["remaining"], 28)

        # 有薪病假: 已用完 — used 40, remaining 0 ("40 小時 / 1 年" 帶後綴 → total None)
        sick = out["有薪病假"]
        self.assertEqual(sick["used"], 40)
        self.assertEqual(sick["remaining"], 0)
        self.assertEqual(sick["total_raw"], "40 小時 / 1 年")

        # 半薪病假 / 事假: 法定無上限 → remaining None（cascade 視為可吸收）
        self.assertIsNone(out["半薪病假"]["remaining"])
        self.assertIsNone(out["事假(含家庭照顧假)"]["remaining"])

        # Workday-style values fall through as raw text only (non-小時 → None)
        forget = out["忘刷忘帶卡"]
        self.assertEqual(forget["used"], None)
        self.assertEqual(forget["used_raw"], "0.5 工作天 / 1次")

    def test_short_rows_returns_empty(self):
        self.assertEqual(parse_items_panel([["header"]]), {})


class TestParseAnnualPanel(unittest.TestCase):
    def test_picks_remaining_hours(self):
        out = parse_annual_panel(ANNUAL_ROWS)
        self.assertEqual(out["remaining_hours"], 81)
        self.assertEqual(out["grant_hours"], 81)  # 合計 81
        self.assertEqual(out["used_hours"], 0)


class TestOpenLeaveForm(unittest.TestCase):
    def test_click_success(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"ok": True}
        open_leave_form(portal, "http://x")
        portal.open.assert_called_once()
        portal.eval_json.assert_called_once()

    def test_click_failure_raises(self):
        portal = mock.Mock()
        portal.eval_json.return_value = {"error": "not found"}
        with self.assertRaises(RuntimeError):
            open_leave_form(portal, "http://x")


class TestFetchBalances(unittest.TestCase):
    def test_round_trip(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"ok": True},
            {"rows": ITEMS_ROWS},
            {"rows": ANNUAL_ROWS},
        ]
        out = fetch_balances(portal, "http://x")
        self.assertIn("items", out)
        self.assertIn("補休假", out["items"])
        self.assertEqual(out["items"]["補休假"]["remaining"], 28)
        self.assertEqual(out["annual_leave"]["remaining_hours"], 81)

    def test_missing_items_raises(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"ok": True},
            {"error": "no doc"},
        ]
        with self.assertRaises(RuntimeError):
            fetch_balances(portal, "http://x")


class TestFormatBalanceTable(unittest.TestCase):
    def test_includes_補休_and_特休(self):
        portal = mock.Mock()
        portal.eval_json.side_effect = [
            {"ok": True},
            {"rows": ITEMS_ROWS},
            {"rows": ANNUAL_ROWS},
        ]
        balances = fetch_balances(portal, "http://x")
        text = format_balance_table(balances)
        self.assertIn("補休假", text)
        # 不寫死數字：補休假剩餘由 fixture 解析得來，渲染後應出現在表內
        bukyu_rem = balances["items"]["補休假"]["remaining"]
        self.assertIn(f"{bukyu_rem}h", text)
        self.assertIn("特休假", text)
        annual_rem = balances["annual_leave"]["remaining_hours"]
        self.assertIn(f"{annual_rem}h", text)


if __name__ == "__main__":
    unittest.main()

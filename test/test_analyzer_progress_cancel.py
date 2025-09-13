import unittest


class TestAnalyzerProgressCancel(unittest.TestCase):
    def test_progress_callback_invoked(self):
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.parse_attendance_file("sample-attendance-data.txt", incremental=True)
        analyzer.group_records_by_day()

        calls = []
        analyzer.set_progress_callback(
            lambda step, cur, total: calls.append((step, cur, total))
        )
        analyzer.set_cancel_check(lambda: False)

        analyzer.analyze_attendance()
        # At least one progress call expected
        self.assertGreater(len(calls), 0)

    def test_cancel_early(self):
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.parse_attendance_file("sample-attendance-data.txt", incremental=True)
        analyzer.group_records_by_day()

        count = {"i": 0}

        def cancel_after_first():
            count["i"] += 1
            return count["i"] > 1

        analyzer.set_progress_callback(lambda *_: None)
        analyzer.set_cancel_check(cancel_after_first)
        analyzer.analyze_attendance()
        # Ensure cancel path was hit (i increments at least twice: before returning True)
        self.assertGreaterEqual(count["i"], 2)

    def test_progress_callback_exception_does_not_break(self):
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.parse_attendance_file("sample-attendance-data.txt", incremental=True)
        analyzer.group_records_by_day()

        def boom(*_args):
            raise RuntimeError("boom")

        analyzer.set_progress_callback(boom)
        analyzer.set_cancel_check(lambda: False)
        # Should not raise
        analyzer.analyze_attendance()

    def test_late_reason_depleted_forget_quota(self):
        from attendance_analyzer import (
            AttendanceAnalyzer,
            AttendanceRecord,
            AttendanceType,
            WorkDay,
        )
        from datetime import datetime
        from lib.policy import Rules

        analyzer = AttendanceAnalyzer()

        date = datetime(2025, 7, 1)
        checkin = AttendanceRecord(
            date=date,
            scheduled_time=datetime(2025, 7, 1, 10, 30),
            actual_time=datetime(2025, 7, 1, 10, 35),
            type=AttendanceType.CHECKIN,
            card_number="",
            source="",
            status="",
            processed="",
            operation="",
            note="",
        )
        checkout = AttendanceRecord(
            date=date,
            scheduled_time=datetime(2025, 7, 1, 19, 30),
            actual_time=datetime(2025, 7, 1, 19, 45),
            type=AttendanceType.CHECKOUT,
            card_number="",
            source="",
            status="",
            processed="",
            operation="",
            note="",
        )
        wd = WorkDay(
            date=date,
            checkin_record=checkin,
            checkout_record=checkout,
            is_friday=False,
            is_holiday=False,
        )

        # Deplete quota so forget punch is not available
        analyzer.forget_punch_usage[date.strftime("%Y-%m")] = (
            analyzer.config.forget_punch_allowance_per_month
        )

        analyzer._analyze_single_workday(wd, Rules())
        late_issues = [i for i in analyzer.issues if i.type.name == "LATE"]
        self.assertTrue(any("本月忘刷卡額度已用完" in i.description for i in late_issues))

    def test_status_row_when_no_current_user(self):
        from attendance_analyzer import AttendanceAnalyzer
        from datetime import datetime

        analyzer = AttendanceAnalyzer()
        analyzer._identify_complete_work_days = (  # type: ignore
            lambda: [datetime(2025, 7, 1)]
        )
        analyzer.current_user = None
        out = analyzer._compute_incremental_status_row()
        # when current_user is None, function computes status row from complete days
        self.assertEqual(out[0], '2025/07/01')


if __name__ == "__main__":
    unittest.main()

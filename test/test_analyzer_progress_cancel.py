import unittest


class TestAnalyzerProgressCancel(unittest.TestCase):
    def test_progress_callback_invoked(self):
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.parse_attendance_file('sample-attendance-data.txt', incremental=True)
        analyzer.group_records_by_day()

        calls = []
        analyzer.set_progress_callback(lambda step, cur, total: calls.append((step, cur, total)))
        analyzer.set_cancel_check(lambda: False)

        analyzer.analyze_attendance()
        # At least one progress call expected
        self.assertGreater(len(calls), 0)

    def test_cancel_early(self):
        from attendance_analyzer import AttendanceAnalyzer

        analyzer = AttendanceAnalyzer()
        analyzer.parse_attendance_file('sample-attendance-data.txt', incremental=True)
        analyzer.group_records_by_day()

        count = {'i': 0}

        def cancel_after_first():
            count['i'] += 1
            return count['i'] > 1

        analyzer.set_progress_callback(lambda *_: None)
        analyzer.set_cancel_check(cancel_after_first)
        analyzer.analyze_attendance()
        # Ensure cancel path was hit (i increments at least twice: before returning True)
        self.assertGreaterEqual(count['i'], 2)


if __name__ == '__main__':
    unittest.main()


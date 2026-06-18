"""Regression: parse_attendance_file must accept files without a header.

Previously line 1 was unconditionally skipped, silently dropping the first
record when the input had no header row (e.g. files produced by other tools).
"""

import os
import tempfile
import unittest

from attendance_analyzer import AttendanceAnalyzer

HEADER = "\t".join(
    [
        "應刷卡時段",
        "當日卡鐘資料",
        "刷卡別",
        "卡鐘編號",
        "資料來源",
        "異常狀態",
        "處理狀態",
        "異常處理作業",
        "備註",
    ]
)
ROW_IN = "2025/07/01 09:30\t2025/07/01 10:25\t上班\t1\t刷卡匯入\t遲到\t\t\t"
ROW_OUT = "2025/07/01 18:30\t2025/07/01 19:49\t下班\t1\t刷卡匯入\t\t\t\t"


class TestParseFirstLine(unittest.TestCase):
    def _write(self, lines: list[str]) -> str:
        fd, path = tempfile.mkstemp(prefix="202507-Tester-出勤資料-", suffix=".txt")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def test_file_with_header_parses_two_records(self) -> None:
        path = self._write([HEADER, ROW_IN, ROW_OUT])
        try:
            a = AttendanceAnalyzer()
            a.parse_attendance_file(path, incremental=False)
            self.assertEqual(len(a.records), 2)
        finally:
            os.remove(path)

    def test_file_without_header_parses_all_records(self) -> None:
        path = self._write([ROW_IN, ROW_OUT])
        try:
            a = AttendanceAnalyzer()
            a.parse_attendance_file(path, incremental=False)
            self.assertEqual(
                len(a.records), 2, "first data line must not be dropped as header"
            )
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()

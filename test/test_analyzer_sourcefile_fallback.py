import os
import tempfile
import unittest
from unittest import mock

from attendance_analyzer import AttendanceAnalyzer


class TestAnalyzerSourceFileFallback(unittest.TestCase):
    def test_source_file_name_fallback_on_exception(self):
        # Prepare a minimal valid file (only header) so parsing proceeds
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'any.txt')
            with open(path, 'w', encoding='utf-8') as f:
                f.write('應刷卡時段\t當日卡鐘資料\t刷卡別\t卡鐘編號\t資料來源\t異常狀態\t處理狀態\t異常處理作業\t備註\n')

            an = AttendanceAnalyzer()

            # Patch only attendance_analyzer.os to a shim whose basename raises
            class _DummyPath:
                @staticmethod
                def basename(_):
                    raise RuntimeError('boom')

            class _DummyOS:
                path = _DummyPath()

            with mock.patch('attendance_analyzer.os', new=_DummyOS()):
                an.parse_attendance_file(path, incremental=False)

            self.assertIsNone(an.source_file_name)


if __name__ == '__main__':
    unittest.main()

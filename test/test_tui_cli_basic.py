import os
import sys
import unittest
from unittest import mock


class TestTuiCliBasic(unittest.TestCase):
    def setUp(self):
        # ensure logging doesn't spam stdout in tests
        pass

    def _run_cli(self, argv):
        from lib import cli
        with self.assertRaises(SystemExit) as cm:
            cli.run(argv)
        return cm.exception.code

    def test_tui_import_error_message_and_exit(self):
        # Arrange
        argv = [
            'prog',
            'sample-attendance-data.txt',
            'csv',
            '--tui',
        ]

        # Simulate textual not installed by raising ImportError in importlib
        with mock.patch('importlib.import_module', side_effect=ImportError()):
            # Capture logs
            import logging
            from io import StringIO
            stream = StringIO()
            handler = logging.StreamHandler(stream)
            root = logging.getLogger('attendance_analyzer') if logging.getLogger('attendance_analyzer').handlers else logging.getLogger()
            logging.getLogger().addHandler(handler)
            try:
                code = self._run_cli(argv)
            finally:
                logging.getLogger().removeHandler(handler)

        self.assertEqual(code, 1)
        msg = stream.getvalue()
        self.assertIn('未安裝 Textual', msg)
        self.assertIn('pip install .[tui]', msg)

    def test_tui_flag_prefill_passed_to_launcher(self):
        argv = [
            'prog',
            'sample-attendance-data.txt',
            'csv',
            '--tui',
            '--full',
        ]

        called = {}

        def fake_launch(prefill):
            called['prefill'] = prefill

        with mock.patch('tui.launch_tui', side_effect=fake_launch):
            # Avoid importing textual inside launcher during this test
            from lib import cli
            # Should not SystemExit when launcher exists
            cli.run(argv)

        self.assertIn('prefill', called)
        pre = called['prefill']
        self.assertEqual(pre['filepath'], 'sample-attendance-data.txt')
        self.assertEqual(pre['format'], 'csv')
        self.assertTrue(pre['full'])
        self.assertFalse(pre['incremental'])

    def test_cli_compatibility_without_tui(self):
        # Should execute normal flow without raising SystemExit
        from lib import cli
        cli.run(['prog', 'sample-attendance-data.txt', 'csv'])


if __name__ == '__main__':
    unittest.main()

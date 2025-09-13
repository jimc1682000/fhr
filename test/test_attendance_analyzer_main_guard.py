import runpy
import unittest
from unittest import mock


class TestMainGuard(unittest.TestCase):
    def test_module_main_invokes_cli_run(self):
        with mock.patch('lib.cli.run') as mock_run:
            # Execute attendance_analyzer as if __main__ to cover main() guard
            runpy.run_module('attendance_analyzer', run_name='__main__')
            mock_run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
"""Category: Analyzer
Purpose: Execute module under __main__ to cover CLI handoff."""

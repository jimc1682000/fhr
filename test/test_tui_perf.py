import time
import unittest

try:
    from textual.testing import Pilot  # type: ignore
    from tui.wizard_app import WizardApp
    HAS_TEXTUAL = True
except Exception:
    HAS_TEXTUAL = False


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class TestTuiColdStart(unittest.IsolatedAsyncioTestCase):
    async def test_cold_start_under_threshold(self):
        import os
        start = time.monotonic()
        app = WizardApp(prefill={'filepath': 'sample-attendance-data.txt', 'format': 'csv'}, auto_close=True)
        async with Pilot(app):
            pass
        elapsed = time.monotonic() - start
        # Local threshold 2s; CI lenient 3s
        threshold = 3.0 if os.getenv('GITHUB_ACTIONS') else 2.0
        self.assertLess(elapsed, threshold)


if __name__ == '__main__':
    unittest.main()

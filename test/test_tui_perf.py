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
        start = time.monotonic()
        app = WizardApp(prefill={'filepath': 'sample-attendance-data.txt', 'format': 'csv'}, auto_close=True)
        async with Pilot(app):
            pass
        elapsed = time.monotonic() - start
        # Allow 3s on CI to be lenient
        self.assertLess(elapsed, 3.0)


if __name__ == '__main__':
    unittest.main()


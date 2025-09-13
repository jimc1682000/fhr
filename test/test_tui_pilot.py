import os
import unittest


try:
    from textual.testing import Pilot  # type: ignore
    from tui.wizard_app import WizardApp
    HAS_TEXTUAL = True
except Exception:
    HAS_TEXTUAL = False


@unittest.skipUnless(HAS_TEXTUAL, "textual not installed")
class TestWizardPilot(unittest.IsolatedAsyncioTestCase):
    async def test_key_flow_and_preview_limit(self):
        prefill = {
            'filepath': 'sample-attendance-data.txt',
            'format': 'csv',
            'incremental': True,
            'full': False,
            'reset_state': False,
        }
        app = WizardApp(prefill=prefill, auto_close=False)
        async with Pilot(app) as pilot:
            # Step 1 -> Step 2
            await pilot.press("enter")
            self.assertEqual(app.step, 2)
            # Step 2 -> Step 3
            await pilot.press("enter")
            self.assertEqual(app.step, 3)
            # Run (r) -> Step 4 (Preview)
            await pilot.press("r")
            self.assertEqual(app.step, 4)
            table = app.query_one("#preview")
            # DataTable exposes row_count attribute
            self.assertTrue(getattr(table, 'row_count', 0) <= 200)
            # Next -> Done
            await pilot.press("enter")
            self.assertEqual(app.step, 5)
            # Quit
            await pilot.press("q")


if __name__ == '__main__':
    unittest.main()


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
    async def asyncSetUp(self):
        # Avoid real network/backoff in analyzer during UI tests
        import os

        os.environ["HOLIDAY_API_MAX_RETRIES"] = "0"
        os.environ["HOLIDAY_API_BACKOFF_BASE"] = "0"
        os.environ["HOLIDAY_API_MAX_BACKOFF"] = "0"

    async def test_key_flow_and_preview_limit(self):
        prefill = {
            "filepath": "sample-attendance-data.txt",
            "format": "csv",
            "incremental": True,
            "full": False,
            "reset_state": False,
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
            self.assertTrue(getattr(table, "row_count", 0) <= 200)
            # Log sink should have captured analyzer logs
            self.assertGreater(len(app.log_sink), 0)
            # Styles applied for first rows should reflect mapping
            self.assertTrue(len(getattr(app, "_styles_applied", [])) > 0)
            # Next -> Done
            await pilot.press("enter")
            self.assertEqual(app.step, 5)
            # Quit
            await pilot.press("q")

    async def test_block_next_on_invalid_file_then_fix(self):
        prefill = {
            "filepath": "nonexistent.txt",
            "format": "csv",
            "incremental": True,
            "full": False,
            "reset_state": False,
        }
        app = WizardApp(prefill=prefill, auto_close=False)
        async with Pilot(app) as pilot:
            # Attempt to go next with invalid file
            await pilot.press("enter")
            # Should stay on step 1
            self.assertEqual(app.step, 1)
            # Now set a valid path and proceed
            app.query_one("#filepath").value = "sample-attendance-data.txt"
            await pilot.press("enter")
            self.assertEqual(app.step, 2)


if __name__ == "__main__":
    unittest.main()

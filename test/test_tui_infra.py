import os
import time
import unittest
import threading
from unittest import mock


class TestI18n(unittest.TestCase):
    def test_detect_language_env_override(self):
        with mock.patch.dict(os.environ, {"FHR_LANG": "en"}, clear=False):
            from tui.i18n import detect_language

            self.assertEqual(detect_language(), "en")

    def test_detect_language_default_chinese_for_zh_locale(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            import locale

            with mock.patch("locale.getdefaultlocale", return_value=("zh_TW", "UTF-8")):
                from tui.i18n import detect_language

                self.assertEqual(detect_language(), "zh_TW")

    def test_translator_fallback_returns_msgid(self):
        from tui.i18n import get_translator

        _ = get_translator()
        self.assertEqual(_("UNKNOWN_KEY"), "UNKNOWN_KEY")


class TestLoggingBridge(unittest.TestCase):
    def test_textual_log_handler_appends_messages(self):
        from tui.logging_bridge import TextualLogHandler
        import logging

        sink = []
        handler = TextualLogHandler(sink)
        handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        logger = logging.getLogger("tui-test")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            logger.info("hello")
            logger.warning("warn")
        finally:
            logger.removeHandler(handler)
        self.assertEqual(sink, ["INFO:hello", "WARNING:warn"])


class TestAdapters(unittest.TestCase):
    def test_run_analysis_in_thread_progress_and_cancel(self):
        from tui.adapters import run_analysis_in_thread

        calls = []

        def fake_worker(args, progress_cb, cancel_event):
            total = 5
            for i in range(total):
                if cancel_event.is_set():
                    return
                progress_cb("step", i + 1, total)
            return

        cancel = threading.Event()

        def progress(step, cur, total):
            calls.append((step, cur, total))

        th = run_analysis_in_thread(fake_worker, {}, progress, cancel)
        th.join(timeout=2)
        self.assertFalse(th.is_alive())
        self.assertEqual(len(calls), 5)

    def test_truncate_rows_limits_to_200(self):
        from tui.adapters import truncate_rows

        rows = list(range(5000))
        out = truncate_rows(rows, 200)
        self.assertEqual(len(out), 200)

    def test_cancel_mid_run_with_injected_task(self):
        from tui.adapters import run_in_thread
        import threading
        import time

        cancel = threading.Event()
        ticks = []

        def long_task():
            # simulate long work
            for i in range(1000):
                if cancel.is_set():
                    break
                ticks.append(i)
                time.sleep(0.001)

        th = run_in_thread(long_task)
        time.sleep(0.02)
        cancel.set()
        th.join(timeout=0.5)
        self.assertFalse(th.is_alive())


if __name__ == "__main__":
    unittest.main()

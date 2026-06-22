"""Tests for `lib/portal/client.py` (agent-browser wrapper).

We mock `subprocess.run` so the suite never shells out to a real CLI.
"""

import subprocess
import unittest
from unittest import mock

from lib.portal.client import (
    AgentBrowserError,
    AgentBrowserMissing,
    LoginTimeout,
    PortalSession,
    _parse_eval_output,
    ensure_installed,
    ensure_login,
    is_logged_in,
    js_escape,
)


def _ok(stdout: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _err(returncode: int = 1, stderr: str = "boom") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


class TestEnsureInstalled(unittest.TestCase):
    def test_missing_raises(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(AgentBrowserMissing):
                ensure_installed()

    def test_present_no_raise(self):
        with mock.patch("shutil.which", return_value="/usr/local/bin/agent-browser"):
            ensure_installed()  # no raise


class TestParseEvalOutput(unittest.TestCase):
    def test_extracts_dict(self):
        raw = '✓ Done\n{"foo": 1}'
        self.assertEqual(_parse_eval_output(raw), {"foo": 1})

    def test_extracts_list(self):
        raw = '[{"a": 1}]'
        self.assertEqual(_parse_eval_output(raw), [{"a": 1}])

    def test_primitive_true(self):
        self.assertIs(_parse_eval_output("true"), True)

    def test_primitive_false(self):
        self.assertIs(_parse_eval_output("false"), False)

    def test_int(self):
        self.assertEqual(_parse_eval_output("42"), 42)

    def test_string_fallthrough(self):
        self.assertEqual(_parse_eval_output("hello"), "hello")

    def test_empty(self):
        self.assertIsNone(_parse_eval_output(""))


class TestJsEscape(unittest.TestCase):
    def test_apostrophe(self):
        self.assertEqual(js_escape("it's"), "it\\'s")

    def test_newline(self):
        self.assertEqual(js_escape("a\nb"), "a\\nb")

    def test_backslash(self):
        self.assertEqual(js_escape(r"a\b"), r"a\\b")


class TestPortalSession(unittest.TestCase):
    def _portal(self) -> PortalSession:
        # Skip the install probe so we don't need shutil.which patching here.
        return PortalSession(session="test-sess", check=False)

    def test_open_invokes_cli(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok("✓ ok")) as run:
            portal.open("http://x")
        args = run.call_args[0][0]
        self.assertEqual(args[1:3], ["open", "http://x"])
        self.assertIn("--session", args)
        self.assertIn("test-sess", args)

    def test_open_headed_flag(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok("ok")) as run:
            portal.open("http://x", headed=True)
        self.assertIn("--headed", run.call_args[0][0])

    def test_eval_json_parses_dict(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok('✓ Done\n{"v": 7}')):
            self.assertEqual(portal.eval_json("()"), {"v": 7})

    def test_nonzero_raises(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_err(2, "nope")):
            with self.assertRaises(AgentBrowserError):
                portal.open("http://x")

    def test_dialog_accept_swallows_failures(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_err(1, "no dialog")):
            portal.dialog_accept()  # no raise

    def test_missing_binary_raises(self):
        portal = self._portal()
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(AgentBrowserMissing):
                portal.open("http://x")

    def test_timeout_raises(self):
        portal = self._portal()
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1)):
            with self.assertRaises(AgentBrowserError):
                portal.open("http://x")

    def test_context_manager(self):
        portal = self._portal()
        with portal as p:
            self.assertIs(p, portal)

    def test_simple_wrappers_invoke_cli(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok("http://here")) as run:
            portal.wait(250)
            self.assertEqual(portal.get_url(), "http://here")
            portal.click_ref("@e1")
            portal.select_ref("@e2", "全部")
        verbs = [c[0][0][1] for c in run.call_args_list]
        self.assertEqual(verbs, ["wait", "get", "click", "select"])

    def test_close_swallows_error(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_err(1, "no daemon")):
            portal.close()  # no raise

    def test_close_ok(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok()):
            portal.close()

    def test_screenshot_returns_true_on_success(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_ok()) as run:
            self.assertTrue(portal.screenshot("/tmp/a.png"))
            self.assertTrue(portal.screenshot("/tmp/a.png", full=True))
        self.assertIn("--full", run.call_args[0][0])

    def test_screenshot_returns_false_on_error(self):
        portal = self._portal()
        with mock.patch("subprocess.run", return_value=_err(1, "closed")):
            self.assertFalse(portal.screenshot("/tmp/a.png"))


class TestParseEvalEdge(unittest.TestCase):
    def test_json_like_but_invalid_returns_candidate(self):
        # 命中 _JSON_RE 但 json.loads 失敗 → 回傳原字串候選
        out = _parse_eval_output("✓ Done\n{oops not json}")
        self.assertEqual(out, "{oops not json}")


class TestSessionContextManager(unittest.TestCase):
    def test_session_sugar_yields_portal(self):
        from lib.portal.client import session

        with session("sess-x", check=False) as portal:
            self.assertIsInstance(portal, PortalSession)
            self.assertEqual(portal.session, "sess-x")


class TestIsLoggedIn(unittest.TestCase):
    def _portal(self) -> PortalSession:
        return PortalSession(session="t", check=False)

    def test_back_on_login_url(self):
        portal = self._portal()
        with (
            mock.patch.object(portal, "open"),
            mock.patch.object(portal, "get_url", return_value="http://x/LoginFOrginal.asp"),
            mock.patch("time.sleep"),
        ):
            self.assertFalse(is_logged_in(portal, "http://x"))

    def test_authenticated_path(self):
        portal = self._portal()
        with (
            mock.patch.object(portal, "open"),
            mock.patch.object(
                portal, "get_url", return_value="http://x/ehrPortal/DEPT/Personal.asp"
            ),
            mock.patch("time.sleep"),
        ):
            self.assertTrue(is_logged_in(portal, "http://x"))

    def test_chrome_error(self):
        portal = self._portal()
        with (
            mock.patch.object(portal, "open"),
            mock.patch.object(portal, "get_url", return_value="chrome-error://broken"),
            mock.patch("time.sleep"),
        ):
            self.assertFalse(is_logged_in(portal, "http://x"))


class TestEnsureLogin(unittest.TestCase):
    def _portal(self) -> PortalSession:
        return PortalSession(session="t", check=False)

    def test_already_logged_in_no_open(self):
        portal = self._portal()
        with (
            mock.patch("lib.portal.client.is_logged_in", return_value=True),
            mock.patch.object(portal, "open") as op,
            mock.patch("time.sleep"),
        ):
            ensure_login(portal, "http://x")
        op.assert_not_called()

    def test_transitions_to_logged_in(self):
        portal = self._portal()
        urls = iter(
            [
                "http://x/LoginFOrginal.asp",
                "http://x/LoginFOrginal.asp",
                "http://x/ehrPortal/DEPT/Home.asp",
            ]
        )
        with (
            mock.patch("lib.portal.client.is_logged_in", return_value=False),
            mock.patch.object(portal, "open"),
            mock.patch.object(portal, "get_url", side_effect=lambda: next(urls)),
            mock.patch("time.sleep"),
        ):
            ensure_login(portal, "http://x", poll_interval_secs=0, max_wait_secs=60)

    def test_timeout(self):
        portal = self._portal()
        with (
            mock.patch("lib.portal.client.is_logged_in", return_value=False),
            mock.patch.object(portal, "open"),
            mock.patch.object(portal, "get_url", return_value="http://x/LoginFOrginal.asp"),
            mock.patch("time.sleep"),
        ):
            with self.assertRaises(LoginTimeout):
                ensure_login(portal, "http://x", poll_interval_secs=0, max_wait_secs=0)


if __name__ == "__main__":
    unittest.main()

"""`agent-browser` CLI wrapper.

`agent-browser` (https://github.com/vercel-labs/agent-browser) is an
optional Node.js CLI that drives a persistent Chromium session. We
shell out to it via subprocess for all Portal automation — `attendance`,
`approvals`, `balances`, `apply_forms`.

Design choices:
  - The binary is an OPTIONAL dep. `PortalSession.__enter__()` probes
    `agent-browser --version`; missing → AgentBrowserMissing with an
    install hint, callers can handle gracefully.
  - One session name per logical run (default: `"fhr"`, override via
    env `AGENT_BROWSER_SESSION`). The daemon persists between commands
    so login state is reused.
  - All `eval` calls go through `eval_json()`: the helper wraps the
    JS in a regex-aware JSON extractor matching what code_agent_hr's
    `browser_eval()` did. The agent-browser CLI prints assorted noise
    around the value; we accept either a top-level JSON object/array
    or a primitive (`true` / `false` / int / string).
  - We deliberately do NOT support arbitrary Python <-> Portal data
    flows here — only what the higher-level modules need.

Security policy (from CLAUDE.md): NEVER pass user credentials through
this wrapper. The login flow is `ensure_login()`, which opens the
login page in headed mode and POLLS the current URL until it changes
away from the login screen. The user types their password directly
into the browser window.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


class AgentBrowserError(RuntimeError):
    """A non-zero exit / unparseable output from `agent-browser`."""


class AgentBrowserMissing(RuntimeError):
    """`agent-browser` CLI is not installed or not on PATH."""

    DEFAULT_HINT = (
        "agent-browser CLI 未安裝。請執行：\n"
        "  npm install -g agent-browser\n"
        "  agent-browser install\n"
        "或將 npm 全域 bin 加入 PATH。"
    )


class LoginTimeout(RuntimeError):
    """`ensure_login` polled too long without seeing a login transition."""


_JSON_RE = re.compile(r"[\[\{].*[\]\}]", re.DOTALL)


def _binary() -> str:
    return os.environ.get("AGENT_BROWSER_BIN", "agent-browser")


def _default_session() -> str:
    return os.environ.get("AGENT_BROWSER_SESSION", "fhr")


def ensure_installed() -> None:
    """Raise `AgentBrowserMissing` if the CLI isn't reachable."""
    if shutil.which(_binary()) is None:
        raise AgentBrowserMissing(AgentBrowserMissing.DEFAULT_HINT)


class PortalSession:
    """Context manager around the agent-browser daemon.

    Usage:
        with PortalSession() as portal:
            portal.open("http://...")
            data = portal.eval_json("({foo: 1})")

    The daemon itself is persistent: closing this context does NOT kill
    it, so consecutive commands reuse the logged-in session. Callers
    that want a hard reset can call `close()` explicitly.
    """

    def __init__(
        self, session: str | None = None, *, check: bool = True, timeout_secs: int = 30
    ):
        self.session = session or _default_session()
        self.timeout_secs = timeout_secs
        if check:
            ensure_installed()

    # ---------- subprocess primitives ----------

    def _run(
        self, args: list[str], *, timeout: int | None = None, capture: bool = True
    ) -> str:
        cmd = [_binary(), *args, "--session", self.session]
        try:
            result = subprocess.run(
                cmd,
                capture_output=capture,
                text=True,
                timeout=timeout or self.timeout_secs,
                check=False,
            )
        except FileNotFoundError as e:
            raise AgentBrowserMissing(AgentBrowserMissing.DEFAULT_HINT) from e
        except subprocess.TimeoutExpired as e:
            raise AgentBrowserError(
                f"agent-browser timed out after {self.timeout_secs}s: {' '.join(cmd)}"
            ) from e
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise AgentBrowserError(
                f"agent-browser exited {result.returncode}: {stderr or '(no stderr)'}\n"
                f"cmd: {' '.join(cmd)}"
            )
        return (result.stdout or "").strip()

    # ---------- public surface ----------

    def open(self, url: str, *, headed: bool = False) -> str:
        args = ["open", url]
        if headed:
            args.append("--headed")
        return self._run(args)

    def wait(self, ms: int) -> None:
        self._run(["wait", str(ms)])

    def get_url(self) -> str:
        return self._run(["get", "url"])

    def click_ref(self, ref: str) -> None:
        self._run(["click", ref])

    def select_ref(self, ref: str, value: str) -> None:
        self._run(["select", ref, value])

    def dialog_accept(self) -> None:
        # Best-effort: agent-browser exits non-zero when no dialog is open.
        # That's expected and not an error.
        try:
            self._run(["dialog", "accept"])
        except AgentBrowserError:
            pass

    def eval_json(self, js: str) -> Any:
        """Run `agent-browser eval <js>` and parse the result.

        The CLI prints extra noise (`✓ Done`, etc.) before / after the
        JSON value; we extract the JSON-shaped substring with a regex
        match. Booleans / ints fall through as primitives.
        """
        raw = self._run(["eval", js])
        return _parse_eval_output(raw)

    def close(self) -> None:
        try:
            self._run(["close"])
        except AgentBrowserError:
            pass

    def screenshot(self, out_path: str, *, full: bool = False) -> bool:
        """Save a PNG of the current page. Returns False if agent-browser
        couldn't write the file (e.g. closed daemon). Caller handles failure."""
        args = ["screenshot", out_path]
        if full:
            args.append("--full")
        try:
            self._run(args)
            return True
        except AgentBrowserError:
            return False

    # ---------- context manager ----------

    def __enter__(self) -> PortalSession:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        # Don't close — let the daemon persist for follow-up commands.
        return None


def _parse_eval_output(raw: str) -> Any:
    """Pull a JSON-shaped value out of the raw `agent-browser eval` output.

    The CLI tends to print:
        ✓ Done
        {...payload...}
    or sometimes nested status lines around the value. We try a regex
    JSON match first, then fall back to primitive coercion.
    """
    if not raw:
        return None
    m = _JSON_RE.search(raw)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return candidate
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        return raw


@contextmanager
def session(name: str | None = None, **kwargs):
    """Functional sugar matching `with PortalSession(...) as portal:`."""
    portal = PortalSession(name, **kwargs)
    try:
        yield portal
    finally:
        pass  # see PortalSession.__exit__


# ---------- login helpers ----------

_LOGIN_PATH_HINTS = ("login", "LoginF")  # 104 EHR pages we recognize


def is_logged_in(portal: PortalSession, base_url: str) -> bool:
    """Probe an authenticated page; if we land back on a login URL we
    treat the session as logged out."""
    portal.open(f"{base_url}/DEPT/Personal_Atten_Defaut.asp")
    time.sleep(2)
    url = portal.get_url() or ""
    if not url or "chrome-error" in url:
        return False
    if any(hint.lower() in url.lower() for hint in _LOGIN_PATH_HINTS):
        return False
    return "/ehrPortal/" in url or "/WorkflowWeb/" in url


def ensure_login(
    portal: PortalSession,
    base_url: str,
    *,
    max_wait_secs: int = 600,
    poll_interval_secs: int = 3,
) -> None:
    """If not logged in, open the login page in headed mode and poll
    until the URL transitions away. Raises `LoginTimeout` if the user
    never logs in within `max_wait_secs`."""
    if is_logged_in(portal, base_url):
        logger.info("✅ 已登入 (session=%s)", portal.session)
        return

    logger.info("🚀 開啟瀏覽器，請手動登入...")
    portal.open(f"{base_url}/LoginFOrginal.asp", headed=True)
    deadline = time.time() + max_wait_secs
    dot_count = 0
    while time.time() < deadline:
        time.sleep(poll_interval_secs)
        url = portal.get_url() or ""
        if (
            url
            and "login" not in url.lower()
            and "loginf" not in url.lower()
            and ("/ehrPortal/" in url or "/WorkflowWeb/" in url)
        ):
            logger.info("\n🎉 登入成功 (session=%s)", portal.session)
            time.sleep(1)
            return
        dot_count += 1
        if dot_count % 20 == 0:
            logger.info("(等待登入中... %d s)", dot_count * poll_interval_secs)
    raise LoginTimeout(
        f"等待登入超過 {max_wait_secs}s — 請確認瀏覽器視窗有開、帳密輸入正確、且網路通暢"
    )


def js_escape(s: str) -> str:
    """Safely embed a Python string in a single-quoted JavaScript literal."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

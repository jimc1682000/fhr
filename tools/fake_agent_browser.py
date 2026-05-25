#!/usr/bin/env python3
"""Fake `agent-browser` CLI for offline E2E.

Set `FHR_FAKE_AB_FIXTURE_DIR` to a fixtures directory and put this
script on PATH (or point `AGENT_BROWSER_BIN` at it). Honors the small
subset of `agent-browser` commands that `lib/portal/client.py` uses,
returning canned stdout instead of driving a real browser.

Fixtures layout (relative to FHR_FAKE_AB_FIXTURE_DIR):
  state/                  — per-session state files (auto-managed)
  open/<slug>.txt         — stdout for `open <url>`; slug = url path
                            with non-alnum replaced by `_`. Optional.
  eval/<sha1>.json        — JSON body for `eval <js>`. `sha1` is the
                            first 10 chars of sha1(js). Required for
                            every distinct eval call the tests exercise.
                            Body is what `agent-browser eval` would
                            print (we wrap it with ✓ markers).
  snapshot/<seq>.txt      — sequential snapshot outputs. <seq> is a
                            zero-padded counter per session.
  screenshot.png          — single canned PNG copied to every
                            `screenshot <path>` invocation. Override
                            per-call via `screenshot/<basename>.png`.

Environment knobs:
  FHR_FAKE_AB_FIXTURE_DIR  required — fixtures root
  FHR_FAKE_AB_TRACE        if set, append each call to trace.log
  FHR_FAKE_AB_LOG_DIR      override log directory (default fixture_dir)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path


def _fixture_dir() -> Path:
    d = os.environ.get("FHR_FAKE_AB_FIXTURE_DIR")
    if not d:
        sys.stderr.write(
            "fake_agent_browser: FHR_FAKE_AB_FIXTURE_DIR not set\n"
        )
        sys.exit(2)
    p = Path(d)
    if not p.is_dir():
        sys.stderr.write(f"fake_agent_browser: fixture dir missing: {p}\n")
        sys.exit(2)
    return p


def _session_state_path(fixture_dir: Path, session: str) -> Path:
    state_dir = fixture_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", session)
    return state_dir / f"{safe}.json"


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"current_url": "", "snapshot_seq": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"current_url": "", "snapshot_seq": 0}


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _trace(fixture_dir: Path, args: list[str]) -> None:
    if not os.environ.get("FHR_FAKE_AB_TRACE"):
        return
    log_dir = Path(os.environ.get("FHR_FAKE_AB_LOG_DIR", str(fixture_dir)))
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "trace.log").open("a", encoding="utf-8") as f:
        f.write(" ".join(args) + "\n")


def _split_session(raw_args: list[str]) -> tuple[list[str], str]:
    """Strip `--session NAME` from raw args; return (clean, session)."""
    out: list[str] = []
    session = "default"
    i = 0
    while i < len(raw_args):
        if raw_args[i] == "--session" and i + 1 < len(raw_args):
            session = raw_args[i + 1]
            i += 2
            continue
        out.append(raw_args[i])
        i += 1
    return out, session


def _slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:120]


def _cmd_open(args: list[str], fixture_dir: Path, state: dict) -> int:
    if not args:
        print("fake_agent_browser: open needs <url>", file=sys.stderr)
        return 2
    url = args[0]
    state["current_url"] = url
    # Look up a fixture if one exists; otherwise print a fake success line.
    slug = _slugify(url)
    fixture = fixture_dir / "open" / f"{slug}.txt"
    if fixture.exists():
        print(fixture.read_text(encoding="utf-8").rstrip())
    else:
        print(f"✓ {url}")
    return 0


def _cmd_wait(args: list[str], fixture_dir: Path, state: dict) -> int:
    # No real wait — tests run fast.
    return 0


def _cmd_get(args: list[str], fixture_dir: Path, state: dict) -> int:
    if not args:
        return 2
    target = args[0]
    if target == "url":
        print(state.get("current_url", ""))
        return 0
    if target == "title":
        fixture = fixture_dir / "get" / "title.txt"
        print(fixture.read_text(encoding="utf-8").rstrip()
              if fixture.exists() else "")
        return 0
    # Unsupported sub — print empty.
    return 0


def _cmd_eval(args: list[str], fixture_dir: Path, state: dict) -> int:
    if not args:
        return 2
    js = args[0]
    sha = hashlib.sha1(js.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    fixture = fixture_dir / "eval" / f"{sha}.json"
    if not fixture.exists():
        # Per-fixture-dir default (lets a single _default.json catch every
        # un-keyed eval, useful for the dry-run path where most evals just
        # return `{ok: true}` and the JS callsites don't read the value).
        default = fixture_dir / "eval" / "_default.json"
        if default.exists():
            fixture = default
        else:
            # Built-in safe default so callers don't have to populate one.
            print("✓ Done")
            print('{"success": true, "ok": true, "matched": 1, "matches": []}')
            return 0
    body = fixture.read_text(encoding="utf-8").rstrip()
    # agent-browser CLI prints stdout with a small marker; tests parse JSON
    # with regex so any wrapping is fine.
    print("✓ Done")
    print(body)
    return 0


def _cmd_snapshot(args: list[str], fixture_dir: Path, state: dict) -> int:
    snap_dir = fixture_dir / "snapshot"
    if not snap_dir.exists():
        return 0
    seq = state.get("snapshot_seq", 0) + 1
    candidates = sorted(snap_dir.glob("*.txt"))
    if not candidates:
        return 0
    fixture = candidates[(seq - 1) % len(candidates)]
    state["snapshot_seq"] = seq
    sys.stdout.write(fixture.read_text(encoding="utf-8"))
    return 0


def _cmd_click(args: list[str], fixture_dir: Path, state: dict) -> int:
    return 0


def _cmd_select(args: list[str], fixture_dir: Path, state: dict) -> int:
    return 0


def _cmd_dialog(args: list[str], fixture_dir: Path, state: dict) -> int:
    # `dialog accept` etc. — noop in fake.
    return 0


def _cmd_screenshot(args: list[str], fixture_dir: Path, state: dict) -> int:
    if not args:
        return 2
    out_path = Path(args[0])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Per-basename override, else single canned PNG.
    override = fixture_dir / "screenshot" / out_path.name
    fallback = fixture_dir / "screenshot.png"
    src = override if override.exists() else fallback
    if not src.exists():
        sys.stderr.write(
            f"fake_agent_browser: no screenshot fixture at {src}\n"
        )
        return 1
    shutil.copyfile(src, out_path)
    return 0


def _cmd_close(args: list[str], fixture_dir: Path, state: dict) -> int:
    state["current_url"] = ""
    state["snapshot_seq"] = 0
    return 0


def _cmd_fill(args: list[str], fixture_dir: Path, state: dict) -> int:
    # `fill @eN "value"` — noop.
    return 0


def _cmd_session(args: list[str], fixture_dir: Path, state: dict) -> int:
    # `session list` etc. — return nothing useful but exit 0.
    return 0


COMMANDS = {
    "open": _cmd_open,
    "navigate": _cmd_open,
    "goto": _cmd_open,
    "wait": _cmd_wait,
    "get": _cmd_get,
    "eval": _cmd_eval,
    "snapshot": _cmd_snapshot,
    "click": _cmd_click,
    "select": _cmd_select,
    "dialog": _cmd_dialog,
    "screenshot": _cmd_screenshot,
    "close": _cmd_close,
    "fill": _cmd_fill,
    "session": _cmd_session,
}


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    if not raw:
        return 2
    if raw[0] in {"--version", "-V"}:
        print("fake-agent-browser/0.1 (no real browser)")
        return 0
    fixture_dir = _fixture_dir()
    args, session = _split_session(raw)
    if not args:
        return 2
    cmd, rest = args[0], args[1:]
    # Drop terminal flags we don't care about (e.g. `-i`, `--headed`).
    rest = [a for a in rest if not a.startswith("-")]

    _trace(fixture_dir, [cmd, *rest, "--session", session])

    state_path = _session_state_path(fixture_dir, session)
    state = _load_state(state_path)

    handler = COMMANDS.get(cmd)
    if handler is None:
        sys.stderr.write(f"fake_agent_browser: unsupported subcommand: {cmd}\n")
        return 2
    rc = handler(rest, fixture_dir, state)
    _save_state(state_path, state)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

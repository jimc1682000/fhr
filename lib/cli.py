"""Top-level CLI dispatcher.

Subcommand-oriented: `fhr {analyze, export, import}`. Backward
compatible — if the first positional argument doesn't match a known
subcommand and looks like a file path, we prepend `analyze` so the
historical `python attendance_analyzer.py <file>` invocation still
works without changes.

Subcommand handlers live in `lib/commands/`. Each module exposes
`add_parser(subparsers)` and `run(args)`.
"""
from __future__ import annotations

import argparse
import sys

KNOWN_SUBCOMMANDS = {
    "analyze", "export", "import",
    "portal-fetch", "portal_fetch",
    "portal-sync", "portal_sync",
}


def _looks_like_legacy_invocation(argv: list[str]) -> bool:
    """True when the first arg isn't a subcommand and isn't a flag.

    Heuristic: historical `python attendance_analyzer.py
    202508-員工-出勤資料.txt [csv]` callers passed a file path as the
    first positional. Anything starting with `-` is a flag and should
    fall through to argparse so `--help` etc. work at the top level.
    """
    return bool(argv) and argv[0] not in KNOWN_SUBCOMMANDS and not argv[0].startswith("-")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fhr",
        description="考勤分析系統 - 支援增量分析、Portal 介接、外部工具互通",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True, metavar="SUBCOMMAND")

    # Lazy import each handler — keeps top-level help fast and lets
    # individual commands skip importing heavy deps until selected.
    from lib.commands import (
        analyze as analyze_cmd,
        export as export_cmd,
        import_ as import_cmd,
        portal_fetch as portal_fetch_cmd,
        portal_sync as portal_sync_cmd,
    )

    analyze_cmd.add_parser(sub)
    export_cmd.add_parser(sub)
    import_cmd.add_parser(sub)
    portal_fetch_cmd.add_parser(sub)
    portal_sync_cmd.add_parser(sub)
    return parser


def run(argv: list | None = None) -> None:
    raw = sys.argv[1:] if argv is None else argv[1:]
    if _looks_like_legacy_invocation(raw):
        raw = ["analyze", *raw]

    parser = build_parser()
    args = parser.parse_args(raw)

    if args.cmd == "analyze":
        from lib.commands import analyze as analyze_cmd
        analyze_cmd.run(args)
    elif args.cmd == "export":
        from lib.commands import export as export_cmd
        export_cmd.run(args)
    elif args.cmd == "import":
        from lib.commands import import_ as import_cmd
        import_cmd.run(args)
    elif args.cmd in ("portal-fetch", "portal_fetch"):
        from lib.commands import portal_fetch as portal_fetch_cmd
        portal_fetch_cmd.run(args)
    elif args.cmd in ("portal-sync", "portal_sync"):
        from lib.commands import portal_sync as portal_sync_cmd
        portal_sync_cmd.run(args)
    else:
        parser.error(f"unknown subcommand: {args.cmd}")

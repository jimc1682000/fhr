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
    "analyze",
    "export",
    "import",
    "portal-fetch",
    "portal_fetch",
    "portal-sync",
    "portal_sync",
    "portal-check",
    "portal_check",
    "portal-balances",
    "portal_balances",
    "portal-apply",
    "portal_apply",
    "reasons",
}


_TOP_LEVEL_HELP_FLAGS = {"-h", "--help"}


def _looks_like_legacy_invocation(argv: list[str]) -> bool:
    """True when no token in argv names a known subcommand.

    Historical callers passed flags + a file path in any order:
        python attendance_analyzer.py 202508-員工-出勤資料.txt
        python attendance_analyzer.py 202508-員工-出勤資料.txt csv
        python attendance_analyzer.py --full sample.txt
        python attendance_analyzer.py --debug --reset-state sample.txt csv
    The only way to identify a "new" invocation is the presence of a
    subcommand keyword somewhere on the line; we let `-h`/`--help`
    fall through to the top-level parser so users can see all
    subcommands.
    """
    if not argv:
        return False
    if any(a in _TOP_LEVEL_HELP_FLAGS for a in argv):
        return False
    return not any(a in KNOWN_SUBCOMMANDS for a in argv)


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
        portal_apply as portal_apply_cmd,
        portal_balances as portal_balances_cmd,
        portal_check as portal_check_cmd,
        portal_fetch as portal_fetch_cmd,
        portal_sync as portal_sync_cmd,
        reasons as reasons_cmd,
    )

    analyze_cmd.add_parser(sub)
    export_cmd.add_parser(sub)
    import_cmd.add_parser(sub)
    portal_fetch_cmd.add_parser(sub)
    portal_sync_cmd.add_parser(sub)
    portal_check_cmd.add_parser(sub)
    portal_balances_cmd.add_parser(sub)
    portal_apply_cmd.add_parser(sub)
    reasons_cmd.add_parser(sub)
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
    elif args.cmd in ("portal-check", "portal_check"):
        from lib.commands import portal_check as portal_check_cmd

        portal_check_cmd.run(args)
    elif args.cmd in ("portal-balances", "portal_balances"):
        from lib.commands import portal_balances as portal_balances_cmd

        portal_balances_cmd.run(args)
    elif args.cmd in ("portal-apply", "portal_apply"):
        from lib.commands import portal_apply as portal_apply_cmd

        portal_apply_cmd.run(args)
    elif args.cmd == "reasons":
        from lib.commands import reasons as reasons_cmd

        reasons_cmd.run(args)
    else:
        parser.error(f"unknown subcommand: {args.cmd}")

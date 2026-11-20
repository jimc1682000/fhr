#!/usr/bin/env python3
import sys
import unittest
from trace import Trace


def main() -> int:
    tr = Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    # unittest.main() reports its result by raising SystemExit. Keep that code
    # so a failing suite fails CI instead of passing as "coverage written".
    exit_code = 0
    try:
        tr.runfunc(lambda: unittest.main(module=None, argv=["", "-q"]))
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    tr.results().write_results(show_missing=True, summary=True, coverdir="coverage_report")
    print("Coverage report written to coverage_report/.")
    if exit_code:
        print(f"Tests failed (unittest exit code {exit_code}).", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
import sys
import unittest
from trace import Trace

def main() -> None:
    tr=Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
    try:
        tr.runfunc(lambda: unittest.main(module=None, argv=['', '-q']))
    except SystemExit:
        pass
    tr.results().write_results(show_missing=True, summary=True, coverdir='coverage_report')
    print('Coverage report written to coverage_report/.')

if __name__ == '__main__':
    main()


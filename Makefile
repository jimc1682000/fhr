PY := python3

.PHONY: test coverage

test:
	$(PY) -m unittest -q

# Generate coverage report using stdlib trace (no external deps)
coverage:
	$(PY) - << 'PY'
from trace import Trace
import sys, unittest
tr=Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
try:
    tr.runfunc(lambda: unittest.main(module=None, argv=['', '-q']))
except SystemExit:
    pass
tr.results().write_results(show_missing=True, summary=True, coverdir='coverage_report')
print('Coverage report written to coverage_report/.')
PY


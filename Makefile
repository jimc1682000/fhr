PY := python3

.PHONY: test coverage

test:
	$(PY) -m unittest -q

# Generate coverage report using stdlib trace (no external deps)
coverage:
	$(PY) tools/run_coverage.py
	$(PY) tools/gen_coverage_badge.py

.PHONY: coverage-check
coverage-check: coverage
	$(PY) tools/check_coverage_threshold.py --min 100

PY := python3

.PHONY: test coverage

test:
	$(PY) -m unittest -q

# Generate coverage report using stdlib trace (no external deps)
coverage:
	$(PY) tools/run_coverage.py
	$(PY) tools/gen_coverage_badge.py

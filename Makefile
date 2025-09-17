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
	$(PY) tools/check_coverage_threshold.py --min 90

.PHONY: lint
lint:
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check . ; \
	else \
		$(PY) tools/lint.py ; \
	fi

.PHONY: install-hooks
install-hooks:
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit install && echo "✅ Pre-commit hooks installed successfully!" ; \
	else \
		echo "❌ Error: pre-commit not found. Install with: pip install pre-commit" ; \
		exit 1 ; \
	fi

.PHONY: pre-commit-run
pre-commit-run:
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit run --all-files ; \
	else \
		echo "❌ Error: pre-commit not found. Install with: pip install pre-commit" ; \
		exit 1 ; \
	fi

.PHONY: pre-commit-update
pre-commit-update:
	@if command -v pre-commit >/dev/null 2>&1; then \
		pre-commit autoupdate && echo "✅ Pre-commit hooks updated!" ; \
	else \
		echo "❌ Error: pre-commit not found. Install with: pip install pre-commit" ; \
		exit 1 ; \
	fi

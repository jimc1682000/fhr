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

.PHONY: lint
lint:
	@if command -v ruff >/dev/null 2>&1; then \
		ruff check . ; \
	else \
		$(PY) tools/lint.py ; \
	fi

.PHONY: install-hooks
install-hooks:
	@mkdir -p .git/hooks
	cp -f hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "Installed git pre-commit hook. Use SKIP_TESTS=1 to skip tests."

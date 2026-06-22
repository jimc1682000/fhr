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
	$(PY) tools/check_coverage_threshold.py

.PHONY: lint
# 用 `$(PY) -m ruff`（= requirements-dev 釘的 ruff==0.15.18），而非 PATH 上
# 可能不同版本的 ruff，確保格式判定與 CI / pre-commit 一致。
lint:
	@if $(PY) -m ruff --version >/dev/null 2>&1; then \
		$(PY) -m ruff check . && $(PY) -m ruff format --check . ; \
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

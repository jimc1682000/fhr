# 0012. 格式化改用 ruff format，並一律以 `python -m ruff` 呼叫

- Status: Accepted
- Date: 2026-06-22

## Context

專案同時用 black 格式化、ruff lint，兩套工具設定重疊。另外，PATH 上的 `ruff` 可能是系統或 Homebrew 安裝的其他版本，與 `requirements-dev.txt` 釘住的版本不同；不同版本的 `ruff format` 輸出可能不同，造成本機格式化後與 CI 的 `ruff format --check` 對不上，產生格式 churn。

## Decision

- 移除 black，pre-commit、CI、Taskfile 與 `pyproject.toml` 統一改用 `ruff format`（行長度 100），並對整個 repo 套用一次。
- Makefile、Taskfile 與 CI 一律以 `python -m ruff` 呼叫，確保用的是 venv 內、由 `requirements-dev.txt` 釘住的版本，而不是 PATH 上飄動的版本。

## Consequences

- 本機、pre-commit 與 CI 三方的格式判定一致。
- 升級 ruff 須改 `requirements-dev.txt` 的版本並重新格式化整個 repo，作為單獨的提交。
- 直接在 shell 打 `ruff` 仍可能用到別的版本；文件與指令範例一律寫 `python -m ruff` 或 `make lint`。

來源：PR #41、#42

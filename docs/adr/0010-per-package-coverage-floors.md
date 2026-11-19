# 0010. 覆蓋率改為各套件下限，並在 pre-commit 跑完整測試

- Status: Accepted
- Date: 2026-06-03

## Context

Portal 自動化（0009）新增大量要呼叫 `agent-browser` 子程序的協調程式，這些 `run()` 路徑主要由整合測試覆蓋，單元測試難以達到 100%。若維持 0003 的全面 100% 門檻，就只能為了數字寫脆弱的 mock 測試。

## Decision

- 覆蓋率門檻改為 `tools/coverage_baseline.json` 定義的各套件下限：整體下限 `overall_min` 80%，各套件（`attendance_analyzer`、`lib.core`、`lib.io`、`lib.portal`、`lib.commands`）各有 floor，容許低於 floor 的幅度 `tolerance_pct` 為 1%。
- `lib.commands` 的 floor 刻意最低，因為其協調流程以整合測試為主。
- 鼓勵透過 PR 調高 floor。
- 量測工具沿用 0003 的 stdlib trace，CI 以 `tools/check_coverage_threshold.py` 檢查。
- pre-commit 新增完整 `unittest` hook，在提交前抓出重構漂移；可用 `SKIP_TESTS=1` 跳過。
- 離線 E2E 以 `tools/fake_agent_browser.py` 重播 fixture，另有截圖比對工具 `tools/diff_screenshots.py`（Pillow 只用於開發工具）。

## Consequences

- 門檻不再是單一數字，新增套件時須同步更新 baseline 檔。
- 文件中若仍寫著固定百分比（例如 90%），以 `tools/coverage_baseline.json` 為準。
- pre-commit 跑完整測試會讓提交變慢，而且測試會在提交時的 Git 環境下執行，這點引出了 0016 的隔離需求。

來源：PR #38

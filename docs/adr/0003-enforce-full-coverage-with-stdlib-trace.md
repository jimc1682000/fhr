# 0003. 以 stdlib trace 量測覆蓋率並強制 100%

- Status: Superseded by 0010
- Date: 2025-09-13

## Context

模組化（0002）後測試數量快速增加，需要一個 CI 可執行的覆蓋率門檻，防止新程式碼沒有測試就進 main。專案當時希望不增加任何外部相依。

## Decision

- 以 Python 標準函式庫的 `trace` 量測覆蓋率：`tools/run_coverage.py` 產生 `coverage_report/`，`tools/gen_coverage_badge.py` 產生本地 `assets/coverage.svg` badge。
- `tools/check_coverage_threshold.py` 在 CI 強制整體與各檔案皆為 100%。
- 提供 `make coverage`、`make coverage-check` 供本機重現。
- 同時整併測試共用 helper（`DummyResp`、`temp_env`、`urlopen_sequence`），並移除無法到達的分支。

## Consequences

- 覆蓋率工具零外部相依，CI 與本機結果一致。
- 100% 門檻在純分析器階段可行；引入要驅動瀏覽器子程序的 Portal 自動化後，`run()` 類協調流程難以單元測試覆蓋，門檻改為各套件下限，見 0010。

來源：PR #27、#28

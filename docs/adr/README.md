# Architecture Decision Records

格式與撰寫規則見 [0000](0000-record-architecture-decisions.md)。

| 編號 | 標題 | 狀態 |
|---|---|---|
| [0000](0000-record-architecture-decisions.md) | 以 ADR 記錄架構決策 | Accepted |
| [0001](0001-holiday-api-retry-and-fallback.md) | 假日資料載入採重試退避並退回基本假日 | Accepted |
| [0002](0002-modularize-core-into-lib.md) | 核心邏輯拆分到 `lib/`，假日來源抽象為 provider | Accepted |
| [0003](0003-enforce-full-coverage-with-stdlib-trace.md) | 以 stdlib trace 量測覆蓋率並強制 100% | Superseded by 0010 |
| [0004](0004-debug-mode-is-read-only.md) | Debug 模式一律唯讀，不寫入狀態檔 | Accepted |
| [0005](0005-wfh-for-every-friday.md) | 所有非國定假日的週五一律建議 WFH | Accepted |
| [0006](0006-export-merge-policy-and-confirmed-cleanup.md) | 匯出預設覆寫單一檔案，清理須先預覽再確認 | Accepted |
| [0007](0007-late-arrival-always-leave-forget-punch-manual.md) | 遲到一律建議請假，忘刷卡保留給使用者手動使用 | Accepted |
| [0008](0008-holiday-source-taiwan-calendar-via-jsdelivr.md) | 假日資料改抓社群維護的 TaiwanCalendar（經 jsDelivr） | Accepted |
| [0009](0009-portal-automation-via-headed-browser.md) | 以 headed 瀏覽器自動化 Portal，分析與送單以版本化 JSON 銜接 | Accepted |
| [0010](0010-per-package-coverage-floors.md) | 覆蓋率改為各套件下限，並在 pre-commit 跑完整測試 | Accepted |
| [0011](0011-leave-type-cascade-allocation.md) | 請假假別依餘額串接分配，整筆不拆單 | Accepted |
| [0012](0012-ruff-format-via-python-m.md) | 格式化改用 ruff format，並一律以 `python -m ruff` 呼叫 | Accepted |
| [0013](0013-portal-check-pre-flight.md) | 送單前先以 `portal-check` 檢查駁回與簽核中的單據 | Accepted |
| [0014](0014-pip-package-and-container-without-portal.md) | 以 pip 套件與多架構容器發佈，Portal 自動化不進 image | Accepted |
| [0015](0015-shared-repo-policy-automerge.md) | PR 合併自動化採共用 `repo-policy` reusable workflow | Accepted |
| [0016](0016-isolate-git-env-in-tests.md) | 測試建立 Git fixture 時清除所有 `GIT_*` 環境變數 | Accepted |
| [0017](0017-reconcile-submissions-against-portal-list.md) | 送單結果以 Portal 清單對帳為準 | Accepted |

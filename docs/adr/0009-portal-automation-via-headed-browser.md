# 0009. 以 headed 瀏覽器自動化 Portal，分析與送單以版本化 JSON 銜接

- Status: Accepted
- Date: 2026-06-03

## Context

工具原本只能「吃匯出的出勤 TXT、產報表」，抓出勤資料與送加班／請假單都靠手動操作 104 EHR Portal。Portal 沒有公開 API，登入與內網環境都綁在使用者桌面上。

## Decision

- `fhr` CLI 改為多子命令：`analyze`（既有）、`export`、`import`、`portal-fetch`、`portal-sync`、`portal-balances`、`portal-apply`、`reasons`。不帶子命令的舊用法仍可執行。
- Portal 操作透過外部工具 `agent-browser` 驅動 headed 瀏覽器，相關程式集中在 `lib/portal/`。`agent-browser` 是選配相依，純 TXT 分析流程不需要它。
- 分析結果與送單之間以版本化 JSON 銜接：`attendance-analysis/v1` 與 `portal-attendance-snapshot/v1`，規格放在 `docs/schema/`，`lib/schema.py` 處理版本解析。新增欄位屬 minor 變更，破壞相容才升 major。
- 狀態檔新增 `applied_forms`，由 `portal-sync` 從 Portal 鏡射已送出的單據，`portal-apply` 據此去重，取代手動維護的截止日期。
- `export` 預設改為完整分析，`--incremental` 才啟用增量，避免增量模式默默漏掉條目。
- `portal-apply` 支援 `--dry-run` 與截圖，供人工確認後再真正送出。
- 加班理由由 `fhr reasons` 收集 git 證據，再由 agent skill 抽象成給 HR 看的文字；分析器本身不呼叫任何 LLM API。

## Consequences

- Portal 自動化只能在有桌面瀏覽器與內網的機器上跑，無法進容器（見 0014）。
- Portal 頁面結構改變時 scraper 會壞；以 `tools/fake_agent_browser.py` 搭配錄製的 fixture 做離線 E2E 重播，降低回歸風險。
- 頁面上的「送出成功」並不可靠，後續改以 Portal 清單對帳（見 0017）。

來源：PR #38

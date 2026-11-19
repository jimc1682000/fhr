# 0006. 匯出預設覆寫單一檔案，清理須先預覽再確認

- Status: Accepted
- Date: 2025-10-03

## Context

早期每次匯出前都會把舊檔備份成 `_analysis_YYYYMMDD_HHMMSS.*`，重跑幾次後工作目錄就堆滿時間戳備份。CLI 與 Web 服務對輸出檔的處理也不一致。

## Decision

- 新增 `--export-policy {merge,archive}`，預設 `merge`：直接改寫 `<original>_analysis.(csv|xlsx)`，只保留一份正式輸出。
- `archive` 保留舊行為，寫入前先建立時間戳備份。
- 新增 `--cleanup-exports`：先列出候選檔案並詢問，確認後預設只刪時間戳備份；搭配 `--debug` 時連同本次產生的主檔一起刪除。
- 清理邏輯集中在 `lib/export_cleanup.py`（`list_backups()`、`cleanup_exports()`），CLI 與 Web 服務共用。
- Web 流程刪檔採兩段式：前端先呼叫 `POST /api/exports/cleanup-preview` 取得 `token` 與 `snapshot`，再於 `/api/analyze` 帶回 `cleanup_token`、`cleanup_snapshot`，伺服器核對一致才刪除。

## Consequences

- 預設行為不再保留歷史版本，需要比較前後結果時須明確指定 `archive`。
- 任何刪檔都必須經過列出與確認，預覽與實際刪除之間檔案若有變動，token／snapshot 核對會擋下，避免誤刪或競態。

來源：PR #34

# 環境變數與假日載入（Holiday Resilience）

系統會自動載入國定假日：2025 年走硬編碼，其餘年份先嘗試政府開放資料，失敗回退到基本固定假日（元旦、國慶）。

## 環境變數
- `HOLIDAY_API_MAX_RETRIES`：最大重試次數（預設 3）
- `HOLIDAY_API_BACKOFF_BASE`：指數退避基準秒數（預設 0.5）
- `HOLIDAY_API_MAX_BACKOFF`：每次重試的最大等待秒數上限（預設 8）

測試建議將上述值設為 0，以加快測試並避免 flakiness；網路呼叫請使用 mock（`urllib.request.urlopen`）。


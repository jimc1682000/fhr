# 0001. 假日資料載入採重試退避並退回基本假日

- Status: Accepted
- Date: 2025-09-13

## Context

分析器需要國定假日判斷週五 WFH 與整日缺勤是否成立。2025 年假日寫死在程式內，其他年份要從網路動態載入。最初的實作只呼叫一次，逾時或伺服器暫時故障就直接失去當年假日資料，導致國定假日被誤判成需要請假或 WFH 的工作日。

## Decision

- 動態載入改為「指數退避 + jitter」重試：逾時、HTTP 429 與 5xx 重試；403 等不可重試的 4xx 立即失敗，不浪費重試次數。
- 重試參數可由環境變數覆寫：`HOLIDAY_API_MAX_RETRIES`（預設 3）、`HOLIDAY_API_BACKOFF_BASE`（預設 0.5）、`HOLIDAY_API_MAX_BACKOFF`（預設 8）。
- 全部失敗時退回 `BasicFixedProvider`，只載入元旦與國慶日，並記 warning，分析仍可完成。
- 只接受 `http`／`https` URL scheme，並使用預設的安全 SSL context；回應中格式錯誤的日期逐筆略過，整份無有效紀錄時視為失敗並觸發退回。

## Consequences

- 網路不穩時分析不會中斷，但退回基本假日後，其他國定假日可能被當成工作日；使用者須注意 log 裡的 warning。
- 測試一律 mock `urllib.request.urlopen`，不打真實網路，並把退避參數設為 0 以維持快速且結果固定。
- 403 不重試的規則在 0008 時發揮作用：舊資料來源下線並擋下預設 User-Agent，log 顯示的正是「HTTP 403 — 不重試」。

來源：PR #14、#15、#16、#17、#25

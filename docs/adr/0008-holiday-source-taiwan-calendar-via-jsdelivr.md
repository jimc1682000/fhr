# 0008. 假日資料改抓社群維護的 TaiwanCalendar（經 jsDelivr）

- Status: Accepted
- Date: 2026-06-03

## Context

原本的政府開放資料假日 API 已下線，任何 client 都回 HTTP 404；Python `urllib` 的預設 User-Agent 甚至更早就被擋成 HTTP 403。結果是非 2025 年份只剩基本假日，勞動節、補假等日子被當成一般工作日或週五，產生錯誤的 WFH 建議。官方 dataset 雖然仍有新年度 CSV，但每年檔名帶隨機 UUID，無法由年份推導 URL，必須爬 dataset 頁面，維護成本太高。

## Decision

- 假日來源改為社群維護的 `ruyut/TaiwanCalendar`，經 jsDelivr CDN 取得：`https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/{year}.json`。
- 回應格式改為 `[{date, week, isHoliday, description}]` 的 list，provider 與測試 helper（`DummyResp`、`urlopen_sequence`）同步支援 list payload。
- 請求一律帶明確的 User-Agent，避免再被某個 host 以 UA 擋下。
- 重試、退避與退回基本假日的機制沿用 0001。

## Consequences

- URL 由年份直接推得，CDN 可用性高；代價是仰仗第三方社群維護的資料，資料若延遲更新，新年度會退回基本假日。
- 類別名稱仍是 `TaiwanGovOpenDataProvider`，實際上已不是政府 API；改名屬可選重構，閱讀程式碼時須留意。
- 2025 年仍使用 `Hardcoded2025Provider`，不走網路。

來源：PR #37

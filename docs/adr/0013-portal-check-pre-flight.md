# 0013. 送單前先以 `portal-check` 檢查駁回與簽核中的單據

- Status: Accepted
- Date: 2026-07-26

## Context

送下一波加班／請假單之前沒有固定的檢查，容易重送已被駁回的單，或在舊單還在簽核時疊上新單。此外，`portal-sync` 原本沒有抓到每筆單據的簽核狀態，狀態欄一律空白。

## Decision

- 新增 `fhr portal-check`，固定作為 `portal-apply` 送單流程的第 0 步。
- 列出需要處理的單據：已駁回（評估是否重送）、流程停止（抽單，評估是否需補單）、未處理（仍在簽核，避免疊單）。已核准等終結狀態不列出。
- `--since YYYY/MM` 可限縮假勤日範圍。
- 唯讀：不對 Portal 寫入，也不改狀態檔。
- 以 exit code 表達結果，方便腳本串接（例如 `fhr portal-check --since 2026/01 && fhr portal-apply …`）：
  - `0`：乾淨
  - `1`：有需處理的單據
  - `5`：取不到 apply lock
  - `6`：查詢失敗
- scraper 改從查詢結果列的「狀態」欄擷取簽核狀態，`portal-sync` 也一併寫入每筆快取。

## Consequences

- 送單流程多一步，但重送與疊單的情況會在送出前被攔下。
- 查詢失敗時以 6 結束，不會被誤讀成「沒有待處理單據」。
- 狀態分類依實際 Portal 下拉選單與狀態欄文字建立，Portal 改版時須重新驗證。

來源：PR #43、#49

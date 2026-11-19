# 0004. Debug 模式一律唯讀，不寫入狀態檔

- Status: Accepted
- Date: 2025-10-01

## Context

增量分析靠 `attendance_state.json` 記錄已處理的日期範圍。排查問題時重跑分析，會把測試用的執行寫進狀態檔，讓下一次正式增量分析跳過不該跳過的日期。需要一個「可以放心重跑」的模式。

## Decision

- 新增 `--debug` CLI 旗標與 `FHR_DEBUG` 環境變數，兩者都啟用 debug 模式。
- Debug 模式同時做兩件事：log 等級調到 DEBUG，以及 `AttendanceStateManager` 以唯讀模式載入、略過所有狀態寫入。
- Web 服務支援全域（`FHR_DEBUG=true`）與單次請求層級（`POST /api/analyze` 的 `debug=true`）兩種切換，前端有對應核取方塊。

## Consequences

- 詳細 log 與「不改狀態」綁在一起，不能只開其中一個；需要詳細 log 又要寫入狀態時，只能另外調整 logger。
- Debug 模式仍會產生匯出檔；搭配 `--cleanup-exports` 時會連同本次產生的主檔一起刪除（見 0006）。
- 測試須涵蓋「debug 模式下增量分析不寫狀態」這條保護。

來源：PR #32

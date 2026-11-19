# 0002. 核心邏輯拆分到 `lib/`，假日來源抽象為 provider

- Status: Accepted
- Date: 2025-09-13

## Context

早期所有邏輯都塞在 `attendance_analyzer.py`：解析、分組、規則計算、狀態管理、假日載入與 CSV／Excel 匯出混在同一個類別，難以單獨測試，也難以替換假日資料來源。

## Decision

- 把純邏輯與 I/O 拆成 `lib/` 底下的小模組：`parser`、`grouping`、`dates`、`policy`（`Rules` dataclass 與遲到／加班計算）、`state`（`AttendanceStateManager`）、`filename`、`backup`、`report`、`csv_exporter`、`excel_exporter`、`cli`。
- 假日載入改為 `HolidayProvider` 介面：`Hardcoded2025Provider`、`BasicFixedProvider`、`TaiwanGovOpenDataProvider`，由 service 依年份協調。
- `attendance_analyzer.py` 保留為對外入口與協調者，`main()` 委派給 `lib.cli.run()`；CLI 旗標與輸出格式不變。
- 公司規則集中在 `lib/config.py` 的 `AttendanceConfig` dataclass，執行時可由工作目錄下的 `config.json` 覆寫。

## Consequences

- `attendance_analyzer.py` 仍是核心模組：`lib.*`／`server.*` 反向 import 其中的 `Issue`、`IssueType`、`AttendanceAnalyzer` 與 `logger`，打包時不可遺漏（見 0014）。
- 為了不破壞既有測試，部分舊方法以 shim 形式留在分析器內並委派給新模組。
- `config.json` 覆寫只套用與 `AttendanceConfig` 屬性同名（小寫）的鍵。repo 內附的 `config.json` 仍是早期的大寫鍵（如 `LATEST_CHECKIN`），因此實際上不會覆寫任何值，現行規則以 dataclass 預設值為準（見 0007）。
- 更換假日來源只需新增或修改 provider，不必動分析流程（見 0008）。

來源：PR #1、#14、#15、#26、#27

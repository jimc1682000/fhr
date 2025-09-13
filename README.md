# 考勤分析系統

[![Coverage](assets/coverage.svg)](docs/testing.md)

> Python attendance analyzer with Taiwan holiday support, calculating late arrivals, overtime, and WFH recommendations

這是一個企業考勤分析工具，可以自動分析考勤記錄並計算需要申請的遲到/加班時數。

## 功能特色

- 🕒 自動計算遲到時數
- ⏰ 自動計算加班時數（符合1小時以上規定）
- 🏠 自動識別週五WFH假建議
- 📊 生成詳細分析報告
- 📈 匯出Excel/CSV格式統計資料
- 🔄 智慧忘刷卡建議（每月2次額度）
- 🗓️ 支援跨年份出勤分析（自動載入國定假日）
- **🚀 NEW: 增量分析功能 - 避免重複處理已分析資料**
- **📁 NEW: 支援跨月檔案格式 (`202508-202509-姓名-出勤資料.txt`)**
- **💾 NEW: 智慧狀態管理 - 自動記住處理進度**
- **📋 NEW: 增強輸出格式 - 標示新發現與已存在問題**

## Quick Start

```bash
# 1) 最常用：增量分析 + 預設Excel
python attendance_analyzer.py "202508-姓名-出勤資料.txt"

# 2) 產生CSV
python attendance_analyzer.py "202508-姓名-出勤資料.txt" csv

# 3) 跨月資料
python attendance_analyzer.py "202508-202509-姓名-出勤資料.txt"
```

提示：如需 Excel 匯出，建議安裝 `openpyxl`：`pip install openpyxl`。

### 系統需求

- Python 3.8+
- 標準庫（無強制第三方依賴）
- Excel 匯出（可選）：`openpyxl`

### TUI 預告與版本需求

- 即將導入 Textual TUI（逐步精靈）。
- TUI 僅支援 Python 3.8+。
- 初版將以 `--tui` 旗標啟動；缺少依賴時提供安裝指引（`textual`）。

### 常見錯誤提示

- 看不到 Excel 輸出 → 未安裝 `openpyxl`，請先安裝或改用 `csv` 格式。
- 未啟用增量分析 → 檔名需為 `YYYYMM-姓名-出勤資料.txt` 或 `YYYYMM-YYYYMM-姓名-出勤資料.txt`。
- 解析失敗或欄位錯亂 → 原始檔需為「tab 分隔」的文字檔（.txt），不是逗號或空白分隔。
- 沒有任何輸出變化 → 可能無新資料；若要重跑全部，加入 `--full` 或 `--reset-state`。

## 延伸閱讀（docs/）

- 概覽與規則：[docs/overview.md](docs/overview.md)
- 安裝與使用：[docs/usage.md](docs/usage.md)
- 增量分析詳解：[docs/incremental.md](docs/incremental.md)
- 檔案格式需求：[docs/data-format.md](docs/data-format.md)
- 計算邏輯：[docs/logic.md](docs/logic.md)
- 輸出（Excel/CSV/備份 + 範例）：[docs/output.md](docs/output.md)
- 系統架構（Before/After + 元件與流程）：[docs/architecture.md](docs/architecture.md)
- 假日載入與環境變數：[docs/environment.md](docs/environment.md)
- 專案結構：[docs/project-structure.md](docs/project-structure.md)
- 技術需求：[docs/requirements.md](docs/requirements.md)
- 測試與品質保證：[docs/testing.md](docs/testing.md)
- 貢獻指南（PR/Commit）：[docs/contributing.md](docs/contributing.md)
- 疑難排解：[docs/troubleshooting.md](docs/troubleshooting.md)
 - Coverage 指令（無需安裝 coverage）：`make coverage`（輸出於 `coverage_report/`）

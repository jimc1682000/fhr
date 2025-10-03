# 使用（Usage）

## CLI 快速開始

```bash
# 1) 最常用：增量分析 + 預設 Excel
python attendance_analyzer.py "202508-姓名-出勤資料.txt"

# 2) 產生 CSV
python attendance_analyzer.py "202508-姓名-出勤資料.txt" csv

# 3) 跨月資料
python attendance_analyzer.py "202508-202509-姓名-出勤資料.txt"
```

### 基本命令格式

```bash
python attendance_analyzer.py <考勤檔案路徑> [格式] [選項]
```

- 格式：`excel`（預設）或 `csv`
- 選項：
  - `--incremental` / `-i`：增量分析（預設）
  - `--full` / `-f`：完整重新分析
  - `--reset-state` / `-r`：清除使用者狀態
  - `--debug`：啟用除錯模式（詳細日誌、停用狀態寫入）

### 常見情境範例

```bash
# 增量分析（單月或跨月）
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt"
python attendance_analyzer.py "202508-202509-員工姓名-出勤資料.txt"

# 完整分析 / 重建狀態
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --full
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --reset-state

# 範例檔案 + 除錯模式
python attendance_analyzer.py sample-attendance-data.txt
python attendance_analyzer.py sample-attendance-data.txt csv
python attendance_analyzer.py sample-attendance-data.txt --debug
```

## Textual TUI 操作

```bash
# 預設深色主題
python -m tui

# 指定淺色主題或 textual-web 模式
python -m tui --light
python -m tui --webview
```

- 介面提供表單欄位、增量/完整切換、匯出策略、狀態檔清理、近期檔案清單與進度日誌。
- `Ctrl+D` 切換深/淺色、`Ctrl+L` 切換繁中/英文提示、`Ctrl+C` 送出取消請求、`F5` 重送上一筆表單資料。

### textual-web 模式

| 項目 | 說明 |
|------|------|
| 使用方式 | `python -m tui --webview`（需安裝 `textual-web`） |
| 適用情境 | 遠端教學、展示，或無法直接使用終端時 |
| 安全建議 | 綁定在內部網路、SSH 轉發或 HTTPS 代理後再分享網址 |
| 限制 | 目前僅供內部工具使用，未提供公開登入保護；不建議直接暴露於互聯網 |

如需錄製或截圖，請參考 [`docs/tui_capture_setup.md`](tui_capture_setup.md) 取得建議的螢幕寬度、指令與檔案命名規則。


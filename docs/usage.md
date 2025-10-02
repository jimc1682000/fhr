# 使用（Usage）

## Quickstart
```bash
# 1) 最常用：增量分析 + 預設Excel
python attendance_analyzer.py "202508-姓名-出勤資料.txt"

# 2) 產生CSV
python attendance_analyzer.py "202508-姓名-出勤資料.txt" csv

# 3) 跨月資料
python attendance_analyzer.py "202508-202509-姓名-出勤資料.txt"
```

## 基本使用
```bash
python attendance_analyzer.py <考勤檔案路徑> [格式] [選項]
```
- 格式：`excel`（預設）或 `csv`
- 選項：
  - `--incremental` / `-i`：增量分析（預設）
  - `--full` / `-f`：完整重新分析
  - `--reset-state` / `-r`：清除使用者狀態
  - `--debug`：啟用除錯模式（詳細日誌、停用狀態寫入）
  - `--export-policy {merge,archive}`：匯出策略；預設 `merge` 覆寫主檔案，可改用 `archive` 保留 timestamp 備份
  - `--cleanup-exports`：清除匯出檔案前會列出候選並詢問確認；預設只刪 timestamp 備份，搭配 `--debug` 時亦會刪除當次輸出

## 範例
- 增量分析：
```bash
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt"
python attendance_analyzer.py "202508-202509-員工姓名-出勤資料.txt"
```
- 完整分析：
```bash
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --full
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --reset-state
```
- 範例檔案：
```bash
python attendance_analyzer.py "sample-attendance-data.txt"
python attendance_analyzer.py "sample-attendance-data.txt" csv
python attendance_analyzer.py "sample-attendance-data.txt" --debug
python attendance_analyzer.py "sample-attendance-data.txt" --export-policy archive
python attendance_analyzer.py "sample-attendance-data.txt" --debug --cleanup-exports
```

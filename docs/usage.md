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
```


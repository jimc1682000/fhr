# 專案結構

```
fhr/
├── attendance_analyzer.py          # 主要分析程式（增量分析）
├── test/                           # 測試目錄
│   └── test_attendance_analyzer.py # 單元測試（含跨年份）
├── lib/                            # 共用模組
│   ├── __init__.py
│   └── excel_exporter.py           # Excel 匯出共用函式庫
├── sample-attendance-data.txt      # 範例出勤資料
├── sample-attendance-data_analysis.csv # 範例分析結果（含狀態欄位）
├── CLAUDE.md                       # AI 代理知識庫（技術文件）
├── README.md                       # 使用者說明文件（精簡版）
├── .gitignore                      # 版本控制排除規則（保護隱私）
└── [執行時產生的檔案]
    ├── attendance_state.json       # 增量分析狀態檔案（不提交）
    ├── *_analysis.csv              # CSV 分析結果（不提交）
    ├── *_analysis.xlsx             # Excel 分析結果（不提交）
    ├── *_YYYYMMDD_HHMMSS.csv       # 備份檔案（時間戳記命名，不提交）
    ├── *_YYYYMMDD_HHMMSS.xlsx      # 備份檔案（時間戳記命名，不提交）
    └── [實際出勤資料].txt          # 使用者的出勤檔案（不提交）
```

## 檔案說明

### 核心檔案
- `attendance_analyzer.py`：主程式，包含增量分析功能
- `test/test_attendance_analyzer.py`：完整的單元測試套件
- `lib/excel_exporter.py`：共用 Excel 匯出工具
- `sample-attendance-data.txt`：測試用範例資料

### 增量分析相關
- `attendance_state.json`：使用者處理狀態（隱私，不提交）
- 狀態欄位：輸出檔包含 `[NEW] 本次新發現` 或 `已存在` 標示

### 備份系統相關
- 備份檔名：`<原檔名>_YYYYMMDD_HHMMSS.<副檔名>`（例：`sample_20250827_165618.xlsx`）
- 建立新分析檔前自動備份，避免覆蓋
- 備份檔皆由 `.gitignore` 排除

### 隱私保護
- 實際使用者資料與分析結果皆不提交版本控制
- 僅保留去識別化範例檔案


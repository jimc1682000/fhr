# 考勤分析系統

> Python attendance analyzer with Taiwan holiday support, calculating late arrivals, overtime, and WFH recommendations

這是一個企業考勤分析工具，可以自動分析考勤記錄並計算需要申請的遲到/加班時數。

## 功能特色

- 🕒 自動計算遲到時數
- ⏰ 自動計算加班時數（符合1小時以上規定）
- 🏠 自動識別週五WFH假建議
- 📊 生成詳細分析報告
- 📈 匯出CSV格式統計資料
- 🔄 智慧忘刷卡建議（每月2次額度）
- 🗓️ 支援跨年份出勤分析（自動載入國定假日）

## 出勤規則

- **彈性上下班**：每日工作8小時 + 1小時午休
- **上班時間**：最早08:30，最晚10:30
- **午休時間**：12:30-13:30
- **加班規定**：最少1小時以上才可申請，之後每半小時一個區間
- **週五規定**：預設WFH日，可申請整天9小時WFH假（國定假日除外）

## 安裝與使用

### 基本使用

```bash
python attendance_analyzer.py <考勤檔案路徑> [格式]
```

**參數說明**：
- `考勤檔案路徑`：必填，出勤資料檔案路徑
- `格式`：可選，輸出格式 (`excel` 或 `csv`)，預設為 `excel`

### 範例

```bash
# 使用範例檔案測試（預設Excel格式）
python attendance_analyzer.py "sample-attendance-data.txt"

# 指定輸出格式
python attendance_analyzer.py "sample-attendance-data.txt" excel
python attendance_analyzer.py "sample-attendance-data.txt" csv

# 使用實際出勤檔案（支援不同年份）
python attendance_analyzer.py "202507-202508-員工姓名-出勤資料.txt"
python attendance_analyzer.py "202601-202602-員工姓名-出勤資料.txt" csv
```

## 輸出說明

### 終端報告
系統會在終端顯示完整的分析報告，包含：
- 需要請遲到的日期和時長
- 需要請加班的日期和時長  
- 建議申請WFH假的日期
- 統計摘要

### 分析報告檔案

系統支援兩種輸出格式：

#### Excel格式（預設，推薦）
- 檔案名：`<原檔名>_analysis.xlsx`
- 包含精美格式化的分析報告
- 類型色彩標示：遲到(紅)、加班(藍)、WFH(綠)、忘刷卡(橙)
- 自動欄位寬度調整
- 跨平台相容（Windows/Mac/Linux）

#### CSV格式（相容性選項）
- 檔案名：`<原檔名>_analysis.csv`
- UTF-8-BOM編碼，確保Mac Excel正確顯示
- 分號分隔，適合歐洲地區Excel設定

**兩種格式都包含**：
- 日期
- 類型（遲到/加班/WFH假）
- 時長（分鐘）
- 詳細說明
- 時段資訊
- 計算公式

## 檔案格式需求

考勤檔案應為tab分隔的文字檔案，包含以下欄位：
1. 應刷卡時段
2. 當日卡鐘資料  
3. 刷卡別（上班/下班）
4. 卡鐘編號
5. 資料來源
6. 異常狀態
7. 處理狀態
8. 異常處理作業
9. 備註

### 範例資料格式

```
應刷卡時段	當日卡鐘資料	刷卡別	卡鐘編號	資料來源	異常狀態	處理狀態	異常處理作業	備註
2025/07/01 08:00	2025/07/01 10:28	上班	1	刷卡匯入				
2025/07/01 17:00	2025/07/01 21:33	下班	1	刷卡匯入			
2025/07/04 08:00		上班			曠職	已處理		
2025/07/04 17:00		下班			曠職	已處理		
2025/07/08 08:00	2025/07/08 10:32	上班	1	刷卡匯入	遲到	已處理		
```

**注意**：
- 各欄位之間使用tab字元分隔
- 曠職記錄的「當日卡鐘資料」欄位為空
- 週五的記錄會被自動識別為WFH假建議
- 系統已包含範例檔案 `sample-attendance-data.txt` 供測試使用

## 計算邏輯

### 遲到計算
- 上班時間超過10:30即為遲到
- 計算實際打卡時間與10:30的時間差

### 加班計算  
- 下班時間 = 上班時間 + 8小時 + 1小時午休
- 實際下班時間超過計算下班時間即為加班
- 只有加班時間≥1小時才會列入申請建議

### 週五處理
- 自動識別週五日期
- 建議申請整天WFH假而非計算遲到/加班

## 系統架構

```
attendance_analyzer.py
├── AttendanceRecord: 考勤記錄資料結構
├── WorkDay: 工作日資料結構  
├── Issue: 問題記錄資料結構
└── AttendanceAnalyzer: 主要分析器
    ├── parse_attendance_file(): 解析考勤檔案
    ├── group_records_by_day(): 按日期分組記錄
    ├── analyze_attendance(): 分析考勤問題
    ├── generate_report(): 生成文字報告
    └── export_csv(): 匯出CSV統計
```

## 範例輸出

```
# 考勤分析報告

## 需要請遲到的日期：

1. **2025/07/08** - 遲到2分鐘
2. **2025/07/22** - 遲到281分鐘

## 需要請加班的日期：

1. **2025/07/01** - 加班2小時5分鐘
2. **2025/07/21** - 加班1小時58分鐘

## 建議申請WFH假的日期：

1. **2025/07/04** - 建議申請整天WFH假

## 統計摘要：

- 遲到天數：2 天
- 加班天數：2 天  
- 建議WFH天數：1 天
```

## 國定假日支援

系統採用混合假日載入策略，確保跨年份資料分析的準確性：

### 2025年（當年）
- 使用硬編碼假日清單，提供最佳效能
- 包含完整的台灣國定假日（春節、清明、端午、中秋、國慶等）

### 其他年份（2026+）
- 自動檢測出勤資料中的年份
- 嘗試從政府開放資料API動態載入假日
- API不可用時載入基本假日（元旦、國慶日）
- 系統會顯示載入狀態資訊

### 載入過程
```
資訊: 動態載入 2026 年國定假日...
警告: 無法取得 2026 年完整假日資料，僅載入基本固定假日
```

## 注意事項

- 曠職記錄（無打卡資料）不會計入分析
- 週五的考勤記錄會被標記為WFH假建議
- 加班時間未滿1小時不會列入申請建議
- 系統僅分析工作日，不處理週末和國定假日
- 跨年份資料會自動載入相應年份的國定假日

## 專案結構

```
fhr/
├── attendance_analyzer.py          # 主要分析程式
├── test_attendance_analyzer.py     # 單元測試（包含跨年份測試）
├── sample-attendance-data.txt      # 範例出勤資料
├── CLAUDE.md                       # AI代理知識庫
├── README.md                       # 說明文件
└── [分析結果檔案]
    ├── *_analysis.csv              # CSV格式分析結果
    └── [實際出勤資料].txt          # 使用者的出勤檔案
```

## 技術需求

### 必要環境
- Python 3.6+
- 標準庫（sys, datetime, csv, re等）

### 可選依賴
- `openpyxl`：Excel格式支援（推薦安裝）
  ```bash
  pip install openpyxl
  ```

**注意**：
- 如果未安裝 `openpyxl`，系統會自動回退到CSV格式
- CSV格式完全基於標準庫，無需額外安裝

## 授權

此專案採用 MIT License 授權。

### MIT License

```
MIT License

Copyright (c) 2025 Jimmy Chen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

此工具為企業考勤管理工具，適用於彈性工時制度的公司。
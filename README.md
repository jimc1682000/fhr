# 考勤分析系統

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

## 出勤規則

- **彈性上下班**：每日工作8小時 + 1小時午休
- **上班時間**：最早08:30，最晚10:30
- **午休時間**：12:30-13:30
- **加班規定**：最少1小時以上才可申請，之後每半小時一個區間
- **週五規定**：預設WFH日，可申請整天9小時WFH假（國定假日除外）

## 安裝與使用

### 基本使用

```bash
python attendance_analyzer.py <考勤檔案路徑> [格式] [選項]
```

**參數說明**：
- `考勤檔案路徑`：必填，出勤資料檔案路徑
- `格式`：可選，輸出格式 (`excel` 或 `csv`)，預設為 `excel`

**分析模式選項**：
- `--incremental` / `-i`：啟用增量分析模式（預設）
- `--full` / `-f`：強制完整重新分析
- `--reset-state` / `-r`：清除使用者的處理狀態記錄

### 使用範例

#### 增量分析範例（推薦）
```bash
# 預設增量分析模式 - 自動跳過已處理資料
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt"

# 跨月檔案增量分析
python attendance_analyzer.py "202508-202509-員工姓名-出勤資料.txt"

# 指定輸出格式（增量分析 + CSV）
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" csv
```

#### 完整分析模式
```bash
# 強制重新分析所有資料
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --full

# 清除處理狀態後重新分析
python attendance_analyzer.py "202508-員工姓名-出勤資料.txt" --reset-state
```

#### 範例檔案測試
```bash
# 使用範例檔案測試（會回退到完整分析模式）
python attendance_analyzer.py "sample-attendance-data.txt"
python attendance_analyzer.py "sample-attendance-data.txt" csv
```

## 輸出說明

### 終端報告
系統會在終端顯示完整的分析報告，包含：
- 需要請遲到的日期和時長
- 需要請加班的日期和時長  
- 建議申請WFH假的日期
- 統計摘要

### 分析報告檔案

#### 📦 智慧備份系統
- **自動備份**：建立新分析檔案前，自動備份現有檔案
- **時間戳記命名**：備份檔案格式 `<原檔名>_YYYYMMDD_HHMMSS.<副檔名>`
- **範例**：`sample-attendance-data_analysis.xlsx` → `sample-attendance-data_analysis_20250827_165618.xlsx`
- **使用者控制**：讓使用者自行決定保留檔案數量和版本管理
- **安全保障**：避免意外覆蓋檔案造成資料遺失

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
- **NEW**: 狀態（在增量模式下標示 `[NEW] 本次新發現` 或 `已存在`）

### 實際使用範例

以下展示增量分析的實際效果：

#### 第一次分析
```bash
python attendance_analyzer.py "202507-202508-員工姓名-出勤資料.txt"
```
**輸出**：
```
📋 識別使用者: 員工姓名
📅 檔案涵蓋期間: 2025-07-01 至 2025-08-31
🔄 增量分析: 發現 36 個新的完整工作日需要處理
💾 已更新處理狀態: 2025-07-01 至 2025-08-26

統計摘要：
- 🔄 建議忘刷卡天數：3 天
- 😰 需要請遲到天數：2 天
- 💪 加班天數：6 天
```

#### 第二次分析（文件無變化）
```bash
python attendance_analyzer.py "202507-202508-員工姓名-出勤資料.txt"
```
**輸出**：
```
⚠️  發現重疊日期範圍: [(2025-07-01, 2025-08-26)]
✅ 增量分析: 沒有新的工作日需要處理
📊 跳過已處理：36 天

統計摘要：全部為 0（因為沒有新資料需要處理）
```

## 增量分析功能 🚀

### 工作原理
1. **檔案名稱識別**：自動從檔名提取使用者姓名和日期範圍
2. **狀態管理**：使用 `attendance_state.json` 記錄處理歷史
3. **智慧重疊檢測**：自動處理跨月檔案的日期重疊問題
4. **完整工作日識別**：僅處理有上下班記錄的完整工作日
5. **按月額度管理**：忘刷卡使用次數按年月分別計算

### 檔案命名規範
為了啟用增量分析，檔案名稱必須遵循以下格式：
- **單月檔案**：`YYYYMM-姓名-出勤資料.txt`（如：`202508-員工姓名-出勤資料.txt`）
- **跨月檔案**：`YYYYMM-YYYYMM-姓名-出勤資料.txt`（如：`202508-202509-員工姓名-出勤資料.txt`）

### 狀態檔案說明
系統會在專案根目錄建立 `attendance_state.json` 來追蹤：
- 各使用者的處理日期範圍
- 每月忘刷卡使用統計
- 最後處理時間記錄

⚠️ **注意事項**：
- 如果檔案名稱不符合規範，系統會自動回退到完整分析模式
- 🔒 **隱私保護**：`attendance_state.json` 包含使用者識別資訊，已設定為不提交至版本控制
- 📁 **本地檔案**：每位使用者的狀態檔案僅存於本地，不會與他人共享

## 檔案格式需求

### 檔案命名（增量分析必需）
參見上方「檔案命名規範」

### 資料格式
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

### 完整工作日定義
- 必須同時有上班和下班兩筆記錄
- 不論實際打卡時間是否為空（曠職也算完整記錄）
- 只有單一上班或下班記錄的日期不會被處理

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

### 核心元件
```
attendance_analyzer.py
├── AttendanceRecord: 考勤記錄資料結構
├── WorkDay: 工作日資料結構  
├── Issue: 問題記錄資料結構（增強：支援新/舊狀態）
├── AttendanceStateManager: 🆕 狀態管理器（JSON持久化）
└── AttendanceAnalyzer: 主要分析器（增強版）
    ├── parse_attendance_file(): 解析檔案 + 初始化增量狀態
    ├── group_records_by_day(): 分組記錄 + 載入假日資料  
    ├── analyze_attendance(): 智慧分析（完整/增量模式）
    ├── generate_report(): 生成報告 + 增量統計資訊
    ├── export_csv(): CSV匯出 + 狀態欄位
    ├── export_excel(): Excel匯出 + 狀態標示
    └── 🆕 增量分析相關方法:
        ├── _extract_user_and_date_range_from_filename(): 檔名解析
        ├── _identify_complete_work_days(): 完整工作日識別
        ├── _get_unprocessed_dates(): 新日期檢測
        └── _update_processing_state(): 狀態更新
```

### 增量分析流程
1. **檔名解析** → 提取使用者和日期範圍
2. **狀態載入** → 讀取 `attendance_state.json`
3. **重疊檢測** → 識別已處理的日期範圍
4. **工作日篩選** → 找出新的完整工作日
5. **智慧分析** → 僅分析新資料
6. **狀態更新** → 保存處理結果

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
├── attendance_analyzer.py          # 主要分析程式（增強版，支援增量分析）
├── test_attendance_analyzer.py     # 單元測試（包含跨年份測試）
├── sample-attendance-data.txt      # 範例出勤資料
├── sample-attendance-data_analysis.csv # 範例分析結果（含狀態欄位）
├── CLAUDE.md                       # AI代理知識庫（技術文件）
├── README.md                       # 使用者說明文件
├── .gitignore                      # 版本控制排除規則（保護隱私）
└── [執行時產生的檔案]
    ├── attendance_state.json       # 增量分析狀態檔案（不提交）
    ├── *_analysis.csv              # CSV格式分析結果（不提交）
    ├── *_analysis.xlsx             # Excel格式分析結果（不提交）
    ├── *_YYYYMMDD_HHMMSS.csv       # 🆕 備份檔案（時間戳記命名，不提交）
    ├── *_YYYYMMDD_HHMMSS.xlsx      # 🆕 備份檔案（時間戳記命名，不提交）
    └── [實際出勤資料].txt          # 使用者的出勤檔案（不提交）
```

### 檔案說明

#### 核心檔案
- **attendance_analyzer.py**: 主程式，包含所有增量分析功能
- **test_attendance_analyzer.py**: 完整的單元測試套件
- **sample-attendance-data.txt**: 測試用範例資料

#### 增量分析相關
- **attendance_state.json**: 🔒 使用者處理狀態（包含隱私資訊，不提交）
- **狀態欄位**: 所有輸出檔案都包含 `[NEW] 本次新發現` 或 `已存在` 標示

#### 備份系統相關
- **備份檔案命名**: `<原檔名>_YYYYMMDD_HHMMSS.<副檔名>`（如：`sample_20250827_165618.xlsx`）
- **自動備份**: 建立新分析檔案前，自動備份現有同名檔案
- **使用者控制**: 使用者可自行管理備份檔案的保留和刪除
- **隱私保護**: 所有備份檔案都被 `.gitignore` 排除，不會意外提交

#### 隱私保護
- 所有實際使用者資料和分析結果都被 `.gitignore` 排除
- 備份檔案採用時間戳記模式匹配，確保完全排除
- 僅保留去識別化的範例檔案供測試使用

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

### 測試與品質保證

#### 單元測試
```bash
# 運行完整測試套件（21個測試）
python3 test_attendance_analyzer.py

# 測試涵蓋範圍
# ✅ 核心業務邏輯（8個測試）
# ✅ 輸出格式驗證（3個測試）
# ✅ 進階功能（3個測試）
# ✅ 增量分析與備份（5個測試）
# ✅ 資料結構驗證（3個測試）
```

**測試特色**：
- **100% 通過率**：所有測試在各種環境下穩定通過
- **隔離執行**：使用臨時檔案，測試間互不干擾
- **自動清理**：所有測試產生的檔案自動刪除
- **真實場景**：涵蓋實際使用情況和邊界條件

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
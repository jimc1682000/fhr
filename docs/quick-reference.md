# 快速參考手冊 (Quick Reference)

> 命令、格式與設定速查表 - 適合熟悉系統的用戶快速查詢

## 🎯 命令速查表

### CLI 基本操作
| 操作 | 命令 | 說明 |
|------|------|------|
| **基本分析** | `python attendance_analyzer.py file.txt` | 預設：Excel + 增量模式 |
| **強制完整分析** | `python attendance_analyzer.py file.txt --full` | 重新處理所有資料 |
| **CSV 輸出** | `python attendance_analyzer.py file.txt csv` | 如無 openpyxl 的備選方案 |
| **重置使用者狀態** | `python attendance_analyzer.py file.txt --reset-state` | 清除處理歷史記錄 |
| **Debug 模式** | `python attendance_analyzer.py file.txt --debug` | 詳細日誌、停用狀態寫入 |
| **保留 timestamp 備份** | `python attendance_analyzer.py file.txt --export-policy archive` | 匯出前備份舊檔案 |
| **清理匯出檔案** | `python attendance_analyzer.py file.txt --cleanup-exports` | 列出待刪清單並詢問；預設刪 timestamp，Debug 模式也刪主檔 |
| **顯示幫助** | `python attendance_analyzer.py --help` | 完整參數說明 |

### Web 服務操作  
| 操作 | 命令 | 存取位置 |
|------|------|----------|
| **啟動開發服務** | `uvicorn server.main:app --reload` | http://localhost:8000 |
| **指定埠號** | `uvicorn server.main:app --port 8080` | http://localhost:8080 |
| **API 文件** | 啟動服務後瀏覽 | http://localhost:8000/docs |
| **健康檢查** | `curl localhost:8000/api/health` | JSON 回應 |

### Docker 部署
| 操作 | 命令 | 說明 |
|------|------|------|
| **建立映像** | `docker build -t fhr:latest .` | 建立 Docker 映像 |
| **啟動服務** | `docker run -p 8000:8000 -v "$PWD/build:/app/build" fhr` | 單次執行 |
| **Compose 啟動** | `docker compose up -d` | 背景執行服務 |
| **查看日誌** | `docker logs fhr` | 檢視容器日誌 |
| **停止服務** | `docker compose down` | 停止 Compose 服務 |

### 開發工具
| 操作 | 命令 | 用途 |
|------|------|------|
| **執行測試** | `python -m unittest -q` | 完整測試套件 |
| **測試覆蓋率** | `make coverage` | 產生覆蓋率報告 |
| **程式碼檢查** | `make lint` | Ruff 或 fallback 檢查 |
| **安裝開發工具** | `pip install -r requirements-dev.txt` | Black, Ruff, pre-commit |
| **安裝 Git Hook** | `make install-hooks` | 自動格式化與測試 |

## 📁 檔案格式速查

### 檔名格式規範 (增量分析必需)
```bash
# 單月檔案
YYYYMM-姓名-出勤資料.txt
# 範例: 202508-王小明-出勤資料.txt

# 跨月檔案  
YYYYMM-YYYYMM-姓名-出勤資料.txt
# 範例: 202508-202509-王小明-出勤資料.txt
```

### 檔案內容格式 (9 欄位，tab 分隔)
```
應刷卡時段	當日卡鐘資料	刷卡別	卡鐘編號	資料來源	異常狀態	處理狀態	異常處理作業	備註
2025/07/01 08:00	2025/07/01 10:28	上班	1	刷卡匯入				
2025/07/01 17:00	2025/07/01 21:33	下班	1	刷卡匯入				
```

### 輸出檔案格式
| 格式 | 檔名範例 | 特色 |
|------|----------|------|
| **Excel** | `file_analysis.xlsx` | 色彩標示、欄寬最佳化 |
| **CSV** | `file_analysis.csv` | UTF-8-BOM、分號分隔 |
| **備份檔（archive 模式）** | `file_analysis_20250127_143022.xlsx` | 使用 `--export-policy archive` 時產生 |

## ⚙️ 設定速查

### 環境變數
```bash
# 假日 API 設定
export HOLIDAY_API_MAX_RETRIES=3          # 最大重試次數
export HOLIDAY_API_BACKOFF_BASE=0.5       # 退避基準秒數
export HOLIDAY_API_MAX_BACKOFF=8          # 最大等待秒數

# 日誌設定
export FHR_LOG_LEVEL=INFO                 # 日誌等級
export FHR_LOG_FILE=fhr.log               # 日誌檔案
export FHR_DEBUG=false                    # Debug 模式（true 時跳過狀態寫入）

# 狀態檔案 (Docker 適用)
export FHR_STATE_FILE=/app/build/attendance_state.json
```

### 基本 config.json 範本
```json
{
  "work_hours": 8,
  "lunch_break_minutes": 60,
  "latest_arrival_time": "10:30",
  "overtime_minimum_minutes": 60,
  "forget_punch_monthly_limit": 2
}
```

### 完整 config.json 範例
```json
{
  "work_hours": 8,
  "lunch_break_minutes": 60,
  "earliest_checkin": "08:30",
  "latest_checkin": "10:30", 
  "lunch_start": "12:30",
  "lunch_end": "13:30",
  "overtime_minimum_minutes": 60,
  "overtime_increment_minutes": 60,
  "forget_punch_allowance_per_month": 2,
  "forget_punch_max_minutes": 60
}
```

## 🔍 常見問題快速修復

| 問題 | 快速檢查 | 解決方案 |
|------|----------|----------|
| **無 Excel 輸出** | `python -c "import openpyxl"` | `pip install openpyxl` |
| **增量分析未啟用** | 檢查檔名格式 | 使用 `YYYYMM-姓名-出勤資料.txt` |
| **假日載入失敗** | `ping data.gov.tw` | 檢查網路，系統會使用基本假日 |
| **記憶體不足** | `free -h` | 使用 CSV 格式或分割檔案 |
| **權限錯誤** | `ls -la *.txt` | `chmod 644 *.txt` |
| **處理緩慢** | `df -h` | 檢查磁碟空間與網路連線 |

## 🎨 輸出格式範例

### 終端報告範例
```
# 🎯 考勤分析報告 ✨

📋 使用者: 王小明
📅 處理期間: 2025-08-01 至 2025-08-31
🔄 增量分析: 發現 15 個新的完整工作日需要處理

## 🔄 建議使用忘刷卡的日期：
1. **2025/08/05** - 🔄✅ 遲到15分鐘，建議使用忘刷卡 (本月剩餘: 1次)

## 😰 需要請遲到的日期：  
1. **2025/08/10** - 😅 遲到75分鐘 (超過1小時)

## 💪 需要請加班的日期：
1. **2025/08/01** - 🔥 加班2小時5分鐘

## 🏠 建議申請WFH假的日期：
1. **2025/08/04** - 😊 建議申請整天WFH假

## 📊 統計摘要：
- 忘刷卡建議：1 天
- 遲到天數：1 天  
- 加班天數：1 天
- WFH建議天數：1 天
```

### Excel 輸出欄位
| 欄位 | 內容範例 | 說明 |
|------|----------|------|
| **日期** | 2025/08/05 | YYYY/MM/DD 格式 |
| **類型** | 遲到 | 問題類型 |
| **時長(分鐘)** | 75 | 數值格式 |
| **說明** | 遲到75分鐘 | 使用者友善描述 |
| **時段** | 10:30-11:45 | 時間範圍 |
| **計算式** | 實際時間11:45 > 最晚到班10:30 | 計算邏輯 |
| **狀態** | [NEW] 本次新發現 | 增量模式狀態 |

### CSV 輸出格式 (UTF-8-BOM, 分號分隔)
```csv
日期;類型;時長(分鐘);說明;時段;計算式;狀態
2025/08/05;遲到;75;遲到75分鐘;10:30-11:45;實際時間11:45 > 最晚到班10:30;[NEW] 本次新發現
```

## 🌐 API 端點速查

### REST API 端點
| 方法 | 端點 | 功能 | 參數 |
|------|------|------|------|
| **POST** | `/api/analyze` | 上傳分析 | file, mode, output, reset_state, debug |
| **GET** | `/api/download/{id}/{filename}` | 下載結果 | 路徑參數 |
| **GET** | `/api/health` | 健康檢查 | 無 |
| **GET** | `/docs` | API 文件 | 無 |
| **GET** | `/` | Web 介面 | 無 |

### cURL 範例
```bash
# 基本分析
curl -F "file=@sample-data.txt" \
     -F mode=incremental \
     -F output=excel \
     -F reset_state=false \
     -F debug=false \
     http://localhost:8000/api/analyze

# 健康檢查
curl http://localhost:8000/api/health

# 下載結果
curl -O http://localhost:8000/api/download/{analysis_id}/{filename}
```

## 💡 效能最佳化提示

### 處理速度最佳化
- **小檔案** (<1MB)：任何模式都很快
- **中檔案** (1-10MB)：推薦使用增量模式
- **大檔案** (>10MB)：分割檔案或使用 CSV 格式
- **網路受限**：設定 `HOLIDAY_API_MAX_RETRIES=0`

### 記憶體使用最佳化
- **Excel 模式**：需要額外 30% 記憶體
- **CSV 模式**：記憶體使用最少
- **增量模式**：只處理新資料，節省記憶體
- **Docker 模式**：設定適當的記憶體限制

---

💡 **小提示**: 將此頁面加入書籤以便快速查詢。大多數問題的解答都能在這裡找到，詳細說明請參考 [troubleshooting.md](troubleshooting.md)。

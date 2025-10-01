# 考勤分析系統

[![Coverage](assets/coverage.svg)](docs/testing.md)

> Python attendance analyzer with Taiwan holiday support, calculating late arrivals, overtime, and WFH recommendations

這是一個企業考勤分析工具，可以自動分析考勤記錄並計算需要申請的遲到/加班時數。

## 功能特色

- 🕒 自動計算遲到時數
- ⏰ 自動計算加班時數（符合1小時以上規定）
- 🏠 **自動識別週五WFH假建議（無論是否有打卡，除國定假日外）**
- 📊 生成詳細分析報告
- 📈 匯出Excel/CSV格式統計資料
- 🔄 智慧忘刷卡建議（每月2次額度）
- 🗓️ 支援跨年份出勤分析（自動載入國定假日）
- **🚀 NEW: 增量分析功能 - 避免重複處理已分析資料**
- **📁 NEW: 支援跨月檔案格式 (`202508-202509-姓名-出勤資料.txt`)**
- **💾 NEW: 智慧狀態管理 - 自動記住處理進度**
- **📋 NEW: 增強輸出格式 - 標示新發現與已存在問題**

## 🚀 快速開始 - 選擇適合的使用方式

### 👤 個人用戶 (命令列工具)
```bash
# 最常用：自動增量分析
python attendance_analyzer.py "202508-王小明-出勤資料.txt"

# 產生 CSV 格式
python attendance_analyzer.py "202508-王小明-出勤資料.txt" csv

# 跨月資料處理
python attendance_analyzer.py "202508-202509-王小明-出勤資料.txt"
```

### 🖥️ 系統管理員 (Web 服務 + Docker)
```bash
# Docker 一鍵部署
docker compose up --build -d
# 瀏覽器開啟 http://localhost:8000

# 或手動啟動 Web 服務
pip install fastapi uvicorn pydantic python-multipart openpyxl
uvicorn server.main:app --reload
# 瀏覽器開啟 http://localhost:8000
```

### 👩‍💻 開發者 (本地開發環境)
```bash
# 完整開發環境設定
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt              # 包含開發工具
make install-hooks                                # 安裝 Git pre-commit hooks
python -m unittest -q                            # 執行測試套件
make coverage                                     # 檢查測試覆蓋率
```

## 📊 系統能力與特色
- **🎯 精準度**: 90%+ 測試覆蓋率  
- **⚡ 效能**: 支援處理 10 萬筆記錄，增量分析避免重複處理
- **🔒 安全性**: 本地處理，資料不上傳，支援企業隱私要求
- **🌏 國際化**: 完整中英文介面，支援台灣國定假日
- **🔧 可擴展**: 模組化架構，支援客製化業務規則

## 🏢 企業級功能
- **🌐 Web 介面**: FastAPI 後端 + 現代化前端，支援多人使用
- **🐳 容器部署**: Docker 生產就緒，支援 Kubernetes 擴展  
- **🔗 API 整合**: REST API 支援與 HRIS/薪資系統整合
- **👥 多租戶**: 支援多部門、多公司資料隔離
- **📈 監控**: 內建健康檢查、日誌管理與效能監控

## Quick Start (傳統 CLI)

提示：如需 Excel 匯出，建議安裝 `openpyxl`：`pip install openpyxl`。

### Debug 模式（安全測試）

- 在 CLI 加上 `--debug`：`python attendance_analyzer.py sample-attendance-data.txt --debug`
  - 日誌層級提升為 DEBUG，顯示解析、分組與分析細節。
  - 停用狀態檔寫入，確保不會覆寫 `attendance_state.json`。
- 後端服務可設定環境變數 `FHR_DEBUG=true` 取得相同效果。

### 常見錯誤提示

- 看不到 Excel 輸出 → 未安裝 `openpyxl`，請先安裝或改用 `csv` 格式。
- 未啟用增量分析 → 檔名需為 `YYYYMM-姓名-出勤資料.txt` 或 `YYYYMM-YYYYMM-姓名-出勤資料.txt`。
- 解析失敗或欄位錯亂 → 原始檔需為「tab 分隔」的文字檔（.txt），不是逗號或空白分隔。
- 沒有任何輸出變化 → 可能無新資料；若要重跑全部，加入 `--full` 或 `--reset-state`。

## 📚 完整文件

👉 **[文件導航中心](docs/index.md)** - 快速找到您需要的文件  
🔍 **[命令速查手冊](docs/quick-reference.md)** - 常用命令與格式參考  
🛠️ **[疑難排解指南](docs/troubleshooting.md)** - 問題診斷與解決方案  
📋 **[改進項目清單](todos/README.md)** - 待開發功能與文檔改進項目

## 延伸閱讀（docs/）

**核心功能文件**:
- [系統概覽](docs/overview.md) - 整體功能與企業級特色
- [使用指南](docs/usage.md) - 詳細操作說明與最佳實務  
- [檔案格式](docs/data-format.md) - 輸入檔案格式與命名規範
- [增量分析](docs/incremental.md) - 智慧狀態管理與處理邏輯
- [輸出格式](docs/output.md) - Excel/CSV 匯出與備份機制

**技術文件**:
- [系統架構](docs/architecture.md) - 模組化設計與資料流程
- [業務邏輯](docs/logic.md) - 考勤規則與計算方式
- [測試框架](docs/testing.md) - 100% 覆蓋率測試策略
- [環境設定](docs/environment.md) - 假日 API 與環境變數

**部署與維護**:
- [Web 服務](docs/service.md) - FastAPI 後端與前端部署
- [系統需求](docs/requirements.md) - 相依套件與硬體需求
- [專案結構](docs/project-structure.md) - 檔案組織與模組說明
- [貢獻指南](docs/contributing.md) - 開發流程與程式碼規範

**企業級文件** (23 個文件完整列表請見 [docs/index.md](docs/index.md))

## Web 服務（Backend + Frontend）

- 後端：FastAPI，提供上傳、分析、下載 API，自動產生 OpenAPI 文件。
- 前端：輕量靜態頁面（vanilla + i18next）支援 i18n，提供上傳、選擇增量/完整、CSV/Excel、重置狀態、預覽與下載。

啟動方式：

```bash
pip install fastapi uvicorn pydantic python-multipart  # 可選：openpyxl（Excel）
uvicorn server.main:app --reload
# 瀏覽器開啟 http://localhost:8000/
# API docs: http://localhost:8000/docs
```

更多說明請見：[docs/service.md](docs/service.md)

### Docker 部署

```bash
# 建置映像
docker build -t fhr:latest .

# 執行（將容器內 build/ 掛載到本機以保留輸出與上傳）
docker run --rm -p 8000:8000 -v "$PWD/build:/app/build" fhr:latest

# 瀏覽器開啟 http://localhost:8000/
```

或使用 Docker Compose：

```bash
docker compose up --build -d
# 停止：docker compose down
```

## Lint

- 推薦：安裝 Ruff/Black 並執行 `make lint`（若無 Ruff，會使用內建的輕量 fallback 檢查：語法）。

```bash
# 使用 ruff（如已安裝）
make lint

# 或手動執行 fallback（無外部依賴）
python3 tools/lint.py

# 開發者可選：安裝開發工具與 Git Hook
pip install -r requirements-dev.txt
make install-hooks  # 安裝 pre-commit hook（black + ruff + tests）
```

CI（GitHub Actions）
- 對 PR 自動執行：Ruff（lint）、Black（格式檢查）、單元測試 + 覆蓋率 100% 門檻。

備註：
- UI 預設為「完整」模式與「Excel」輸出，且選項順序預設優先顯示。
- 下載檔名結尾會自動加上 UTC 時間戳（`_analysis_YYYYMMDD_HHMMSS`），避免重複下載覆蓋。
- Docker 內部會將狀態檔寫入 `/app/build/attendance_state.json`（可由 `FHR_STATE_FILE` 覆蓋）。掛載 `-v "$PWD/build:/app/build"` 可保留狀態於主機端。

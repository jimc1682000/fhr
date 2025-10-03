# 專案結構

```text
fhr/
├── attendance_analyzer.py          # CLI 入口與報告彙整
├── lib/                            # 共用邏輯模組
│   ├── service/                    # AnalyzerService、Options、Result 等資料模型
│   ├── excel_exporter.py           # Excel 匯出邏輯
│   ├── i18n.py                     # 多語系 helper（CLI/Web/TUI 共用）
│   ├── recent.py                   # 近期檔案與歷史紀錄 helper
│   └── __init__.py
├── tui/                            # Textual 文字介面
│   ├── __main__.py                 # `python -m tui` 啟動器（含 --webview）
│   ├── __init__.py
│   └── app.py                      # AttendanceAnalyzerApp + 表單/進度 UI
├── server/                         # FastAPI 服務
│   └── main.py                     # REST API 與靜態檔掛載
├── web/                            # 靜態前端（vanilla + i18next）
├── docs/                           # 文件系統（使用者/運維/開發/企業）
│   ├── index.md                    # 文件導航
│   ├── usage.md                    # CLI/TUI 使用指南
│   ├── architecture.md             # 系統架構與服務層
│   └── ...
├── test/                           # 單元測試與 Textual headless 驗證
│   ├── test_service_analyzer.py
│   └── test_tui_app.py             # 表單流程、語系、textual-web smoke
├── assets/                         # 文件與 README 插圖
│   ├── coverage.svg
│   └── tui-main.png                # Textual 主畫面截圖
├── todos/                          # 任務追蹤（含 M1~M4 進度）
├── requirements.txt                # 執行所需依賴（含 textual、textual-web 選配）
├── requirements-dev.txt            # 開發工具（ruff、black、pre-commit）
├── Makefile                        # lint、測試、coverage 快速指令
├── CLAUDE.md / AGENTS.md           # AI 協作與程式貢獻說明
└── README.md                       # 快速開始、安裝步驟與 TUI 截圖
```

## 檔案說明

### 核心元件
- **`attendance_analyzer.py`**：負責指令列流程控制與報告輸出。
- **`lib/service/`**：共享 `AnalyzerService`，提供 CLI/Web/TUI 一致的分析結果、預覽與匯出控制。
- **`lib/i18n.py`**：集中語系偵測與翻譯字串，支援 `Ctrl+L` 語系切換。
- **`lib/recent.py`**：紀錄使用者近期分析檔案，供 TUI/UI 顯示歷程。
- **`docs/`**：文件入口，包含 TUI 操作、安全建議與遷移注意事項。

### 介面與工具
- **CLI**：直接執行 `attendance_analyzer.py` 或 `python attendance_analyzer.py`。
- **Textual TUI**：`python -m tui`（`--webview` 為 textual-web 選配）。
- **Web**：FastAPI (`server/main.py`) + 靜態前端 (`web/`)；Docker、Compose 支援請參考 `docs/service.md`。
- **測試**：`python -m unittest -q`，TUI 相關測試位於 `test/test_tui_app.py`。

### 產出與忽略項目
- `attendance_state.json`、`*_analysis.(csv|xlsx)`、備份檔案：皆列入 `.gitignore`。
- textual-web 截圖與錄影請儲存於 `assets/` 或 `docs/` 對應目錄，並在 `docs/tui_capture_setup.md` 記錄命名規則。

### 遷移提示
- 若從舊的 `feat/tui` 分支移植程式碼，請改用 `lib/service/` 的資料模型與 `AnalyzerService.run()`；所有 Textual 元件需整合到 `tui/app.py`。
- 早期腳本若直接操作 `AttendanceAnalyzer` 類別，請改寫為建立 `AnalysisOptions`，並透過服務層呼叫以獲得一致的預覽與匯出行為。

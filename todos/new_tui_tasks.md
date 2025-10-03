# 新版 TUI 任務清單

## 準備階段
- [x] 確認開發環境 Python、pip、virtualenv 版本符合專案需求並已啟用隔離環境。
- [x] 安裝/更新 `requirements-dev.txt`、`requirements-service.txt` 依賴，驗證 lint/測試工具可使用。
- [x] 安裝 `textual>=0.40`、`textual-forms` 等 TUI 相關套件並進行版本確認。
- [x] 執行 `make lint` 與 `python3 -m unittest -q`，確保基線狀態無錯誤。
- [x] 預備截圖或錄影工具以蒐集後續 TUI 介面素材。（詳見 `docs/tui_capture_setup.md` 指南）

## 服務抽象層（M1）
- [x] 擬定共享分析服務模組的檔案結構（例如 `lib/service/analyzer.py`）。
- [x] 抽離選項 schema，包含預設值、驗證與序列化 helper。
- [x] 將匯出、備份、清理流程集中於服務 API。
- [x] 重構近期檔案/歷史紀錄處理，提供可重用的持久化 helper。
- [x] 統一 i18n helper，確保語系偵測與字串共享。
- [x] 更新 CLI 與 Web 入口，改為使用新的服務層。
- [ ] 完成本區任務後，先同步更新 README.md、AGENTS.md、CLAUDE.md，並確認 lint 全數通過，再建立 M1 commit，摘要服務抽象層成果。

## Textual 介面實作（M2）
- [x] 升級相依：鎖定 `textual>=0.40`，加入 `textual-forms`，並配置內建設計 tokens/主題。
- [x] 以設計 tokens 建立 Textual 版面，對齊 Web 控制台區塊。
- [x] 實作表單流程：檔案選擇、旗標（incremental/full/reset/debug）、匯出策略、清理選項。
- [x] 表單送出須串上共享服務，包含進度日誌與取消控制。
- [x] 呈現分析結果預覽表，支援依問題類型著色與分頁/列數限制。
- [x] 利用共享 helper 保存近期檔案，並提供單次執行的歷史檢視。
- [x] 視需要提供 textual-web 入口，透過旗標或 CLI 參數啟用。
- [x] 完成本區任務後，先同步更新 README.md、AGENTS.md、CLAUDE.md，並確認 lint 全數通過，再建立 M2 commit，摘要 TUI MVP 功能。

## 測試與工具（M3）
- [x] 為服務層撰寫單元測試（解析、分析、匯出、清理、近期紀錄）。
- [x] 覆蓋選項 schema 驗證（合法/非法輸入、預設值、序列化）。
- [x] 測試進度/日誌匯流排行為，含取消傳遞。
- [x] 新增 Textual 元件測試，涵蓋表單流程、預覽呈現、語系切換、取消操作。
- [x] 撰寫 textual-web 模式的 smoke/整合測試，檢驗共享 API。
- [x] 若依賴或測試目標調整，更新 CI 腳本。
- [x] 完成本區任務後，先同步更新 README.md、AGENTS.md、CLAUDE.md，並確認 lint 全數通過，再建立 M3 commit，摘要測試與 textual-web 檢核。

## 文件（M4）
- [x] 更新 README，加入安裝步驟、使用說明與新 TUI 截圖/GIF。
- [x] 調整 `docs/index.md` 導覽與相關章節（服務架構、使用指南）。
- [x] 在開發者文件中描述共享服務層，必要時附流程圖。
- [x] 說明 textual-web 的使用方式與限制（內部工具或公開功能）。
- [x] 加入從舊 `feat/tui` 分支遷移的注意事項。
- [x] 完成本區任務後，先同步更新 README.md、AGENTS.md、CLAUDE.md，並確認 lint 全數通過，再建立 M4 commit，摘要文件與遷移更新。

## 待決事項與追蹤
- [x] 決定共享服務模組置於 `lib/service/` 或其他命名空間。（結論與後續行動紀錄於 `docs/tui_decisions.md`）
- [x] 決定 textual-web 模式是否預設啟用或維持選配。（詳見 `docs/tui_decisions.md`）
- [x] 對齊 CLI/Web/TUI 的進度呈現策略（推播或輪詢）並定義共享匯流排介面。（詳見 `docs/tui_decisions.md`）
- [ ] 為各里程碑（M1–M4）安排審查檢查點。

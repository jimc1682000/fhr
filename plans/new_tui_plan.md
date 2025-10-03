# 新版 TUI 計畫

## 目標
- 重新打造 TUI，使其與 CLI、Web 共用核心邏輯，同時提供貼近 Web 控制台的 Textual 使用體驗。
- 建立易於維護且具高測試涵蓋率的程式碼架構，並以共享服務抽象層支撐各介面。

## 預期成果
- 建立涵蓋解析、分析、匯出、清理、近期紀錄與國際化的共享分析服務層。
- 實作採用 textual-forms 與 Textual 內建設計 tokens 的 TUI，支援 Web 版的主要功能與旗標。
- 視需要提供 textual-web 執行入口，供內部 smoke 測試或展示使用。
- 完成架構說明、使用方式與測試流程的文件更新。

## 準備階段
- 確認開發環境已安裝 Python 版本、pip、virtualenv 等必要工具，並更新至專案指定版本。
- 安裝或更新 `requirements-dev.txt`、`requirements-service.txt` 所需套件，確保 lint/測試工具可用。
- 預先安裝 `textual>=0.40` 與 `textual-forms` 等相關依賴，驗證終端環境支援。
- 執行 `make lint` 與基本測試，確保現有主程式狀態健康無誤。
- 準備截圖/錄影工具以便後續紀錄新版 TUI 介面。

## 工作分流
1. **服務抽象層**（命名空間鎖定 `lib/service/`，詳見 `docs/tui_decisions.md`）
   - 抽離分析服務模組，提供同步/非同步 API、選項 schema、進度匯流排與取消掛勾。
   - 統一路徑、備份、清理與近期紀錄的管理介面，供各入口重用。
   - 整合語系偵測與共享字串等 i18n helper。
   - 導入 `ProgressEvent` 匯流排介面，供 CLI/Web/TUI 共用。

2. **Textual 介面實作**
   - 升級 Textual 版本並納入 textual-forms，善用內建設計 tokens 與主題能力。
   - 以表單流程重現 Web 使用步驟：選檔、旗標切換、匯出策略、清理確認、Debug 模式、執行與預覽。
   - 串接共享進度/日誌匯流排與取消事件。
   - textual-web 維持選配：以 CLI 旗標 `--webview` 啟用並提供相依說明。

3. **測試與工具**
   - 為服務層、選項驗證、進度匯流排、近期紀錄撰寫單元測試。
   - 為 Textual 元件新增測試，涵蓋表單流程、預覽呈現、語系切換與取消操作。
   - 規畫 smoke script 或整合測試，驗證 textual-web 模式與 API 行為一致。

4. **文件與開發體驗**
   - 更新 README、docs/index.md，補充新版 TUI 的安裝與使用說明。
   - 擴充開發者文件，說明共享服務架構與測試指引。
   - 視需要調整 todos，並記錄從舊版 feat/tui 分支遷移的注意事項。

## 里程碑
- M1：服務抽象層完成，既有 CLI 回歸測試全部通過，並同步 README.md、AGENTS.md、CLAUDE.md。
- M2：Textual TUI MVP 完成，表單流程、預覽表與進度日誌可正常運作，並同步 README.md、AGENTS.md、CLAUDE.md。
- M3：完整測試組合建立，textual-web smoke 測試納入 CI 或手動檢查流程，並同步 README.md、AGENTS.md、CLAUDE.md。
- M4：文件與 todo 更新完成，進入審查階段，並同步 README.md、AGENTS.md、CLAUDE.md。

## 風險與因應
- **相依套件漂移**：Textual 升級需確認環境相容，鎖定版本並記錄安裝步驟。
- **功能回歸風險**：維持 CLI、Web 測試常駐，及早偵測行為變動。
- **使用體驗落差**：開發時持續比對 Web 流程，重用共享字串與預設值。
- **時程分散**：依序完成服務層→TUI→測試→文件，避免頻繁切換上下文。

## 未決議題
- textual-web 開放策略、共享服務層命名空間與進度呈現方案已記錄於 `docs/tui_decisions.md`。
- 若後續評估結果需要調整，請同步更新該文件與此章節。

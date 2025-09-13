# Textual「逐步精靈」TUI 測試計畫 TODO

目標：在不觸碰真網路與不破壞既有 CLI 的前提下，為 TUI 導入足夠的單元與互動測試，確保相容、穩定與可取消。

## A) 基礎相容性與匯入路徑
- [x] `--tui` 旗標解析：與既有參數並存，不提供時行為不變。
- [x] 未安裝 Textual 時的錯誤訊息（截斷但可比對字串關鍵片段，含安裝指引）。
- [x] `--tui` 搭配預填參數（輸入檔/輸出格式/模式）能在 UI 初始狀態反映（先驗證傳入 `launch_tui()` 的 prefill）。

## B) i18n 行為
- [ ] 預設中文：在 `FHR_LANG=zh_TW` 或系統 `zh*` 時 UI 顯示中文。
- [ ] 非中文語系顯示英文：在 `FHR_LANG=en` 或其他語系時顯示英文。
- [ ] env 覆寫優先於系統語系：`FHR_LANG=en` 強制英文。
- [ ] 未提供翻譯字串時 fallback 至英文 msgid。

## C) Logging 與進度/取消
- [ ] `TextualLogHandler` 能接收 `logger.info/warning/error` 並在 UI 訊息列表出現（以 Test hook 擷取）。
- [ ] 進度回報：模擬 `progress_cb` 連續呼叫，UI 百分比/計數正確更新。
- [ ] 取消：在長任務期間觸發取消，執行緒/旗標被觀察到並善後（UI 回復可互動狀態）。

## D) 預覽表格（前 200 行）
- [ ] 對 `sample-attendance-data.txt` 跑分析後，預覽列數 ≤ 200。
- [ ] 大量資料（製造 5k 行假資料）仍只渲染 200 行，不 OOM/不明顯卡頓（以時間門檻斷言）。
- [ ] 狀態色彩：對幾個關鍵狀態（遲到/加班/WFH/假日）渲染樣式存在（用樣式 class 名稱或 ANSI 樣式斷言）。

## E) Textual 互動測試（Pilot）
- [ ] 開啟 App、透過 Pilot 依序操作 Step 1→5，最終產生輸出路徑摘要。
- [ ] 鍵位：`Enter` 下一步、`Esc` 上一步、`R` 執行、`C` 取消、`Q` 離開（至少抽查 3 個）。
- [ ] 錯誤流程：提供不存在檔案→阻止下一步並顯示錯誤；修正後可繼續。

## F) 與核心互動的替身/隔離
- [ ] 模擬/猴補（monkeypatch）假日 API：mock `urllib.request.urlopen`，確保 TUI 測試不發真網路且路徑有回退。
- [ ] 在 `HOLIDAY_API_MAX_RETRIES=0`、`HOLIDAY_API_BACKOFF_BASE=0` 下執行分析，避免測試延遲。
- [ ] 若分析流程需要長時間，替換為可注入的假任務（adapter 注入），讓取消與進度測試更可控。

## G) CLI 相容性回歸
- [ ] 不帶 `--tui` 的既有指令仍可正常完成（解析/分析/匯出），與快照比對關鍵輸出（例如檔名後綴、欄寬設定不變）。

## H) 文件與 CI
- [ ] `README.md` 新增 `--tui` 章節存在性測試（簡單字串包含即可）。
- [ ] CI 新增含 `[tui]` 的 job 能安裝並最小化啟動 TUI（啟動後立刻關閉），避免無頭環境下掛死（加超時）。

## I) 效能與穩定性（輕量）
- [ ] 小檔案冷啟到可互動時間 < 2s（本地門檻，可放寬於 CI）。
- [ ] 取消後資源釋放：執行緒無殘留、log handler 移除（以弱引用或計數檢查）。

---

### 測試實作備忘
- 測試框架：`unittest`（維持專案慣例）；Textual 互動採 `textual.testing.Pilot`。
- 檔案位置：新增 `test/test_tui_*.py`；避免碰觸既有測試命名。
- 網路：一律 mock；若需時間相關 backoff，透過環境變數置零以確保 deterministic。

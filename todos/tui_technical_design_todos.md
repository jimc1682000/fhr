# Textual「逐步精靈」TUI 技術設計 TODO（Python ≥ 3.8）

狀態：草擬中（此清單將跟隨實作逐項勾選）

## 0) 升版與相容性
- [x] 將專案最低版本調整為 `Python >= 3.8`（`README.md`、任一打包檔案，如 `pyproject.toml`/`setup.cfg`/`requirements.txt`）。
- [x] 於 `README.md` 明確標註「TUI 僅在 Python 3.8+ 支援」。
- [x] 維持既有 CLI 與輸出相容（不變更既有預設與欄寬/狀態列語意）。

## 1) 依賴與安裝（可選 extras）
- [x] 新增 extras：`[tui]`，包含 `textual`（版本大於等於一個穩定小版，例如 `textual>=0.50`；實際鎖定待驗證）。
- [x] `pip install .[tui]` 指南加入 `README.md`，不影響非 TUI 使用者。
- [x] 非 TUI 路徑不 import Textual；`--tui` 才延遲 import，缺少依賴時提供友善錯誤訊息與安裝指引。

## 2) CLI 整合（不破壞既有）
- [x] 新增旗標：`--tui`（預設關閉）。
- [x] `--tui` 模式下，原本的「輸入檔、輸出格式、模式」可選擇性提供，若提供則作為精靈預填值（不立即執行）。
- [x] `attendance_analyzer.py` 入口：解析到 `--tui` 時，切換至 TUI 啟動函式 `launch_tui(prefill)`。

## 3) 模組與目錄結構（保持核心檔名穩定）
- [x] 新增 `tui/` 目錄（不改動 `attendance_analyzer.py` 與 `lib/excel_exporter.py` 檔名）。
- [x] 檔案：`tui/wizard_app.py`（Textual App 空殼）、`tui/i18n.py`（i18n 偵測）、`tui/logging_bridge.py`（Log Handler）、`tui/adapters.py`（進度/取消/截斷）。
- [x] `tui/__init__.py` 導出 `launch_tui()`（驗證可選依賴）。

## 4) 精靈 UX 規格（第一版）
- [x] Step 1 — 歡迎與輸入檔：
- [x] 最近使用清單（讀寫簡單 JSON，沿用或並列 `attendance_state.json`）。
  - [x] 檔案挑選（目錄樹 + 路徑輸入）。
- [x] Step 2 — 選項：輸出格式（excel/csv）、執行模式（`--incremental|--full|--reset-state`）。
- [x] Step 3 — 確認與執行：摘要、開始/取消（進度/日誌後續補）。
- [x] Step 4 — 預覽：僅顯示前 200 行的表格（使用 `truncate_rows`；樣式後續補）。
- [x] Step 5 — 完成：完成訊息（輸出路徑與開啟資料夾後續補）。
- [x] 鍵盤：`Enter` 下一步、`Esc` 上一步、`R` 執行、`C` 取消、`Q` 離開。

## 5) 國際化（預設中文，非中文語系顯示英文）
- [x] 決策：採用 `gettext`（標準庫，無額外依賴），找不到目錄時 fallback 至內建字典/英文字串。
- [x] 準備目錄：`locales/<lang>/LC_MESSAGES/fhr.mo`（`zh_TW`、`en`）— 以 tools/po_to_mo.py 於 CI/本地產生 .mo；.po 已提供。
- [x] 偵測語系：
  - [x] 先讀環境變數 `FHR_LANG`（如 `zh_TW`、`en`）。
  - [x] 否則讀 `locale.getdefaultlocale()` 或 `locale.getlocale()`。
  - [x] 若為 `zh*` 則預設中文；其他皆使用英文。
- [x] UI 字串全部走 `_()`；保留英文為 msgid，zh_TW 為翻譯，確保非中文環境自動顯示英文。
- [x] 在 `README.md` 說明 i18n 與覆寫方法（`FHR_LANG`）。

## 6) 背景執行與進度/取消
- [x] 在 Textual 中以 thread 包裝既有分析流程，避免阻塞 UI（小型資料即時完成）。
- [x] `tui/adapters.py`：提供 `run_analysis_in_thread(args, progress_cb, cancel_event)`（目前直接使用 `run_in_thread`）。
- [x] 在核心邏輯可插入「可選的」`progress_cb(step: str, current: int, total: Optional[int])`；未提供時不影響 CLI 路徑。
- [x] 取消機制：以 `threading.Event`（或旗標）在長迴圈/批次處理處檢查並提前收斂；UI `取消` 時設置事件。

## 7) Logging 導流
- [x] `logging_bridge.py`：自訂 `TextualLogHandler`，將 log 推送至 sink，並同步到 TextLog（含時間/等級）。
- [x] 非 TUI 模式下不改變現有 logging 行為。

## 8) 預覽表格（前 200 行）
- [x] 以 Textual DataTable 呈現，限制 200 行。
- [x] 狀態色彩：以 `row_styles` 類別名彙整（後續可綁定 DataTable 樣式）。
- [x] 來源資料：提供 rows 截斷輔助 `truncate_rows()`。

## 9) 錯誤與無依賴提示
- [x] `--tui` 但未安裝 Textual：
  - [x] 提示：`未安裝 Textual，請執行: pip install .[tui]`（i18n 後續連動）。
- [x] 檔案不存在/格式錯誤：在 Step 1 給出就地錯誤訊息並阻止下一步（副檢查：副檢查副檔名）。

## 10) 文件與示例
- [x] `README.md`：新增 `--tui` 使用方式、Python 版本需求、可選安裝與 i18n 指引。（截圖後續補）
- [x] 在 `sample-attendance-data.txt` 基礎上示範第一次跑 TUI 的流程（README 已包含示例）。

## 11) CI 與品質
- [x] 在 CI 新增一個包含 `[tui]` 的 job（Python 3.8+），但保留原有非 TUI job。
- [x] linters/格式化：新增 Ruff（語法級）與 Black（格式檢查，預設設定）。

## 12) 非目標（第一版不做）
- [ ] 全量虛擬化表格與數十萬列平滑滾動。
- [ ] 可視化假日 API 詳細重試面板（僅於 log 呈現摘要）。
- [ ] 配色客製主題（先用預設亮/暗）。

## 13) 里程碑建議
- [x] M1（1–2 天）：`--tui` 入口、依賴與空殼 App 可啟動。
- [x] M2（2–3 天）：步驟 1/2/3（可執行、可取消、log 映射）。
- [x] M3（2 天）：表格預覽（200 行）、i18n 初版、錯誤提示。
- [x] M4（1 天）：文件、CI、收尾與小修（截圖/主題後續可補）。

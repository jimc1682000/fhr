# 測試與品質保證

## 單元測試
```bash
# 運行完整測試套件（多個測試檔）
python3 -m unittest -q

# 或只跑單一測試檔
python3 -m unittest test.test_attendance_analyzer
```

## 測試特色
- 隔離執行：使用臨時檔案，測試間互不干擾
- 自動清理：測試產生檔案自動刪除
- 真實場景：涵蓋實際使用情況與邊界條件
- 假日 API：請以 mock（`urllib.request.urlopen`）模擬，避免真實網路呼叫

## Coverage（無需安裝 coverage）

- 使用 Makefile 目標生成覆蓋率報告（輸出於 `coverage_report/`）：
```bash
make coverage
```

- 或使用標準庫 trace 手動執行：
```bash
python - << 'PY'
from trace import Trace
import sys, unittest
tr=Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.exec_prefix])
try:
    tr.runfunc(lambda: unittest.main(module=None, argv=['', '-q']))
except SystemExit:
    pass
tr.results().write_results(show_missing=True, summary=True, coverdir='coverage_report')
print('Coverage report written to coverage_report/.')
PY
```

## 手動驗證

### CLI 清理流程
1. 準備一個會產生多份 `_analysis_YYYYMMDD_HHMMSS.*` 備份的 TXT 檔。
2. 執行 `python attendance_analyzer.py <file> csv --export-policy archive` 至少一次，確保建立備份。
3. 再執行 `python attendance_analyzer.py <file> csv --cleanup-exports`，確認終端列出備份清單並詢問是否刪除。
4. 輸入 `n` 應顯示「已取消匯出清理」，檔案保持不動；再次執行並輸入 `y`，檢查備份被刪除且主檔保留（除非同時加上 `--debug`）。

### Web UI 清理預覽
1. 啟動服務：`uvicorn server.main:app --reload`。
2. 於瀏覽器開啟 http://localhost:8000/，上傳 `sample-attendance-data.txt`。
3. 勾選「分析後清理備份」，點擊「預覽要刪除的檔案」，確認 Modal 列出時間戳備份；若開啟 Debug，會額外列出主檔案。
4. 按下「確認清理並分析」後，Modal 關閉並送出分析；若在 Modal 開啟期間手動增減備份，送出時會收到重新預覽提示。
5. 分析結束後，畫面下方的清理狀態會顯示實際結果（成功刪除/略過/需重試）。

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

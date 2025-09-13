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


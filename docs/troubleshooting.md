# 疑難排解（Troubleshooting）

- 看不到 Excel 輸出？請安裝 `openpyxl` 或改用 `csv`：`pip install openpyxl`
- 檔名不符規範導致未啟用增量分析？請使用 `YYYYMM-姓名-出勤資料.txt` 或 `YYYYMM-YYYYMM-姓名-出勤資料.txt`
- 假日載入常失敗？調整重試相關環境變數；若仍失敗系統會回退基本假日以繼續分析


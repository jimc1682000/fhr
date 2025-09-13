# 技術需求

## 必要環境
- Python 3.8+
- 標準庫（sys, datetime, csv, re 等）

## 可選依賴
- `openpyxl`：Excel 格式支援（推薦）

```bash
pip install openpyxl
```

注意：若未安裝 `openpyxl`，系統會自動回退到 CSV 格式。

## TUI（Textual）需求
- Python 3.8+（僅在 3.8 以上支援）
- 需額外安裝 `textual`（之後將以 extras `[tui]` 方式提供）：

```bash
pip install textual
```

啟動方式與參數將在 `--tui` 導入後於 README 中說明。

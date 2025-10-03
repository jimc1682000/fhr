# Textual TUI 螢幕截圖與錄影準備指南

為支援新版 TUI 的截圖與展示素材蒐集，本指南整理推薦工具與操作步驟，協助開發者在開發早期就建立一致的截圖流程。

## 推薦工具

| 目的 | 工具 | 說明 |
| --- | --- | --- |
| 擷取靜態畫面 | [Textual Screenshot](https://textual.textualize.io/guide/screenshots/) | Textual 內建的 `--screenshot` 旗標，可輸出高解析度 PNG。 |
| 擷取靜態畫面（替代方案） | [ttyd](https://github.com/tsl0922/ttyd) + 系統截圖工具 | 適用於需在瀏覽器中操作 TUI 時，以系統熱鍵擷取畫面。 |
| 錄製操作影片 | [asciinema](https://asciinema.org/) | 以文字形式錄製終端互動，可嵌入於 README 或文件。 |
| 錄製操作影片（GIF） | [agg](https://github.com/asciinema/agg) | 將 asciinema 錄影轉換為 GIF，方便嵌入文件。 |

## Textual 內建截圖流程

1. 安裝 Textual 與 textual-forms 相依：
   ```bash
   pip install textual>=0.40 textual-forms
   ```
2. 在開發環境啟動 Textual App 時加上 `--screenshot` 旗標，例如：
   ```bash
   python -m my_tui_app --screenshot build/tui-preview.png
   ```
3. 執行流程至欲截圖的畫面後離開程式，Textual 會將預設大小的畫面輸出為 PNG。
4. 如需高解析度輸出，可搭配 `--screenshot-width` 與 `--screenshot-height` 自行調整。

## 終端錄影建議

1. 以 `asciinema rec build/tui-demo.cast` 開始錄影。
2. 依照預期操作 TUI 介面，展示主要流程（檔案選擇→旗標→執行→結果預覽）。
3. 錄影完成後使用 `ctrl+d` 或輸入 `exit` 結束錄影。
4. 需要 GIF 時，可使用 `agg` 轉換：
   ```bash
   agg build/tui-demo.cast build/tui-demo.gif
   ```

## 版本控管與檔案配置

- 建議將最終輸出置於 `assets/tui/` 目錄，並於 `.gitignore` 中維持忽略原始錄影（例如 `.cast` 與原始 `.mov` 檔）。
- 在 README 或文件中引用時，可使用經過壓縮或重新取樣的圖片/動畫，以降低版本庫大小。
- 若需分享錄影給審查者，可將 `.cast` 檔上傳至 asciinema 平台並提供連結。

## 檢查清單

- [ ] 已安裝 Textual 與 textual-forms。
- [ ] 已能在本機使用 `--screenshot` 旗標輸出 PNG。
- [ ] 已安裝 asciinema 與 agg（視需求）。
- [ ] 已規劃素材的儲存目錄與檔案命名。

完成以上步驟後，即可勾選 `todos/new_tui_tasks.md` 中「預備截圖或錄影工具」的待辦，確保後續 TUI 開發有完整的素材蒐集流程。

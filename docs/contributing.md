# Contributing

- 主要規範：根目錄 `AGENTS.md`（開發流程、測試覆蓋、假日 API 退避/回退策略、Stacked PR）
- AI/自動化工具補充：`CLAUDE.md`（Holiday API Resilience、測試執行、Logging & Privacy）

## Commit 與 PR
- 使用 Conventional Commits；訊息可中英雙語，並於描述加入 `Fixes #<issue>`（或 `Closes #<issue>`）
- PR 需包含：摘要、動機、（如有）輸出格式變更之樣例/截圖、測試重點、風險與回退方案
- 已開啟 PR 的分支避免 force-push；如需整理歷史，開 `-v2` 新分支並在 PR 中註明 supersedes
- Stacked PR：請設定正確 base 分支，保持差異最小、相依清楚


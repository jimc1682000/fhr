# 0000. 以 ADR 記錄架構決策

- Status: Accepted
- Date: 2026-11-19

## Context

本專案的設計取捨原本散落在 PR 描述與 issue 討論裡。repo 改以單一 squash commit 重新建立後，原本的 PR／issue 歷史不再存在，新加入的人（包含 agent）無從得知某段看似奇怪的程式碼為什麼長這樣。

## Decision

- 在 `docs/adr/` 以 Architecture Decision Record（ADR）記錄仍影響現行程式碼、或解釋非顯而易見限制的決策。
- 檔名 `NNNN-kebab-title.md`，依決策發生的時間排序編號；`README.md` 為索引。
- 每份 ADR 包含 `Status`、`Date`，以及 `Context`、`Decision`、`Consequences` 三節，篇幅以一頁內為原則。
- `Date` 取做出該決策的 PR 合併日；沒有 PR 的決策取對應提交的日期。
- 「來源」行只引用原 PR 編號（例如 PR #37）作為歷史線索；舊 repo 刪除後，這些編號無法再連結。
- 決策被取代時不刪除舊 ADR，改把狀態標成 `Superseded by NNNN`。
- ADR 不寫入真實人名、員工資料、內部系統名稱或實際出勤紀錄，需要範例時一律用虛構資料。

## Consequences

- 改動既有決策時，須新增一份 ADR 並更新舊 ADR 的狀態，而不是直接改寫舊內容。
- 純重構、文件或錯字修正不需要 ADR。
- 本批 ADR 是從舊 PR 歷史回推整理，日期與動機以當時 PR 描述為準；PR 未說明的細節不另行推測。

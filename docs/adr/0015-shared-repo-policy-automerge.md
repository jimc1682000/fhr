# 0015. PR 合併自動化採共用 `repo-policy` reusable workflow

- Status: Accepted
- Date: 2026-07-30

## Context

作者的多個個人 repo 都需要同一套 PR 風險分類與自動合併規則。若在各 repo 各寫一份 workflow，規則修正須逐一同步，容易漂移。

## Decision

- `.github/workflows/pr-merge-automation.yml` 只是薄 wrapper，呼叫作者自有 `repo-policy` repo 的 `pr-automerge.yml` reusable workflow。
- `uses` 的版本與 `policy_ref` 一律釘在明確的 tag，並且兩者同步更新；目前釘在 v1.6 tag，與中央排程輪詢使用的版本一致。
- repo 專屬設定放在 `.github/policies/pr-automerge.yml`，與中央預設取聯集；目前只設定受信任的留言者與允許的合併執行者。
- 觸發來源：PR 事件、CI 完成、每半小時排程，以及手動 `workflow_dispatch`。手動執行預設 `dry_run`，只分類不標記、不留言、不合併。
- 以 secret `AUTOMERGE_TOKEN` 執行；check rollup 改由 job 自己的 token 讀取（`checks: read`），因為 fine-grained PAT 無法授予 Checks 權限，在 private repo 會讀不到。rollup 綁定 `headRefOid`，避免兩次查詢之間發生 force-push 時，把別的 commit 的綠燈套到目前 head。

## Consequences

- 規則修正在 `repo-policy` 發新 tag，各 repo 只需提一個改兩行版本號的 PR。
- 不使用浮動的主版本 tag，升級時須閱讀中央 repo 的變更內容。
- 合併判定仰仗外部 repo，該 repo 不可用時本 repo 的自動合併也會停擺；手動合併不受影響。

來源：PR #44、#45、#46、#47、#50

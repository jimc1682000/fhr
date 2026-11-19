# 0017. 送單結果以 Portal 清單對帳為準

- Status: Accepted
- Date: 2026-11-07

## Context

Portal 的表單頁面不會可靠地告訴你送出是否成功。例如非 WFH 請假沒填職務代理人時，Portal 會靜默丟棄該單，頁面停在「新增」狀態，而頁面上的停用元件被舊的頁面快照判斷當成成功。結果 `portal-apply` 回報「已送出」，實際上 Portal 上沒有單；同時段已有別的假別、已核准或已抽回的單，以及短假別名對應全名（`事假` 對應到含括號說明的全名）時，也會出現假成功或重複送單。

## Decision

- 一張單只有在 Portal「全部」清單中以可辨識的有效狀態出現，才算送出。
- 每筆流程：
  1. 前置檢查：非 WFH 請假缺 `--proxy` 時整批先以 exit 2 結束，不送任何單。
  2. 預查：先解析唯一的假別全名，再查清單比對起訖日期、時段與假別全名；已有有效單就標 `already_pending`，不重送。抽單或駁回視為不存在；狀態無法判斷或清單無法解析時標 `failed`，不送。
  3. 送出後對帳：清單上找到才標 `confirmed`，否則標 `unconfirmed`。送出途中逾時或發生錯誤也先對帳，再以 exit 5 結束。
- 任一筆不在 `confirmed`／`already_pending`／`dry_run` 時，`portal-apply` 以 exit 5 結束。
- 同一使用者的本機 `portal-apply` 與 `portal-check` 以 `flock` 共用一把鎖，取不到鎖就在接觸 Portal 前以 exit 5 結束。
- 結果檔帶 `run_id` 與 `completed`，以同目錄暫存檔加 rename 原子寫入。
- Claude Code 的 post-tool hook 只回傳固定的判讀與對帳提醒，不自動讀檔或重查。

## Consequences

- 流程只會更保守：無法確認時不送，不會多送。代價是遇到 `unconfirmed` 時須人工到 Portal 確認後再決定是否重送。
- 鎖只涵蓋同一台機器、同一作業系統使用者，不協調其他機器或手動送單。
- 呼叫端若把非 0 一律當失敗，新增的 exit code 不影響其行為。

來源：PR #49

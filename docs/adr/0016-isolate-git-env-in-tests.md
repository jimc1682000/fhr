# 0016. 測試建立 Git fixture 時清除所有 `GIT_*` 環境變數

- Status: Accepted
- Date: 2026-11-06

## Context

在 linked worktree 裡提交時，pre-commit 會在已設定 `GIT_DIR=<主 repo>/.git/worktrees/<wt>` 的環境下跑完整 unittest（見 0010）。`test/test_reasons.py` 建 fixture repo 時繼承了這個環境，git 指令因此寫進主 repo，把主 repo 設成 `core.bare=true`，還多出 fixture commit。

## Decision

- `test/test_reasons.py` 提供 `_git_env()`：複製 `os.environ` 並移除所有 `GIT_*` 變數；建立 fixture 的每個 `subprocess.run` 都使用這個環境。
- 會呼叫被測的 `lib/reasons.py`（它也會繼承環境）的測試類別，在 `setUp` 清掉 `GIT_*`。
- 新增哨兵測試：用真正的 linked worktree 重現原事故，確認主 repo 的 `core.bare`、refs 與 commit 數都不變；另有測試保護 `setUp` 的隔離本身。

## Consequences

- 任何會在測試中執行 `git` 的新測試，都須沿用 `_git_env()` 或同等隔離，否則在 worktree 提交時可能汙染外層 repo。
- 修正只動測試檔，正式程式碼未改。
- 驗證方式：外層同時設 `GIT_DIR` 與 `GIT_INDEX_FILE` 跑完整測試；修正版全部通過，撤回修正時外層 repo 會被改成 bare。

來源：PR #48

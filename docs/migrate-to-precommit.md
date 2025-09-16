# 遷移到 Pre-commit 框架指南

## 背景

本項目已從傳統的 Git hooks 遷移到 [pre-commit](https://pre-commit.com/) 框架，以提供更好的開發體驗和標準化管理。

## 快速遷移步驟

### 1. 清理舊的 hooks（如果有）

```bash
# 備份現有的 pre-commit hook（可選）
cp .git/hooks/pre-commit .git/hooks/pre-commit.backup 2>/dev/null || true

# 移除舊的 hook
rm -f .git/hooks/pre-commit
```

### 2. 安裝 pre-commit 框架

```bash
# 安裝 pre-commit
pip install pre-commit

# 安裝開發依賴（如果還沒安裝）
pip install -r requirements-dev.txt
```

### 3. 安裝新的 hooks

```bash
# 使用新的方式安裝 hooks
make install-hooks

# 或者直接使用 pre-commit
pre-commit install
```

### 4. 測試新的設置

```bash
# 運行所有 hooks 測試
pre-commit run --all-files

# 或使用 make 命令
make pre-commit-run
```

## 主要變化

### 配置文件
- **舊方式**: `hooks/pre-commit` shell script
- **新方式**: `.pre-commit-config.yaml` YAML 配置

### 安裝方式
- **舊方式**: `make install-hooks` 複製 shell script
- **新方式**: `pre-commit install` 自動安裝 hooks

### Hook 內容
- **舊方式**: 
  - black 格式化
  - ruff linting
  - 單元測試運行
- **新方式**:
  - black 格式化（行長度 100）
  - ruff linting + 自動修復
  - 檔案檢查（空白、YAML、大文件等）
  - mypy 類型檢查（可選）
  - **移除了單元測試**（只在 CI 中運行）

## 新增的功能

1. **自動修復**: ruff 現在會自動修復可修復的問題
2. **檔案檢查**: 自動檢查和修復常見檔案問題
3. **版本管理**: 每個 tool 都有明確的版本號
4. **更新機制**: `pre-commit autoupdate` 自動更新工具版本

## 常見問題

### Q: 為什麼移除了單元測試？
A: 單元測試現在只在 CI 中運行，提高了本地開發的速度。覆蓋率要求也從 100% 降低到 90%。

### Q: 如何跳過 hooks？
A: 使用 `git commit --no-verify`，但不推薦這樣做。

### Q: Hook 失敗怎麼辦？
A: 大部分格式問題會自動修復，修復後重新 `git add` 和 `git commit` 即可。

### Q: 如何更新 hooks？
A: 運行 `make pre-commit-update` 或 `pre-commit autoupdate`。

## 回退方案

如果需要回到舊的方式（不推薦）：

```bash
# 1. 移除 pre-commit hooks
pre-commit uninstall

# 2. 恢復備份的 hook（如果有）
cp .git/hooks/pre-commit.backup .git/hooks/pre-commit 2>/dev/null || true

# 3. 或者重新創建舊版本的 hook
git checkout HEAD~1 -- hooks/
make install-hooks
```

## 需要幫助？

- 查看 [`docs/pre-commit-setup.md`](pre-commit-setup.md) 了解詳細設置
- 查看 [Pre-commit 官方文檔](https://pre-commit.com/)
- 聯繫項目維護者

---

**註**: 此遷移是為了改善開發體驗和標準化工具鏈。新的方式更加靈活且易於維護。
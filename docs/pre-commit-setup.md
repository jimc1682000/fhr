# Pre-commit 框架設置指南

本項目使用 [pre-commit](https://pre-commit.com/) 框架來管理 Git hooks，確保代碼質量和一致性。

## 為什麼使用 pre-commit 框架？

與傳統的 Git hooks 相比，pre-commit 框架提供：

- **標準化配置**: 使用 `.pre-commit-config.yaml` 統一管理所有 hooks
- **自動化安裝**: 一鍵安裝所有必要的工具和 hooks
- **豐富生態**: 大量現成的 hooks 可直接使用
- **版本管理**: 每個 hook 都有明確的版本，確保團隊一致性
- **跨平台**: 在不同操作系統上行為一致

## 安裝和設置

### 1. 安裝 pre-commit

```bash
# 使用 pip 安裝
pip install pre-commit

# 或使用 Homebrew (macOS)
brew install pre-commit

# 驗證安裝
pre-commit --version
```

### 2. 安裝項目的 pre-commit hooks

```bash
# 在項目根目錄執行
pre-commit install

# 這會將 hooks 安裝到 .git/hooks/ 目錄
```

### 3. 手動運行所有 hooks（可選）

```bash
# 對所有文件運行 hooks
pre-commit run --all-files

# 只對暫存的文件運行 hooks
pre-commit run
```

## 配置說明

我們的 `.pre-commit-config.yaml` 包含以下 hooks：

### 代碼格式化
- **black**: Python 代碼自動格式化，行長度限制 100 字符
- **ruff**: Python linting 和自動修復

### 通用檢查
- **trailing-whitespace**: 移除行尾空白字符
- **end-of-file-fixer**: 確保文件以換行符結尾
- **check-yaml**: 檢查 YAML 文件語法
- **check-added-large-files**: 防止提交大文件（>1MB）
- **check-merge-conflict**: 檢查合併衝突標記

### 類型檢查（可選）
- **mypy**: Python 靜態類型檢查（僅在 mypy 可用時運行）

## 使用流程

### 正常開發流程

1. **修改代碼**
2. **git add** 暫存修改
3. **git commit** - pre-commit hooks 自動運行
4. 如果 hooks 失敗，修復問題後重新提交

### Hooks 失敗時的處理

```bash
# 如果 hooks 修復了代碼（如 black 格式化）
# 需要重新暫存修改的文件
git add .
git commit

# 如果需要跳過 hooks（不推薦）
git commit --no-verify
```

## 常見使用場景

### 只運行特定 hook

```bash
# 只運行 black
pre-commit run black

# 只運行 ruff
pre-commit run ruff

# 列出所有可用的 hook
pre-commit run --help
```

### 更新 hooks 到最新版本

```bash
# 更新所有 hooks
pre-commit autoupdate

# 手動更新後重新安裝
pre-commit install
```

### 臨時禁用某個 hook

在 `.pre-commit-config.yaml` 中添加 `stages: [manual]`：

```yaml
- id: mypy
  stages: [manual]  # 只在手動運行時執行
```

## CI/CD 集成

pre-commit 也可以在 CI 中運行：

```yaml
# .github/workflows/ci.yml 示例
- name: Run pre-commit
  uses: pre-commit/action@v3.0.1
```

我們目前的 CI 配置分別運行 linting 和測試，但也可以考慮統一使用 pre-commit。

## 故障排除

### Hook 安裝失敗

```bash
# 清理並重新安裝
pre-commit clean
pre-commit install
```

### Python 環境問題

```bash
# 確保使用正確的 Python 環境
which python3
pre-commit install --install-hooks
```

### 跳過特定文件

在 `.pre-commit-config.yaml` 中使用 `exclude` 參數：

```yaml
- id: black
  exclude: ^(migrations/|legacy_code/)
```

## 團隊協作建議

1. **新成員入職**: 確保在開發環境設置文檔中包含 pre-commit 安裝步驟
2. **版本更新**: 定期運行 `pre-commit autoupdate` 並提交更新
3. **自定義 hooks**: 如需項目特定的檢查，使用 `repo: local` 配置
4. **文檔同步**: 配置變更時更新此文檔

## 與傳統 Git Hooks 的遷移

如果之前使用傳統 Git hooks：

1. **備份現有 hooks**:
   ```bash
   cp .git/hooks/pre-commit .git/hooks/pre-commit.backup
   ```

2. **安裝 pre-commit**:
   ```bash
   pre-commit install
   ```

3. **移除項目中的 hooks 目錄**（如果有）:
   ```bash
   rm -rf hooks/
   ```

4. **更新開發文檔**，移除手動安裝 hooks 的說明

## 相關資源

- [Pre-commit 官方文檔](https://pre-commit.com/)
- [Pre-commit Hooks 倉庫](https://github.com/pre-commit/pre-commit-hooks)
- [Black 文檔](https://black.readthedocs.io/)
- [Ruff 文檔](https://docs.astral.sh/ruff/)

---

**注意**: 如果您遇到任何問題，請查看項目的 `CLAUDE.md` 或聯繫維護者。
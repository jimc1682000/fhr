# Release Workflow & Changelog Management

本專案使用 **git-cliff** 與 **commitizen** 進行自動化版本管理與 CHANGELOG 生成。

## 📋 前置需求

### 安裝工具

```bash
# macOS (Homebrew)
brew install git-cliff go-task

# Python 套件（已包含在 requirements-dev.txt）
pip install commitizen
```

### 初始化設定

```bash
# 安裝開發依賴
pip install -r requirements-dev.txt

# 安裝 pre-commit hooks（包含 commitizen 檢查）
pre-commit install
pre-commit install --hook-type commit-msg
```

## 🎯 日常開發流程

### 1. 使用 Commitizen 提交變更

系統已配置 pre-commit hook，所有 commit message 都會自動經過格式驗證：

```bash
# 互動式提交（推薦）
cz commit

# 或使用簡短別名
cz c
```

Commitizen 會引導你選擇：
- **Type**: feat, fix, docs, refactor, test, chore 等
- **Scope**: 影響範圍（可選）
- **Message**: 簡短描述
- **Body**: 詳細說明（可選）
- **Footer**: Breaking changes 或關閉 issue（可選）

### 2. Commit Message 格式規範

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 規範：

```
<type>(<scope>): <subject>

<body>

<footer>
```

**常用 Type**：
- `feat`: 新功能
- `fix`: Bug 修復
- `docs`: 文件變更
- `refactor`: 代碼重構
- `test`: 測試相關
- `chore`: 建置流程或輔助工具變更
- `perf`: 性能優化
- `ci`: CI/CD 配置

**範例**：
```bash
feat(analyzer): add support for cross-month data analysis
fix(export): resolve CSV encoding issue on Windows
docs(readme): update installation instructions
refactor(lib): extract state manager into separate module
```

### 3. 如果忘記使用 Commitizen

Pre-commit hook 會檢查 commit message 格式。若格式不符，會被拒絕提交並顯示錯誤訊息。

**修正方式**：
```bash
# 修改最後一次 commit message
git commit --amend

# 然後使用符合規範的格式重新撰寫
```

## 📊 Changelog 管理

### 預覽未發布的變更

```bash
# 使用 Taskfile（推薦）
task changelog-preview

# 或直接使用 git-cliff
git-cliff --unreleased
```

### 手動更新 CHANGELOG

```bash
# 更新 CHANGELOG.md（加入未發布的變更）
task changelog-update

# 重新生成完整 CHANGELOG
task changelog-full
```

## 🚀 版本發布流程

### 方式一：使用 Commitizen（推薦）

Commitizen 會自動：
1. 分析 commit 歷史
2. 決定版本號（根據 Semantic Versioning）
3. 更新 `pyproject.toml` 版本號
4. 生成/更新 `CHANGELOG.md`
5. 創建 git tag
6. 創建 release commit

```bash
# 互動式版本升級（自動判斷 patch/minor/major）
task bump

# 或明確指定版本類型
task bump-patch   # 1.0.X -> 1.0.(X+1)
task bump-minor   # 1.X.0 -> 1.(X+1).0
task bump-major   # X.0.0 -> (X+1).0.0
```

**發布後別忘記推送**：
```bash
git push --follow-tags
```

### 方式二：手動流程（不推薦）

如果需要更細緻的控制：

```bash
# 1. 確保在主分支且工作目錄乾淨
git checkout main
git pull

# 2. 生成 CHANGELOG
git-cliff --tag v1.2.0 --prepend CHANGELOG.md

# 3. 提交 CHANGELOG
git add CHANGELOG.md
git commit -m "chore(release): prepare for v1.2.0"

# 4. 創建標籤
git tag -a v1.2.0 -m "Release v1.2.0"

# 5. 推送
git push origin main
git push origin v1.2.0
```

## 🛠️ Taskfile 可用任務

查看所有可用任務：
```bash
task help
# 或
task --list
```

**主要任務**：

### 開發任務
- `task test` - 執行單元測試
- `task test-coverage` - 產生覆蓋率報告
- `task lint` - 執行 linting 檢查
- `task format` - 自動格式化程式碼

### Changelog 任務
- `task changelog-preview` - 預覽未發布變更
- `task changelog-update` - 更新 CHANGELOG.md
- `task changelog-full` - 重新生成完整 CHANGELOG

### 版本發布任務
- `task bump` - 互動式版本升級
- `task bump-patch` - Patch 版本升級
- `task bump-minor` - Minor 版本升級
- `task bump-major` - Major 版本升級

### 其他任務
- `task server` - 啟動開發伺服器
- `task tui` - 啟動 TUI 介面
- `task clean` - 清理暫存檔案

## 📝 配置檔案說明

### cliff.toml
Git-cliff 配置檔，定義：
- Changelog 格式與模板
- Commit 分類規則
- Tag 模式匹配
- GitHub 專案資訊

### pyproject.toml
包含 commitizen 配置：
- 版本號位置
- Changelog 檔案路徑
- Tag 格式
- Bump message 格式

### .pre-commit-config.yaml
Pre-commit hooks 配置，包含：
- Ruff format (格式化)
- Ruff (linting)
- Commitizen (commit message 驗證)

## 🔧 故障排除

### Commitizen 驗證失敗

```bash
# 檢查最後一次 commit message 格式
cz check --commit-msg-file .git/COMMIT_EDITMSG

# 查看範例格式
cz example
```

### Pre-commit hook 問題

```bash
# 重新安裝 hooks
pre-commit uninstall
pre-commit install
pre-commit install --hook-type commit-msg

# 測試 hooks
pre-commit run --all-files
```

### 強制略過驗證（不建議）

```bash
# 略過所有 hooks（僅緊急情況使用）
git commit --no-verify -m "emergency fix"
```

## 📚 延伸閱讀

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)
- [git-cliff Documentation](https://git-cliff.org/)
- [Commitizen Documentation](https://commitizen-tools.github.io/commitizen/)
- [go-task Documentation](https://taskfile.dev/)

## 🎓 最佳實踐

1. **頻繁提交**：保持小而專注的 commits
2. **遵循規範**：使用 `cz commit` 確保格式正確
3. **撰寫清晰**：讓他人能快速理解變更內容
4. **定期發布**：累積足夠功能後即發布新版本
5. **維護 CHANGELOG**：確保每次發布都更新 CHANGELOG

---

**Note**: 本專案已配置自動化工具，建議遵循上述流程以確保版本管理的一致性與可追溯性。

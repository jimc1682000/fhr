# 0014. 以 pip 套件與多架構容器發佈，Portal 自動化不進 image

- Status: Accepted
- Date: 2026-07-30

## Context

原本的發佈載體只有 Windows 專用的 PyInstaller `.exe`。專案另有 FastAPI Web 服務（`server/` 與 `web/` 靜態前端），需要可自架的部署方式。Portal 自動化則必須在有 headed 瀏覽器、能連內網的桌面上執行（見 0009）。

## Decision

- 以 `pyproject.toml` 的 `[project]` 定義套件，console script `fhr = lib.cli:run`，可用 `uvx`、`pipx` 或 `pip install .` 安裝；`[service]` extra 帶入 Web 相依。
- `[project].version` 為版本單一真相，commitizen 設 `version_provider = pep621`，tag 格式 `v$version`。
- wheel 以 `only-include` 收錄 `attendance_analyzer.py`、`lib`、`server`、`web`。`attendance_analyzer.py` 是核心模組（見 0002），`web/` 是 pip 安裝時掛載 `/` 的前端資源，兩者都不可遺漏。
- 單一容器 image 由 `docker-entrypoint.sh` 分流：預設 `CMD=["web"]` 啟動 uvicorn，`analyze` 等子命令走 `fhr` CLI。
- push `v*` tag 時，CI 以 buildx 建 `linux/amd64` 與 `linux/arm64` image 並推到 GHCR。
- `portal-*` 子命令不支援在 image 內執行，image 不含 `agent-browser` 與瀏覽器，一律原生安裝。另以 CDP 連 host 瀏覽器作為選配做法，不列入支援範圍。
- `.dockerignore` 排除 `.env` 與員工出勤資料檔，避免公開 image 夾帶個資或內部設定。

## Consequences

- CLI、Web 共用一份程式碼與一個 image；Portal 自動化與容器部署的邊界寫進 `docs/packaging.md`。
- 新增頂層模組或資源目錄時，須同步更新 `only-include`，否則安裝後會缺檔。
- GHCR 首次發佈預設為 private，須手動設為 public 並連結 repo。

來源：PR #31、#40

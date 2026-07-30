# 打包與發佈（Packaging & distribution）

本專案有三種「使用形態」,對應不同的打包載體。核心原則:**沿功能本質切,而不是硬塞進單一載體**。

| 形態 | 載體 | 適合 |
|------|------|------|
| CLI(`analyze` / `export` / `import` / `reasons`) | pip 套件(`fhr` 命令)或容器 | 有 Python 的人、自架、CI |
| Web 服務 | 容器(GHCR 多架構 image)或 `pip install .[service]` | Ops / 自架部署 |
| Portal 自動化(`portal-*`) | **原生安裝(`uvx`/`pipx`)** | 桌面端,需 headed 瀏覽器 + 內網 |

## 為什麼 Portal 不進容器

`portal-*` 子命令透過 [`agent-browser`](https://github.com/vercel-labs/agent-browser) 驅動瀏覽器,本質是**桌面互動行為**:

- `ensure_login()` 會開**有畫面的 Chromium**,等使用者**親手輸入密碼**(程式從不碰 credential)。
- Portal 在**公司內網**(例如 `http://192.168.x.x/...`)。
- agent-browser 跑常駐 daemon、dry-run 還會截圖供人工確認。

把這些塞進容器需要 X11/VNC 轉發 + host networking 連內網 + session volume,成本高、價值負。因此 Portal 的「正規打包」是**原生安裝到桌面**,那裡瀏覽器、Node、內網本來就都在。

## 安裝 CLI(含 Portal)

```bash
# 一次性執行(不落地安裝),直接從原始碼樹:
uvx --from . fhr analyze 202508-Name-出勤資料.txt

# 或從 git 直接跑:
uvx --from git+https://github.com/jimc1682000/fhr fhr analyze ...

# 常駐安裝成使用者工具:
pipx install .            # 或 pipx install git+https://github.com/jimc1682000/fhr
fhr --help
```

Portal 另需 agent-browser(僅 `portal-*` 用得到):

```bash
npm install -g agent-browser
agent-browser install
```

> `config.json`(公司規則覆寫)為**選配**,程式從**當前工作目錄**讀取;找不到就用內建預設值。要客製就在你執行命令的目錄放一份。

## 容器 image(CLI + Web 共用一個 image)

CI 在 push `v*` tag 時,用 `docker buildx` 建 **`linux/amd64` + `linux/arm64`** 並推到 GHCR(見 `.github/workflows/release-image.yml`)。
也可從 GitHub Actions 手動執行同一個 workflow,並在必填的 `tag` input 指定 image tag(例如 `v1.1.0-rc.1`)。

```bash
docker pull ghcr.io/jimc1682000/fhr:latest
```

> **首次發佈後需手動設定可見性**:CI 用 `GITHUB_TOKEN` 第一次推上去的 GHCR package **預設是 private**,且未自動 link 到 repo。要讓他人(或未登入的機器)能匿名 `docker pull`,需到 GitHub → Packages → 該套件 → Package settings 改成 **Public** 並 link 到本 repo。否則 pull 會 auth 失敗。

同一個 image 由 `docker-entrypoint.sh` 分流(預設 `CMD=["web"]`):

```bash
# Web 服務(預設,無參數)
docker run -p 8000:8000 ghcr.io/jimc1682000/fhr:latest
#   → http://localhost:8000

# CLI:把待分析檔所在目錄掛進 /data
docker run --rm -v "$PWD:/data" -w /data \
  ghcr.io/jimc1682000/fhr:latest analyze 202508-Name-出勤資料.txt

# 任意命令(debug)
docker run --rm ghcr.io/jimc1682000/fhr:latest fhr --help
docker run --rm -it ghcr.io/jimc1682000/fhr:latest sh
```

`docker compose up` 仍維持本機 build 啟 Web;要改用已發佈 image,註解掉 compose 的 `build:` 後 `docker compose pull`。

> 容器內**不含** agent-browser/瀏覽器,`portal-*` 在 image 裡不支援(刻意為之,見上)。

## 進階(選配):容器內 Portal 接 host 瀏覽器(`--cdp`)

若真的想在容器世界跑 Portal,可讓容器內的 agent-browser 透過 CDP 連到**你在 host 開的瀏覽器**(在那邊登入、那邊連內網):

```bash
# host 端啟動帶遠端除錯埠的 Chrome,手動登入 Portal:
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222

# 容器內把 agent-browser 指向 host(經 host.docker.internal),AGENT_BROWSER_BIN
# 加上 --cdp;容器需能連到 host 與內網。
```

此路為 power-user 選配,有已知粗糙處(macOS 新版 Chrome 的 `--cdp` attach 可能卡死,見 agent-browser issue #1193),**不是預設支援**。一般情況請走原生安裝。

## 版本號

`[project].version` 為**單一真相**(PEP 621);commitizen 設 `version_provider = "pep621"`,`cz bump` 直接更新它,tag 格式 `v$version`,觸發上面的 image 發佈。

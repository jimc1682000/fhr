# 疑難排解（Troubleshooting）

## 🔍 診斷工具

### 健康檢查
```bash
# 快速系統檢查
python -c "import sys; print(f'Python {sys.version}')"
python -c "import openpyxl; print('openpyxl OK')" 2>/dev/null || echo "⚠️ openpyxl not installed"
python attendance_analyzer.py --help | head -5

# Web 服務健康檢查
curl -s http://localhost:8000/api/health | jq || echo "Web service not running"
```

### 檔案格式驗證
```bash
# 檢查檔案格式
head -3 your-file.txt  # 檢查前三行
file your-file.txt     # 檢查檔案類型
wc -l your-file.txt    # 檢查行數

# 檢查分隔符（應為 tab）
cat -A your-file.txt | head -2  # 顯示隱藏字符，^I 表示 tab
```

### 檔名格式檢查
```bash
# 檢查增量分析檔名格式
echo "your-file.txt" | grep -E '202[0-9]{3}-.*-出勤資料\.txt'
# 有輸出表示格式正確

# 檢查跨月格式
echo "your-file.txt" | grep -E '202[0-9]{3}-202[0-9]{3}-.*-出勤資料\.txt'
```

## ⚠️ 常見錯誤與解決方案

### Excel 輸出問題
**症狀**: 看不到 .xlsx 檔案，只有 .csv 檔案
**診斷**:
```bash
python -c "import openpyxl; print('openpyxl available')" 2>/dev/null || echo "openpyxl missing"
ls -la *analysis* | grep -E '\.(xlsx|csv)$'
```
**解決方案**:
1. 安裝 openpyxl: `pip install openpyxl`
2. 檢查是否生成 CSV 作為備選方案
3. 確認目錄寫入權限: `ls -la . | head -3`

### 增量分析未啟用
**症狀**: 看到 "無法從檔名識別使用者，將使用完整分析模式"
**診斷**:
```bash
# 檢查檔名是否符合格式
basename="your-file.txt"  # 替換成實際檔名
if echo "$basename" | grep -qE '202[0-9]{3}-.*-出勤資料\.txt'; then
    echo "✅ 檔名格式正確"
else
    echo "❌ 檔名格式不正確"
fi
```
**解決方案**: 
- 確保檔名格式為 `YYYYMM-姓名-出勤資料.txt`
- 例如: `202508-王小明-出勤資料.txt`
- 跨月格式: `202508-202509-王小明-出勤資料.txt`

### 假日載入失敗
**症狀**: 看到 "無法取得假日資料" 或 "回退到基本假日" 警告
**診斷**:
```bash
# 檢查網路連線
ping -c 3 data.gov.tw
curl -I https://data.gov.tw/api/v1/rest/datastore_search 2>/dev/null | head -1

# 檢查環境變數設定
env | grep HOLIDAY_API
```
**解決方案**:
1. 檢查網路連線: `ping data.gov.tw`
2. 調整重試參數:
   ```bash
   export HOLIDAY_API_MAX_RETRIES=5
   export HOLIDAY_API_BACKOFF_BASE=1.0
   ```
3. **重要**: 系統會自動使用基本假日，不影響核心分析功能

### 記憶體不足問題
**症狀**: 處理大檔案時程式當機或回應極慢
**診斷**:
```bash
# 檢查檔案大小
ls -lh your-file.txt

# 檢查可用記憶體
free -h 2>/dev/null || vm_stat | head -5  # Linux 或 macOS

# 監控記憶體使用
python -c "
import psutil, os
process = psutil.Process(os.getpid())
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.1f}MB')
"
```
**解決方案**:
1. 分割大檔案: `split -l 5000 large-file.txt part-`
2. 關閉其他程式釋放記憶體
3. 使用 CSV 格式減少記憶體需求: `python attendance_analyzer.py file.txt csv`
4. 考慮增加系統記憶體

### Web 服務問題
**症狀**: 無法啟動 Web 服務或無法存取
**診斷**:
```bash
# 檢查相依套件
python -c "import fastapi, uvicorn; print('FastAPI components OK')"

# 檢查埠號占用
lsof -i :8000 2>/dev/null || netstat -an | grep :8000

# 檢查 Docker 狀態
docker ps | grep fhr
```
**解決方案**:
1. 安裝 Web 服務依賴: `pip install -r requirements-service.txt`
2. 更換埠號: `uvicorn server.main:app --port 8080`
3. 檢查防火牆設定
4. 查看 Docker 日誌: `docker logs fhr`

## 🔧 進階診斷

### 效能分析
```bash
# 分析處理時間
time python attendance_analyzer.py large-file.txt

# 詳細效能分析（需要 cProfile）
python -m cProfile -o profile.stats attendance_analyzer.py file.txt
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative'); p.print_stats(20)"
```

### 詳細日誌分析
```bash
# 啟用詳細日誌
export PYTHONPATH=.
python -c "
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')
" attendance_analyzer.py your-file.txt

# 分析特定錯誤
python attendance_analyzer.py file.txt 2>&1 | grep -i error
```

### Docker 容器診斷
```bash
# 檢查容器狀態
docker ps -a | grep fhr

# 檢視容器日誌
docker logs fhr --tail 50

# 進入容器除錯
docker exec -it fhr /bin/bash

# 檢查容器資源使用
docker stats fhr --no-stream
```

## 📞 取得協助

### 自助診斷順序
1. **檢查基本設定**: Python 版本、依賴套件、檔案格式
2. **查看範例**: `python attendance_analyzer.py sample-attendance-data.txt`
3. **閱讀相關文件**: [quick-reference.md](quick-reference.md) 或 [usage.md](usage.md)
4. **搜尋類似問題**: 在 GitHub Issues 中搜尋錯誤訊息

### 回報問題時請提供
- 完整錯誤訊息
- Python 版本: `python --version`
- 作業系統資訊
- 檔案大小和格式（去除個人資訊）
- 使用的命令

### 社群支援
1. **GitHub Issues**: 回報 bug 或功能請求
2. **文件改進**: 參考 [contributing.md](contributing.md)
3. **討論區**: GitHub Discussions 一般討論

## 🚨 緊急情況處理

### 資料遺失風險
- ✅ **系統自動備份**: 檔名格式 `*_YYYYMMDD_HHMMSS.*`
- ✅ **檢查備份**: `ls -la *_202[0-9]* | head -10`
- ✅ **恢復備份**: 重新命名最新備份檔案移除時間戳

### 系統無回應
1. **檢查系統資源**: `top` 或 `htop` 查看 CPU/記憶體
2. **檢查磁碟空間**: `df -h`
3. **檢查進程**: `ps aux | grep python | grep attendance`
4. **強制終止**: `pkill -f attendance_analyzer`
5. **清理暫存**: 刪除 `*.tmp` 和部分處理檔案後重試

### Web 服務無法存取
1. **檢查服務狀態**: `curl localhost:8000/api/health`
2. **重啟服務**: `docker restart fhr` 或重新啟動 uvicorn
3. **檢查網路**: `netstat -tulpn | grep 8000`
4. **查看錯誤日誌**: 檢查 Docker 或應用程式日誌

---

💡 **小提示**: 大多數問題都可以透過檢查檔案格式、網路連線和系統資源來解決。系統設計具有容錯能力，即使部分功能失敗（如假日載入），核心分析功能仍能正常運作。


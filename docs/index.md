# FHR 文件導航中心

> 考勤分析系統完整文件索引 - 從入門到企業級部署

## 🎯 快速導航

| 我想要... | 推薦文件 | 預計時間 |
|-----------|----------|----------|
| **快速開始使用** | [README.md](../README.md) → [usage.md](usage.md) | 5 分鐘 |
| **部署到生產環境** | [service.md](service.md) → [environment.md](environment.md) | 30 分鐘 |
| **客製化設定** | [overview.md](overview.md) → [logic.md](logic.md) | 15 分鐘 |
| **開發或貢獻程式碼** | [architecture.md](architecture.md) → [contributing.md](contributing.md) | 1 小時 |
| **解決問題** | [troubleshooting.md](troubleshooting.md) → [quick-reference.md](quick-reference.md) | 10 分鐘 |

## 📚 分層文件架構

### 🚀 **使用者文件** - 適合日常使用者
- **[README.md](../README.md)** - 專案主頁與快速開始
- **[usage.md](usage.md)** - 詳細使用指南
- **[data-format.md](data-format.md)** - 檔案格式需求
- **[output.md](output.md)** - 輸出格式說明與範例
- **[incremental.md](incremental.md)** - 增量分析功能詳解
- **[troubleshooting.md](troubleshooting.md)** - 疑難排解指南
- **[quick-reference.md](quick-reference.md)** - 命令速查與快速參考

### 🏗️ **運維文件** - 適合系統管理員
- **[service.md](service.md)** - Web 服務部署與管理
- **[requirements.md](requirements.md)** - 系統需求與依賴
- **[environment.md](environment.md)** - 環境變數與假日 API 設定
- **[project-structure.md](project-structure.md)** - 專案檔案結構

### 🔧 **開發者文件** - 適合開發人員
- **[architecture.md](architecture.md)** - 系統架構設計
- **[logic.md](logic.md)** - 業務邏輯與計算規則
- **[testing.md](testing.md)** - 測試框架與覆蓋率
- **[contributing.md](contributing.md)** - 貢獻指南與開發流程

### 🏢 **企業文件** - 適合企業部署
- **[overview.md](overview.md)** - 系統概覽與企業級功能
- **[api-architecture.md](api-architecture.md)** - API 架構與端點設計
- **[service-architecture.md](service-architecture.md)** - 服務架構與微服務模式
- **[enterprise-integration.md](enterprise-integration.md)** - 企業系統整合指南
- **[compliance-audit.md](compliance-audit.md)** - 合規性與稽核框架
- *(規劃中)* **security.md** - 安全性與合規指南
- *(規劃中)* **deployment.md** - 企業級部署架構
- *(規劃中)* **monitoring.md** - 監控與日誌管理

### 🔬 **進階架構文件** - 適合架構師與技術主管
- **[testing-architecture.md](testing-architecture.md)** - 進階測試架構策略
- **[documentation-automation.md](documentation-automation.md)** - 文件自動化流程

## 🎯 常用情境快速入口

### 📋 **第一次使用**
1. 閱讀 [README.md](../README.md) 了解基本功能
2. 查看 [requirements.md](requirements.md) 確認系統需求
3. 按照 [usage.md](usage.md) 完成第一次分析
4. 遇到問題查閱 [troubleshooting.md](troubleshooting.md)

### 🌐 **部署 Web 服務**
1. 查看 [service.md](service.md) 了解 Web 服務架構
2. 確認 [environment.md](environment.md) 環境設定
3. 使用 Docker 或直接部署
4. 查閱 [troubleshooting.md](troubleshooting.md) 解決部署問題

### 🔧 **客製化開發**
1. 理解 [architecture.md](architecture.md) 系統架構
2. 研讀 [logic.md](logic.md) 業務規則
3. 參考 [contributing.md](contributing.md) 開發流程
4. 運行 [testing.md](testing.md) 中的測試確保品質

### ⚡ **快速查詢**
- **命令速查**: [quick-reference.md](quick-reference.md)
- **錯誤排除**: [troubleshooting.md](troubleshooting.md)
- **檔案格式**: [data-format.md](data-format.md)
- **輸出說明**: [output.md](output.md)

## 📊 文件完成度

| 類別 | 完成度 | 狀態 |
|------|--------|------|
| **基礎使用** | 100% | ✅ 完整 |
| **系統架構** | 95% | ✅ 完整 |
| **開發指南** | 90% | ✅ 完整 |
| **運維部署** | 80% | 🚧 持續改進 |
| **企業功能** | 85% | ✅ 近乎完整 |
| **進階架構** | 80% | ✅ 完整 |
| **安全合規** | 50% | 🚧 持續建立 |

## 🆘 需要協助？

### 📞 **取得支援**
1. **文件問題**: 檢查對應的 `.md` 檔案是否有更新
2. **功能問題**: 查閱 [troubleshooting.md](troubleshooting.md) 常見問題
3. **技術問題**: 參考 [architecture.md](architecture.md) 與 [logic.md](logic.md)
4. **回報問題**: 遵循 [contributing.md](contributing.md) 建立 Issue

### 🔍 **搜尋技巧**
- 使用 `Ctrl+F` 在文件中搜尋關鍵字
- 檔案名稱通常反映內容主題
- 查看文件開頭的目錄結構
- 利用交叉引用連結快速跳轉

## 🚀 系統特色亮點

### 💻 **多種使用方式**
- **命令列工具**: 適合批次處理與自動化
- **Web 介面**: 提供圖形化操作與預覽
- **Docker 容器**: 支援企業級部署與擴展
- **API 服務**: 支援與其他系統整合

### 🎯 **核心優勢**
- **準確性**: 100% 測試覆蓋率，符合台灣勞基法
- **效率性**: 增量分析避免重複處理
- **智慧性**: 自動識別異常與建議
- **擴展性**: 模組化架構支援客製化

---

**最後更新**: 2025-01-27 | **文件版本**: v2.1 | **系統版本**: 查看 [project-structure.md](project-structure.md)
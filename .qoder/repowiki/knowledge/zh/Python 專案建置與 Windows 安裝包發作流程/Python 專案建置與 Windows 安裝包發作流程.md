---
kind: build_system
name: Python 專案建置與 Windows 安裝包發作流程
category: build_system
scope:
    - '**'
source_files:
    - .github/workflows/release.yml
    - .github/workflows/rule-tests.yml
    - tools/make_release.py
    - tools/make_sfx.py
    - packaging/python-runtime.json
    - packaging/sfx-config.txt
    - packaging/sfx-module.json
---

本專案採用「純 Python + GitHub Actions」的輕量建置系統，以 tools/make_release.py 與 tools/make_sfx.py 為核心，將倉庫打包成零安裝的 Windows 自解壓縮檔（.exe）與免安裝 ZIP，並透過 CI 執行單元測試、規則測試與圖譜新鮮度檢查後發布至 GitHub Releases。

**1. 使用的工具與框架**
- 語言：Python 3（標準庫為主，僅在 CI 中呼叫外部 7z 與 curl）
- 持續整合：GitHub Actions（.github/workflows/release.yml 與 rule-tests.yml）
- 封裝格式：7-Zip SFX（7zS2.sfx），搭配批次檔 安裝.bat 作為啟動殼層
- 版本管理：Git tag v* 觸發發版；版本號由 --version 參數或 tag 名稱決定

**2. 關鍵檔案與角色**
- .github/workflows/release.yml：定義四階段工作流（verify → package → installer → windows-check → publish），產出 zip 與 setup.exe 兩個 artifact
- .github/workflows/rule-tests.yml：PR 與 main push 時執行的規則一致性把關，包含 DXF 零相依測試、圖譜重建驗證等
- tools/make_release.py：從倉庫根掃描 INCLUDE_DIRS/EXCLUDE_PATTERNS，攤出 stage 目錄並寫入 安裝清單.json（含每個檔案 sha256），最後可壓縮為 zip
- tools/make_sfx.py：讀取 packaging/python-runtime.json 與 sfx-config.txt，產生 安裝.bat，用 7z 打包後與 SFX 模組拼接成 .exe
- packaging/sfx-module.json：釘死 7zS2.sfx 的 url 與 sha256，CI 會下載並核對
- packaging/python-runtime.json：指定 Python 版本、下載 URL 模板、Authenticode 發行者簽章與安裝引數
- tools/installer.py：使用者端安裝器，支援升級路徑（保留使用者改動、上游新版另存 .上游新版）

**3. 架構與設計決策**
- 兩條取得路徑並行：線1 給技術人員 git clone，線2 給消防專業人員下載 .exe 或 .zip（無 git、零安裝門檻）
- 所有建置邏輯在 Linux runner 上完成，Windows job 僅用於編碼與安裝路徑驗證
- SFX 模組是「建置輸入」而非動態下載，確保最終 exe 的完整性可追溯
- Python 安裝程式不釘 sha256，改用 Authenticode 簽章驗證發行者身分，安全更新不必重算雜湊
- 安裝包內不含 .git，依賴 安裝清單.json 作為權威基準，由 update_guard.py 驅動逐檔判定

**4. 規範與約束**
- 版本號必須符合 v* tag 格式（release workflow on: tags: ["v*"]）
- 發版前必須通過：Python 單元測試、引擎 self-test、規則測試 run-tests --strict、法規圖譜新鮮度檢查
- 安裝包排除 input/範例、output、dist、packaging 等目錄，tests 全部使用 tempfile 不依賴範例資料
- SFX 模組的 sha256 與 member_sha256 必須與 sfx-module.json 一致，否則 CI 失敗
- python-runtime.json 的 url 必須在發版時返回 HTTP 200，避免使用者端才發現連結失效
- 安裝程式升級時，使用者改過的檔案一律保留，上游新版另存為 .上游新版 供比對
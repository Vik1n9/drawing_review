---
kind: dependency_management
name: Python 依賴管理與零安裝策略
category: dependency_management
scope:
    - '**'
source_files:
    - requirements.txt
    - tools/setup.sh
    - tools/installer.py
    - packaging/python-runtime.json
    - packaging/sfx-module.json
---

本專案採用「零安裝主線 + 選用套件」的 Python 依賴管理策略，核心邏輯完全基於 Python 標準庫，第三方套件僅用於少數交付物格式且皆有替代路徑。

**主要系統與工具**
- `requirements.txt`：宣告三個選用套件（ezdxf、openpyxl、pymupdf），皆以寬鬆版本範圍（如 `>=1.3,<2`）聲明，不鎖定精確版本。
- `tools/setup.sh`：一鍵環境部署腳本，優先嘗試 `pip install -r requirements.txt`，失敗後自動回退到 `--user` 或 `--break-system-packages` 模式，並支援 `--with-graph` 參數額外安裝 graphify。
- `tools/installer.py`：Windows 安裝程式入口，內建 `install_optional_packages()` 函式會嘗試 pip 安裝選用套件，但失敗不會中斷安裝流程。
- `packaging/python-runtime.json` 與 `packaging/sfx-module.json`：定義 Python 運行時與 SFX 模組的下載來源與完整性校驗。

**架構與設計決策**
- 零安裝哲學：審圖主線（法規門檻計算、DXF 圖面標註、文件判讀）全部使用標準庫，確保在沙盒、離線環境、企業內網等限制下仍可運作。
- 選用套件容錯：`check_env.py` 會偵測可用功能，使用者可透過替代路徑達成相同目標（如 HTML 版檢核清單替代 Excel 輸出）。
- 升級安全：`update_guard` 機制確保更新時保留使用者修改的檔案，避免裁示紀錄被靜默覆蓋。
- Windows 封裝：透過自解壓縮檔（SFX）搭配 Python 運行時下載，提供免安裝的 exe 發行包。

**約束與規範**
- 選用套件版本範圍採寬鬆上限（`<major+1`），避免上游大版本更動造成破壞。
- 安裝過程不強制要求所有套件成功，失敗僅記錄警告而不中斷。
- Python 運行時版本由 `python-runtime.json` 集中管理，CI 會在發版前驗證網址可達性。
- SFX 模組釘死 sha256 雜湊確保建置輸入完整性，與 Python 運行時的 Authenticode 簽章驗證形成互補策略。
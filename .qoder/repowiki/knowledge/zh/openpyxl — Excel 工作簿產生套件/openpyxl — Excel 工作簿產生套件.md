---
kind: external_dependency
name: openpyxl — Excel 工作簿產生套件
slug: openpyxl
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
source_files:
    - requirements.txt
    - tools/stage_report_xlsx.py
    - tools/review_checklist_xlsx.py
---

用於產出兩階段審查與法條檢核清單的 XLSX 交付物。stage_report_xlsx.py 以 openpyxl 複製 input/範例 中的既有 Excel 模板版面（分頁名稱、欄位順序、合併儲存格、資料驗證、欄寬），review_checklist_xlsx.py 則用相同排版慣例建立「法條檢核清單」工作簿。若環境未安裝會明確提示執行 setup.sh 或 pip install -r requirements.txt，屬於選用套件，審圖主線可改用 HTML 版替代。
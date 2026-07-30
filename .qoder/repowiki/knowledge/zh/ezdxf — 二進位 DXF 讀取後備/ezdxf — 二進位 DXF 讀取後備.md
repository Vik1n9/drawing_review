---
kind: external_dependency
name: ezdxf — 二進位 DXF 讀取後備
slug: ezdxf
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
source_files:
    - requirements.txt
---

作為文字 DXF 解析器（tools/dxf_parse.py，零相依）的後備方案，用於處理二進位 DXF 檔案。屬於選用套件，審圖主線已透過文字 DXF 路徑避免依賴；若安裝成功可提升 DXF 讀取相容性。
---
kind: external_dependency
name: PyMuPDF — PDF 標註工具唯一外部相依
slug: pymupdf
category: external_dependency
category_hints:
    - vendor_identity
scope:
    - '**'
source_files:
    - requirements.txt
    - tools/pdf_annotate.py
---

pdf_annotate.py 使用 PyMuPDF（import fitz）在原始平面圖 PDF 上畫紅圈、編號徽章與文字註解，輸出加註版 PDF。這是本專案唯一突破 stdlib-only 原則的外部套件；若未安裝會明確提示安裝方式。該工具僅用於產出「平面圖紅圈標註」交付物，不影響審圖核心流程。
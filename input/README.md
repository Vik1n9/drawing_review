# 統一輸入資料夾

所有待審資料放這裡，每個案件一個子目錄：

```
input/
├── {案件名}/
│   ├── 平面圖.pdf          — 建築平面圖（可多份，逐層或合併）
│   └── （選）使用執照摘要、面積計算表等佐證文件
└── 法規/
    └── 法條清單.pdf        — 核對用法條清單（有具體來源的條文彙編）
```

- 平面圖 PDF → 由 `/plan-intake` 讀取，產出 case.json 到 `output/{案件名}-{YYYYMMDD}/`
- 法條清單 PDF → 由 `/regulation-intake` 結構化為 `rules/equipment_rules.json` 與 `rules/regulation-checklist.html`（先紅再綠測試通過後才可使用）
- 輸入檔案只讀不改；所有產出一律寫到 `output/`

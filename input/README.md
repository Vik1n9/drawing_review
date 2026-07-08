# 統一輸入資料夾

所有待審資料放這裡，每個案件一個子目錄：

```
input/
├── {案件名}/
│   ├── drawings/
│   │   └── *.dxf           — DXF 向量圖面（可多份，逐層或依專業分圖）
│   └── 審查依據文件         — 使用執照、室內裝修（合格證明）申請書、面積計算表、圖例表等佐證文件
├── 範例/                    — 消防實務表格範例（交付物格式基準，只讀）
│   └── 複合用途建築物及樓層屬性檢討-範例.pdf
└── 法規/
    └── 法條清單.pdf        — 核對用法條清單（有具體來源的條文彙編）
```

**使用執照**與**室內裝修申請書**為 `/plan-intake` 證照文件萃取（`use_permit`／`interior_renovation`／`change_of_use`）
的必要輸入，缺件時 §13 適用判斷與主從用途判定將輸出「需人工判讀」。

- DXF 圖面與審查依據文件 → 由 `/plan-intake` 讀取，產出 case.json 到 `output/{案件名}-{YYYYMMDD}/`
- 法條清單 PDF → 由 `/regulation-intake` 結構化為 `rules/equipment_rules.json` 與 `rules/regulation-checklist.html`（先紅再綠測試通過後才可使用）
- 輸入檔案只讀不改；所有產出一律寫到 `output/`

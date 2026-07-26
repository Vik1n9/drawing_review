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

## 各種檔案格式怎麼處理（都不用安裝任何東西）

| 你手上的檔案 | 怎麼辦 |
|---|---|
| `.dxf` | 直接放進來就好——以標準庫解析，零安裝 |
| **`.dwg`** | **AI 讀不了**（二進位專有格式）。跑 `python3 tools/dwg_guide.py check --path input/`，照它印出的步驟用你自己的 CAD 另存成 DXF |
| `.pdf`（使用執照、申請書、審查表…） | 直接放進來，AI 會自己讀 |
| `.docx`／`.xlsx` | 同上，直接放進來 |

DWG 另存 DXF 時記得：**版本選「AutoCAD 2013」或更新**（舊版的中文是 Big5 編碼，圖層名容易變亂碼），
**不要勾選「二進位／Binary」**。四大 CAD（AutoCAD、ZWCAD 中望、BricsCAD、GstarCAD 浩辰）都可以直接打 `DXFOUT` 指令。

轉檔而來的圖面，`case.json` 對應欄位會標 `source: derived`，可讀性最高只到 B 級——轉檔會改動圖層命名與圖塊，需人工複核。
轉檔產物一律寫到 `output/`，**`input/` 只讀不改**。

- DXF 圖面與審查依據文件 → 由 `/plan-intake` 讀取，產出 case.json 到 `output/`
- 法條清單 PDF → 由 `/regulation-intake` 結構化為 `rules/equipment_rules.json` 與 `rules/regulation-checklist.html`（先紅再綠測試通過後才可使用）
- 輸入檔案只讀不改；所有產出一律寫到 `output/`

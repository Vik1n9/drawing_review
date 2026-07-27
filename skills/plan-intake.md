# 平面圖輸入與圖說底稿建立

對 $ARGUMENTS（案件名）執行圖說結構化，產出 `case.json` 圖說底稿。這是整條審圖流水線的入口，**下游所有計算以本 skill 產出的 case.json 為準，不以 DXF、PDF、SVG 或圖片為準**。

## 輸入與輸出（統一資料夾）

- 輸入：`input/{案件名}/平面圖.dxf` 作為需要審核的主圖面，搭配同資料夾內的 `平面圖.pdf` 輔助對照與相關審查文件（只讀不改）；案件資料夾內不放法規檔
- 輸出：建立 `output/` 新目錄，case.json 與後續所有交付物都寫入此目錄

## 執行流程

### 第一步：收件與圖說可讀性評級

先跑 `python3 tools/dwg_guide.py check --path input/{案件名}/`。它以**檔案內容**（magic bytes）而非副檔名判定格式——送審資料的副檔名常常說謊，且會直接告訴你有沒有 DWG 要先處理。

**格式處理原則（都不需要安裝任何東西）**：

| 格式 | 怎麼處理 |
|---|---|
| `.dxf` | 直接用。`tools/dxf_parse.py` 以標準庫解析，零安裝 |
| `.dwg` | **無法直接判讀**，依 `dwg_guide.py` 印出的步驟請使用者用自己的 CAD 另存 DXF（見下方「DWG 怎麼辦」） |
| `.pdf` | **由你直接讀取檔案**，不需要任何工具或套件 |
| `.docx`／`.xlsx` | 同上，直接讀 |

#### DWG 怎麼辦（零執行也要能講清楚）

DWG 是二進位專有格式，AI 讀不了，一定要轉成 DXF。轉檔器在多數使用者的環境裝不起來，但**他們機器上幾乎必然已有 CAD**，原生匯出零安裝且品質更好。照這樣講給使用者聽：

1. 用你的 CAD 打開這張 DWG
2. 輸入指令 `DXFOUT`（或選單「檔案 → 另存新檔／另存為」）
3. 檔案類型選 DXF，版本選「AutoCAD 2013」或更新
4. **不要勾選「二進位（Binary）」**——本系統只讀文字（ASCII）DXF
5. 存到同一個案件資料夾，副檔名 `.dxf`

AutoCAD／AutoCAD LT、ZWCAD（中望）、BricsCAD、GstarCAD（浩辰）都支援 `DXFOUT` 指令。選 2013 以上是因為舊版 DXF 的中文採 Big5／cp950 編碼，圖層名與文字標註容易變亂碼。

轉檔而來的圖面（無論使用者自己轉或工具轉），對應欄位一律標 `source: derived`，可讀性**最高只到 B 級**——轉檔會遺失或改動圖層命名、字型與圖塊。

#### 收到舊版（R12／Big5）DXF 是常態，不要退件

「版本選 2013 以上」是給還沒匯出的人的建議，**不是收件門檻**。實際送審圖多半是舊版：
`input/範例/楷得立消防設備圖說.dxf` 就是 AC1009（R12）、標頭無 `$DWGCODEPAGE`、圖層名 Big5。
`dxf_parse.py` 會比對候選編碼自動判定並在警告中說明選了哪個、有多少字元無法還原。

- 看到「比對後以 cp950 解碼」→ **正常**，但中文圖層名要人工掃一眼再採用
- 看到「編碼無法確定」或圖層名出現 `�` → 才需要請使用者重新匯出
- 這不影響評級：能正確解析就依一般標準評 A／B 級，不因版本舊而降級

#### 設備符號是圖塊，實設數量看圖塊統計

跑 `python3 tools/dxf_parse.py --input {圖檔}`，輸出的「圖塊統計」依圖層與圖塊名列出插入點數量。
真實圖面上偵煙探測器、緊急照明燈、揚聲器、緊急出口燈、滅火器、消防栓箱全是圖塊，
這份統計就是後續 `/gap-analysis` 比對「應設 vs 實設」的實設側來源。

- 圖塊名通常比圖層名精確（如「偵煙探測器一種」對上圖層 `1_偵煙探測器`），兩者並列供人工核對
- 名稱以 `*` 開頭的匿名圖塊是 CAD 內部產物（舊版 DXF 用來表示填充線與標註），已自動略過
- **圖塊插入點數不等於實際設置數量**——一個圖塊可能代表一組設備，數值須經第三步人工確認才可寫入 `case.json`

盤點 `input/{案件名}/` 內的 `平面圖.dxf`（多張圖時為 `drawings/*.dxf`）、輔助 `平面圖.pdf` 與相關審查文件。審查文件需具名盤點下列類型（有無都要回報）：

- **使用執照**（或變更使用執照、建築物概要表）——用途分類與原核准面積的最高優先證據
- **室內裝修（合格證明）申請書**——裝修範圍、裝修後用途、本次申請面積；§13 新舊標準適用判斷的必要輸入
- 消防安全設備審查表、面積計算表、圖例表等其他文件

先給出**圖說可讀性評級**並告知使用者：

| 等級 | 特徵 | 策略調整 |
|------|------|---------|
| A級（清晰完整） | `平面圖.dxf` 圖層命名清楚，有樓層對應、圖例表、面積標注，且輔助 PDF 與審查文件齊全 | 正常萃取，關鍵欄位仍須人工確認 |
| B級（部分可讀） | DXF 可解析但圖層/圖例不完整，需用輔助 PDF 或審查文件人工對照部分樓層或設備符號 | 可讀部分正常萃取；模糊欄位標 `confidence: low`，列入確認清單優先項 |
| B級（部分可讀）— 轉檔而來 | 原始圖面是 DWG，經另存／轉檔取得 DXF | 同 B 級處理，且**不得升為 A 級**；圖層命名與符號歸類須逐項人工複核，欄位標 `source: derived` |
| C級（難以判讀） | `平面圖.dxf` 缺檔且無法取得（例如只有 DWG 但使用者無 CAD 可匯出）、圖層混亂、座標或比例不明，或只有輔助 PDF/掃描圖 | 轉為「人工輸入模式」：AI 只做欄位清單引導，數值全部由使用者提供 |

**關鍵提醒**：DXF 可解析 ≠ 圖說資料正確。圖層命名、符號歸類、比例與樓層對應都可能錯，任何等級都不得跳過第三步的人工確認關卡。

### 第二步：逐層萃取

對每一樓層萃取以下欄位，每個欄位帶 `value`、`confidence`（high/medium/low）、`source`（drawing/manual/derived）：

1. **基本資料**：案件名、地址、構造種別（耐火／非耐火）、總樓層數（地上／地下）、建築高度
2. **樓層資料**（逐層）：樓層別、樓地板面積、用途（必須依 `skills/place-use-classification.md` 產出第12條候選分類，標註「待確認」）、樓層屬性（地下層／一般樓層／屋頂層或屋突層）、是否無開口樓層（依 §4，標 `需人工判讀` 除非圖面與文件明確）
3. **空間清單**（逐層）：居室名稱、面積、天花板高度（如有標注）
4. **既有設備**（逐層，依 DXF 圖層/圖例/符號辨識）：滅火器、室內消防栓、撒水頭、探測器、出口標示燈、避難方向指示燈、緊急照明、排煙口等的**種類與數量**；圖例不明者列入 `unrecognized_symbols`
5. **收容人數計算基礎**：固定席位數、客席／營業面積等（依用途）
6. **圖面來源索引**：每張 DXF 的 `drawing_id`、路徑、樓層、單位、model-space 外框、圖層清單

### 第二步半：證照文件萃取（使用執照／室內裝修申請書）

自使用執照與室內裝修申請書逐欄萃取，寫入 case.json 的 `use_permit`、`interior_renovation`、`change_of_use` 三個區塊（schema 見第四步）。每欄帶 `value`、`confidence`、`source`（文件路徑寫入 `source_documents`）：

1. **use_permit**：執照字號、核發日期、原核准總樓地板面積、各層原核准用途與面積
2. **interior_renovation**：裝修樓層、工程類別（增建／改建／室內裝修）、本次申請範圍樓地板面積、裝修後用途
3. **change_of_use**：是否變更用途、變更前後用途（§12 候選代碼）、變更前設備是否符合變更前規定（如可考）

室內裝修申請書為建管 E1-2 表單，欄名不明或版面殘缺時，以 `input/範例/室內裝修表單範本/`
的空白官方表單（E1-1、E1-2、E1-4、E1-5、E1-6）核對欄位位置與名稱，該資料夾 README 附
E1-2 → case.json 欄位對照；**對照只用於定位欄位，值一律照案件文件所載，缺欄標「需人工判讀」**。

萃取後必查兩件事：
- **原核准用途 vs 本次申請用途不一致** → 寫入 `manual_review_items`，並於人工確認關卡標紅提示
- 任一區塊文件缺件 → 該區塊留 `null` 並記入 `manual_review_items`（§13 適用判斷將輸出「需人工判讀」）

此區塊是 `/mixed-use-review`（主從用途判定）與 `fire_code_calc.py check-applicability`（§13 新舊標準適用）的資料來源，缺漏會使下游全部輸出「需人工判讀」。

### 第三步：人工確認關卡（強制，不可跳過）

用表格向使用者逐項展示萃取結果與信心度，**必須確認的欄位**：

- 各層用途分類（法定分類直接決定所有門檻，AI 只給建議）
- 各層第 12 條用途分類的「條、款、目」法條位階與證據來源（依 `skills/place-use-classification.md`）
- 各層樓地板面積、總樓地板面積
- 構造種別（耐火／非耐火——影響探測器與撒水頭涵蓋面積）
- 地下層／屋突層或屋頂層／無開口樓層判定
- **證照文件萃取欄位**（use_permit／interior_renovation／change_of_use 全部欄位，特別是原核准用途與本次申請用途是否一致）
- `confidence: low` 的全部欄位

使用者確認或修正後，將對應欄位的 `source` 改為 `manual`、`confidence` 改為 `high`。

### 第三步半：缺失定位基礎（供 SVG 標註網頁使用）

萃取時同步記錄各樓層／各房間在 DXF model-space 中的**圖面 ID 與大致位置**（`drawing_id` + `bbox`），寫入 case.json 的 `layout_index`。後續 `/gap-analysis` 產出 SVG 標註時引用此索引；定位不確定的標 `position_confidence: low`。舊案若只有 PDF 來源，可暫時保留 `page` + 相對座標 `bbox` 作 legacy fallback，但不得作為新案優先格式。

### 第四步：產出 case.json

寫入 `output/case.json`，schema 如下：

```json
{
  "case_name": "範例大樓",
  "created": "2026-07-08",
  "intake_grade": "B",
  "regulation_version": "各類場所消防安全設備設置標準（版本日期見 rules 檔）",
  "source_drawings": [
    {
      "drawing_id": "1F",
      "path": "input/範例大樓/平面圖.dxf",
      "floor": "1F",
      "unit": "mm",
      "model_bbox": [0, 0, 50000, 32000],
      "layers": ["WALL", "DOOR", "FIRE_EQUIPMENT"]
    }
  ],
  "source_documents": [
    {"type": "輔助平面圖", "path": "input/範例大樓/平面圖.pdf"},
    {"type": "使用執照", "path": "input/範例大樓/使用執照.pdf"},
    {"type": "室內裝修申請書", "path": "input/範例大樓/室內裝修申請書.pdf"},
    {"type": "審查文件", "path": "input/範例大樓/消防安全設備審查表.pdf"}
  ],
  "building": {
    "construction": {"value": "耐火", "confidence": "high", "source": "manual"},
    "floors_above": 8,
    "floors_below": 1,
    "total_floor_area": {"value": 3200, "unit": "㎡", "confidence": "high", "source": "manual"},
    "principal_use": {
      "value": "甲5", "category": "甲類場所", "label": "餐廳、飲食店、咖啡廳、茶藝館",
      "legal_basis": "§12 第1款第5目",
      "basis": "使用執照主要用途欄；各層用途以本用途為主、他層構成從屬（/mixed-use-review 確認）",
      "confidence": "high", "source": "manual"
    },
    "mixed_use_assessment": {
      "is_mixed_use": false,
      "category_candidate": null,
      "basis": "各層用途依對照表均構成主用途之從屬部分（或：構成戊1/戊2 候選，填 legal_basis）",
      "confidence": "high", "source": "manual"
    }
  },
  "use_permit": {
    "permit_no": {"value": "○○使字第000000號", "confidence": "high", "source": "manual"},
    "issued_date": {"value": "2010-05-20", "confidence": "high", "source": "manual"},
    "total_floor_area": {"value": 3200, "unit": "㎡", "confidence": "high", "source": "manual"},
    "approved_floor_uses": [
      {"floor": "1F", "use": "商場", "area": 450, "confidence": "high", "source": "manual"}
    ]
  },
  "interior_renovation": {
    "floors": {"value": ["3F"], "confidence": "high", "source": "manual"},
    "works_type": {"value": "室內裝修", "confidence": "high", "source": "manual"},
    "area": {"value": 350, "unit": "㎡", "confidence": "high", "source": "manual"},
    "post_renovation_use": {"value": "乙7", "confidence": "medium", "source": "manual"}
  },
  "change_of_use": {
    "occurred": {"value": false, "confidence": "high", "source": "manual"},
    "before": {"value": null, "confidence": null, "source": null},
    "after": {"value": null, "confidence": null, "source": null},
    "prior_compliant": {"value": null, "confidence": null, "source": null}
  },
  "floors": [
    {
      "floor": "1F",
      "area": {"value": 450, "unit": "㎡", "confidence": "high", "source": "manual"},
      "floor_position": {"value": "ordinary", "label": "一般樓層", "confidence": "high", "source": "drawing"},
      "use_category": {
        "value": "甲5",
        "category": "甲類場所",
        "label": "餐廳、飲食店、咖啡廳、茶藝館",
        "legal_basis": "§12 第1款第5目",
        "confidence": "high",
        "source": "manual"
      },
      "use_candidates": [
        {"value": "甲5", "legal_basis": "§12 第1款第5目", "confidence": "medium", "source": "drawing"}
      ],
      "use_relation": {
        "role": "principal",
        "subordinate_to": null,
        "basis": "依對照表判定（/mixed-use-review 人工確認後填 manual；role: principal|subordinate|independent|null）",
        "confidence": "high", "source": "manual"
      },
      "windowless": {"value": false, "legal_basis": "§4", "confidence": "medium", "source": "drawing"},
      "rooms": [{"name": "客席區", "area": 280, "ceiling_height": 3.2}],
      "existing_equipment": {
        "extinguisher": 2, "indoor_hydrant": 1, "sprinkler_head": 0,
        "smoke_detector": 6, "heat_detector": 2,
        "exit_light": 2, "direction_light": 3, "emergency_light": 8
      },
      "occupancy_basis": {"fixed_seats": 40, "components": [{"name": "客席", "area": 120, "per_sqm": 3}]},
      "layout_index": {"drawing_id": "1F", "bbox": [1200, 1800, 8500, 6200], "position_confidence": "medium"}
    }
  ],
  "unrecognized_symbols": ["3F 東側走廊有一不明圖例，需人工判讀"],
  "manual_review_items": ["地下層是否為無開口樓層需依開口計算確認"]
}
```

### 第五步：收件摘要

向使用者輸出收件摘要：樓層數、各層用途與面積表、既有設備統計表、證照文件萃取摘要（use_permit／interior_renovation／change_of_use）、`需人工判讀` 清單，並詢問是否接續執行 `/mixed-use-review`（主從用途判定與複合用途檢討表，§12 分類定案後再進 `/code-requirements`）。

## 重要注意事項

1. **AI 不做用途分類的最終判定**——複合用途、邊界案例（如附設 KTV 的餐廳）一律列出候選分類請使用者裁決
2. **面積數字寧缺勿猜**——DXF 或審查文件無標注且比例/單位不明時標 `null` + `需人工判讀`，禁止目測估算
3. **圖例辨識保守原則**——不確定的符號進 `unrecognized_symbols`，不要硬歸類
4. 遵守 `AGENTS.md` 五條底線

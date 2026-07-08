# 平面圖輸入與圖說底稿建立

對 $ARGUMENTS（案件名）執行圖說結構化，產出 `case.json` 圖說底稿。這是整條審圖流水線的入口，**下游所有計算以本 skill 產出的 case.json 為準，不以圖片為準**。

## 輸入與輸出（統一資料夾）

- 輸入：`input/{案件名}/` 內的平面圖 PDF（只讀不改）
- 輸出：建立 `output/{案件名}-{YYYYMMDD}/` 新目錄，case.json 與後續所有交付物都寫入此目錄

## 執行流程

### 第一步：收件與圖說可讀性評級

以 Read 工具逐頁讀取 `input/{案件名}/` 內的平面圖 PDF（每次最多 20 頁，分批處理；多份 PDF 逐份處理），先給出**圖說可讀性評級**並告知使用者：

| 等級 | 特徵 | 策略調整 |
|------|------|---------|
| A級（清晰完整） | 有比例尺、圖例表、面積標注、樓層表 | 正常萃取，關鍵欄位仍須人工確認 |
| B級（部分可讀） | 缺圖例或部分標注模糊 | 可讀部分正常萃取；模糊欄位標 `confidence: low`，列入確認清單優先項 |
| C級（難以判讀） | 掃描品質差、無比例尺、手繪 | 轉為「人工輸入模式」：AI 只做欄位清單引導，數值全部由使用者提供 |

**關鍵提醒**：圖面清晰 ≠ 萃取正確。視覺模型對面積數字、圖例符號的誤讀率不可忽略，任何等級都不得跳過第三步的人工確認關卡。

### 第二步：逐層萃取

對每一樓層萃取以下欄位，每個欄位帶 `value`、`confidence`（high/medium/low）、`source`（drawing/manual/derived）：

1. **基本資料**：案件名、地址、構造種別（耐火／非耐火）、總樓層數（地上／地下）、建築高度
2. **樓層資料**（逐層）：樓層別、樓地板面積、用途（依設置標準第12條分類建議，標註「待確認」）、是否無開口樓層（標 `需人工判讀` 除非圖面明確）
3. **空間清單**（逐層）：居室名稱、面積、天花板高度（如有標注）
4. **既有設備**（逐層，依圖例辨識）：滅火器、室內消防栓、撒水頭、探測器、出口標示燈、避難方向指示燈、緊急照明、排煙口等的**種類與數量**；圖例不明者列入 `unrecognized_symbols`
5. **收容人數計算基礎**：固定席位數、客席／營業面積等（依用途）

### 第三步：人工確認關卡（強制，不可跳過）

用表格向使用者逐項展示萃取結果與信心度，**必須確認的欄位**：

- 各層用途分類（法定分類直接決定所有門檻，AI 只給建議）
- 各層樓地板面積、總樓地板面積
- 構造種別（耐火／非耐火——影響探測器與撒水頭涵蓋面積）
- 地下層／無開口樓層判定
- `confidence: low` 的全部欄位

使用者確認或修正後，將對應欄位的 `source` 改為 `manual`、`confidence` 改為 `high`。

### 第三步半：缺失定位基礎（供標註圖使用）

萃取時同步記錄各樓層／各房間在 PDF 中的**頁碼與大致位置**（相對座標 0~1 的外框），寫入 case.json 的 `layout_index`。後續 `/gap-analysis` 產出紅圈標註時引用此索引；定位不確定的標 `position_confidence: low`。

### 第四步：產出 case.json

寫入 `output/{案件名}-{YYYYMMDD}/case.json`，schema 如下：

```json
{
  "case_name": "範例大樓",
  "created": "2026-07-08",
  "intake_grade": "B",
  "regulation_version": "各類場所消防安全設備設置標準（版本日期見 rules 檔）",
  "building": {
    "construction": {"value": "耐火", "confidence": "high", "source": "manual"},
    "floors_above": 8,
    "floors_below": 1,
    "total_floor_area": {"value": 3200, "unit": "㎡", "confidence": "high", "source": "manual"}
  },
  "floors": [
    {
      "floor": "1F",
      "area": {"value": 450, "unit": "㎡", "confidence": "high", "source": "manual"},
      "use_category": {"value": "甲1", "label": "餐飲場所", "confidence": "high", "source": "manual"},
      "windowless": {"value": false, "confidence": "medium", "source": "drawing"},
      "rooms": [{"name": "客席區", "area": 280, "ceiling_height": 3.2}],
      "existing_equipment": {
        "extinguisher": 2, "indoor_hydrant": 1, "sprinkler_head": 0,
        "smoke_detector": 6, "heat_detector": 2,
        "exit_light": 2, "direction_light": 3, "emergency_light": 8
      },
      "occupancy_basis": {"fixed_seats": 40, "components": [{"name": "客席", "area": 120, "per_sqm": 3}]},
      "layout_index": {"page": 1, "bbox": [0.1, 0.15, 0.9, 0.85], "position_confidence": "medium"}
    }
  ],
  "unrecognized_symbols": ["3F 東側走廊有一不明圖例，需人工判讀"],
  "manual_review_items": ["地下層是否為無開口樓層需依開口計算確認"]
}
```

### 第五步：收件摘要

向使用者輸出收件摘要：樓層數、各層用途與面積表、既有設備統計表、`需人工判讀` 清單，並詢問是否接續執行 `/code-requirements`。

## 重要注意事項

1. **AI 不做用途分類的最終判定**——複合用途、邊界案例（如附設 KTV 的餐廳）一律列出候選分類請使用者裁決
2. **面積數字寧缺勿猜**——圖面無標注且無比例尺時標 `null` + `需人工判讀`，禁止目測估算
3. **圖例辨識保守原則**——不確定的符號進 `unrecognized_symbols`，不要硬歸類
4. 遵守 `CLAUDE.md` 審圖最高原則

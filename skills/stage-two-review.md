# 第二階段：消防安全設備設置標準檢討

對 $ARGUMENTS（案件名）依第一階段定案的 §12 分類與樓層屬性，逐條檢討《各類場所消防安全
設備設置標準》第 14 條至第 31 條的應設設備，產出設置標準檢討表（HTML ＋ Excel）。

## 核心規則

- 第一階段必須先完成。結果缺漏、過期或與本案文件不一致時，先執行 `/first-stage-review`，
  或請使用者指認正確的第一階段結果。**不得僅由原始案件文件產出第二階段結果。**
- 第一階段結果經修正時，**從修正後的結果重跑完整第二階段**；不得沿用前一次的勾選、
  未勾選、應設設備列、備註或待釐清事項。

## 開始前必讀（不可跳過）

1. `rules/stage_two_judgment_rules.md`
2. `rules/review_corrections.md`
3. `rules/article18_equipment_options.json`

三份均未經 `governance/` 核定。援引其中任一項做成的結論，輸出時附警語
**「本判斷慣例未經消防專業人員核定，以現行法規為準」**。

## 法條調閱

**不要一次載入 §14~§31 全文。** 逐條判斷時走：

```bash
python3 tools/regulation_graph.py neighbors --article §24        # 定位：引用網＋附表圖檔
python3 tools/regulation_index.py lookup --article '§24,§12'     # 載入：只取相關條文原文
python3 tools/fire_code_calc.py check-threshold --case output/{案件名}-{YYYYMMDD}/case.json
```

其他定位指令：`regulation_graph.py articles --equipment 排煙設備`、
`regulation_graph.py path --from 無開口樓層 --to 排煙設備`。

圖譜不得作為門檻數值來源，節點標題不得當作法規數值使用。附表圖檔在
`rules/法規/1各類場所消防安全設備設置標準_assets/`。

## 必要輸入

- `output/{案件名}-{YYYYMMDD}/case.json`
- `rules/checklists/各類場所消防安全設備設置標準14~31條判斷用.xlsx`
- `input/範例/第二階段-設置標準檢討-格式範本.xlsx`

## 執行流程

### 第一步：確認第一階段已完成

`case.json` 的 `building.mixed_use_assessment` 非 `null` 且 `source: manual`，
各層 `use_category` 已定案。未達成則先跑 `/first-stage-review`。

### 第二步：門檻計算與逐條窮舉

```bash
/code-requirements {案件名}
python3 tools/article_checklist.py --case output/{案件名}-{YYYYMMDD}/case.json
```

工具輸出原文嵌入報告作為計算記錄。

### 第三步：受控自動化關卡（強制，不可跳過）

```bash
python3 tools/case_facts_gate.py --stage second --case output/{案件名}-{YYYYMMDD}/case.json
```

`ready: false` 或結束碼 2 時，**先詢問使用者並等待答覆，不得產出最終工作簿**。
資料不足、來源矛盾、通風／採光／特殊設備或特殊用途無法確認，均屬阻擋問題。

### 第四步：人工定案勾選（AI 不得自行定案）

填 `output/{案件名}-{YYYYMMDD}/stage2_decisions.json`：

```json
{
  "checkedRefs": ["14-2", "18-3", "22", "25"],
  "notesByRef": {"18-3": "停車空間非本次申請範圍"},
  "equipmentRows": [["滅火器", "第14條第2、3款", ""]],
  "pendingRows": [["第14條第5款", "是否設有鍋爐房、廚房等大量使用火源之場所？",
                   "建築圖或空間用途資料", "無法判斷滅火器應設範圍"]]
}
```

- `checkedRefs`：條款代號 `{條}-{款}`，無款次者只寫條號
- `notesByRef`：僅 `非本次申請範圍` 類事實
- `equipmentRows` 省略時由 `checkedRefs` 自動彙整
- `pendingRows` 省略時預設一列 `無`

### 第五步：產出交付物

```bash
python3 tools/checklist_html.py --results output/{案件名}-{YYYYMMDD}/check_results.json
python3 tools/stage_report_xlsx.py stage-two \
  --decisions output/{案件名}-{YYYYMMDD}/stage2_decisions.json \
  --case output/{案件名}-{YYYYMMDD}/case.json
```

## 產出後交叉核對（強制關卡）

定稿前**獨立重讀**第一階段結構化的 §12 分類與本次申請樓層用途，對每一個已勾選的條款驗證：
該條款自身的用途／類別條件是否包含那筆分類本身。

- 僅由其他樓層用途或整棟複合用途判定支撐的勾選一律清除，除非該條款明文適用於建築物整體
  或基地。
- 無法確認適用性者記入「待釐清事項」，不得保留無依據的勾選。
- 第 24 條第 2 款：僅限條文列舉的 §12 第 2 款用途。本次申請為 §12 第 1 款用途（例如
  托嬰中心）時，除非另有符合第 2 款的居室用途並有文件佐證，否則不得勾選。第 2 款第 7 目
  僅適用「住宿型精神復健機構」，一般集合住宅不得勾選。

## 工作簿格式契約

三分頁固定為 `消防安全設備設置標準`、`應設置設備`、`待釐清事項`。

主表欄位固定為 `判斷｜條文/設備｜款項條件｜備註`：

- 符合的列在 `判斷` 欄標 `✓`
- `非本次申請範圍` 逐字使用並以紅字呈現
- 第 18 條必須出現在第 17 條與第 19 條之間
- 第 18 條的 `條文/設備` 欄僅列該款可選設的設備名稱（例：`泡沫、乾粉`），不加條次前綴；
  條文名稱為「應設置**自動**滅火設備」
- 未符合的條款備註留白，除非該備註可預防已知的重複性誤解

`應設置設備`：每項應設消防設備一列，附法條依據與備註。

`待釐清事項`：需使用者提供資料的項目；無則填一列 `無` ＋
`目前依第一階段資料可完成本次第二階段判斷。`。不得只留在對話中。

## 備註欄位規則

主表與 `應設置設備` 的 `備註` 僅可記載明確屬於 `非本次申請範圍` 的事實，未涉及時留白。
條文符合原因、門檻、用途及其他判定說明留在 `款項條件` 欄；資料不足列於「待釐清事項」。
不得在備註欄解決不確定的用途、面積、設備、採光或通風事實。

## 驗證清單（回覆前）

- 已指認本案使用的第一階段結果
- 已讀取 `rules/stage_two_judgment_rules.md` 與 `rules/review_corrections.md`
- 每一個已勾選條款的門檻與用途條件，都已用 `regulation_index.py lookup` 調閱條文原文核對
- 第 18 條出現在第 17 條與第 19 條之間
- 依第 19 條或第 21 條應設警報設備時，第 22 條已勾選（第 20 條不構成觸發條件）
- 產出後交叉核對已完成，無僅由其他樓層或整棟判定支撐的勾選
- `應設置設備` 分頁存在且可讀
- 公式錯誤掃描（`#REF!`、`#DIV/0!`、`#VALUE!`、`#NAME?`、`#N/A`）零命中
- 最終工作簿存在於回報路徑
- 報告標頭注明法規版本；未核定規則已附警語

## 常見錯誤

- 跳過第一階段
- 把附設地下層的一般建築物當成 `地下建築物`
- 僅因本次申請範圍只有一層，就排除整棟／基地層級的應設要求
- 十一層以上建築物勾選第 19 條第 2 款
- 未符合的條款加註說明
- 待釐清事項只留在對話中，未寫入分頁
- 遺漏第 18 條
- 在備註欄寫判定理由，而非留在款項條件欄
- 一次載入 §14~§31 全文，而非定位後只載相關條

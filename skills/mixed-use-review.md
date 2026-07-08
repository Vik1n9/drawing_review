# 複合用途與主從用途判定（產出檢討表）

對 $ARGUMENTS（案件名）執行主從用途判定與複合用途檢討，對應消防實務四步驟工作流程的第 1~3 步：

1. 依《複合用途建築物判斷基準》附表「建築物主用途及從屬用途關係對照表」判定各層用途的主從關係
2. 產出交付物 4「**複合用途建築物及樓層屬性檢討**」HTML（格式對齊 `input/範例/複合用途建築物及樓層屬性檢討-範例.pdf`）
3. 據以定案《各類場所消防安全設備設置標準》第 12 條場所分類，回填 `case.json`

執行位置：`/plan-intake` 之後、`/code-requirements` 之前。§12 分類直接決定所有設備門檻，本 skill 未完成前不得進入設備計算。

## 前置檢查

1. `output/{案件名}-{YYYYMMDD}/case.json` 存在，且 `use_permit` 區塊已完成證照文件萃取；缺件則退回 `/plan-intake` 補齊（或明確記錄「無使用執照可考」進 `manual_review_items`）
2. 各層 `use_category` 至少有候選值（`use_candidates` 非空）
3. `python3 tools/fire_code_calc.py self-test` 通過（會一併檢查 `rules/mixed_use_rules.json` 結構）

## 執行流程

### 第一步：對照表比對（工具，只產候選）

```bash
python3 tools/fire_code_calc.py classify-mixed-use --case output/{案件名}-{YYYYMMDD}/case.json
```

工具逐層比對房名／用途名與對照表 31 項的主要用途部分（B）、便利從屬欄（C）、密切關係欄（D），輸出：

- `從屬候選`：命中某主用途項次的從屬欄位（附項次編號與命中欄位）
- `獨立用途候選`：未命中任何從屬欄 → 傾向構成複合用途
- 整棟結論候選：戊1／戊2／單一主用途

**工具輸出原文嵌入報告作為比對記錄。** 若 `rules/mixed_use_rules.json` 不存在，工具會明示 fallback：主從判定全部需人工判讀，依附表 PDF 人工比對。

**限制（必須告知使用者）**：《複合用途建築物判斷基準》**本文**（管理權同一、使用形態、面積比例等從屬認定要件）尚未入庫，工具只做名稱比對；量化與管理形態認定一律需人工判讀。

### 第二步：人工確認關卡（強制，不可跳過）

用表格向使用者逐層展示，**必須確認**：

- 整棟**主用途**（`building.principal_use`）：§12 條款目、法條位階、證據（使用執照優先）
- 各層 `use_relation.role`：`principal`（主用途）／`subordinate`（從屬，填 `subordinate_to`）／`independent`（獨立，構成複合）
- 是否構成**複合用途建築物**（`building.mixed_use_assessment.is_mixed_use`）與戊1／戊2 分類
- 對照表中 `transcription_note` 標注的疑字項（如涉及本案，須對照 PDF 原件確認）

使用者確認後，將上述欄位 `source` 改 `manual`、`confidence` 改 `high`。**AI 不得自行定案主從關係**（原則 5）。

### 第三步：§12 分類定案回填 case.json

依人工確認結果更新：

- 複合用途成立 → 各層 `use_category` 保留各目分類，`building.mixed_use_assessment` 填 `is_mixed_use: true` 與 `category_candidate`（戊1／戊2）＋ `legal_basis`（§12 第5款第1目／第2目）
- 全部構成從屬 → `building.principal_use` 定案，從屬樓層 `use_relation.role: subordinate`
- 注意 §12-1（戊類複合用途之設備檢討以各目為單元合計面積，見 `rules/法規/第2編-消防設計.md` 供第十二條第五款使用之複合用途建築物條文）——此影響 `/code-requirements` 的面積合計方式，定案時在 case.json `manual_review_items` 或報告中明確注記

### 第四步：產出檢討表（交付物 4）

```bash
python3 tools/mixed_use_report.py --case output/{案件名}-{YYYYMMDD}/case.json
```

產出 `{案件名}-複合用途及樓層屬性檢討.html`：主表逐層列「樓層｜各層用途｜樓地板面積｜本次申請範圍樓地板面積｜樓層屬性」＋合計列＋「複合用途建築物判定」編號結論。`null` 或 `confidence: low` 欄位一律顯示「⚪需人工判讀」，嚴禁以推測填充。

### 第五步：摘要

輸出：主用途／複合用途判定結論（附條號）、各層主從角色表、`需人工判讀` 殘留清單，並詢問是否接續執行 `/code-requirements`。

## 重要注意事項

1. **對照表僅供候選**——從屬認定的管理權、使用形態、面積比例要件（判斷基準本文）未入庫前，最終判定一律人工
2. **`verified: false` 警語必須保留**——`mixed_use_rules.json` 全部未核定
3. **§12 分類未定案不得進 `/code-requirements`**——門檻判斷全繫於此
4. 遵守 `CLAUDE.md` 審圖最高原則

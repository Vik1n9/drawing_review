# 實務註解庫（註解層）

本專案採**法典／註解雙軌制**：

| 層 | 位置 | 內容 | 變更途徑 |
|---|---|---|---|
| **法典層** | `rules/` | 法規條文、結構化規則參數 | 先紅再綠（`skills/red-green.md`） |
| **註解層** | `practice_notes/` | 法典**未涵蓋情境**下的實務見解 | `/practice-note`（`tools/practice_note_engine.py`）＋ 使用者「確認納入」 |

**註解只補充法典，不推翻法典。** 案件結論與法典有出入時，優先假設是「實務補充情境」並草擬註解供審閱；
若真的是法典寫錯或規則抄錯，那是先紅再綠的事，不是註解的事。

> 本專案使用者本身即為消防專業人員，**「確認納入」就是專業判斷的表示，不另設核定關卡**。
> 但註解終究是實務見解而非法規條文：援引註解的審查結論，
> **必須同時列出所補充的法條與註解 ID**，供覆核。

## 目錄

```
practice_notes/
├── active/      — 現行有效註解，每則一個 {id}.json
├── staging/     — Agent 草擬、待使用者確認（未生效）
└── index.json   — 由 practice_note_engine.py reindex 產生（by_article / by_equipment / by_rule_id）
```

註：與 `output/annotations.json` 無關——那是**圖面 SVG 標註**，
本資料夾是**法條實務補充見解**，兩者用途不同、刻意分開命名。

## 工作流程

```bash
# 1. 找出法典涵蓋不到的情境
python3 tools/fire_code_calc.py check-gap \
  --case output/case.json \
  --output output/gap_candidates.json

# 2. 草擬（判讀欄位一律留「（待填）」，須人工填實）
python3 tools/practice_note_engine.py draft \
  --gap output/gap_candidates.json --case {案件名}

# 3. 法典牴觸與重複檢查（0=通過 2=有阻擋問題）
python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/{id}.json

# 4. 使用者輸入「確認納入」後才可套用
python3 tools/practice_note_engine.py apply --draft practice_notes/staging/{id}.json \
  --approved-by "{批准人}" --confirm 確認納入 [--acknowledge-conflict "{確認理由與法源}"]

# 5. 迴歸驗收
python3 tools/practice_note_engine.py test --strict
```

## Schema

每則註解存於 `practice_notes/active/{id}.json`，檔名必須等於 `id`。

```json
{
  "id": "PN-20260725-001",
  "ref_article": "19",
  "ref_rule_ids": ["fire-alarm-threshold"],
  "scenario": {
    "summary": "挑空區超過 12 公尺且該區無常駐人員",
    "conditions": {
      "space_type": "挑空區",
      "ceiling_height_gt_m": 12,
      "occupancy": "none"
    }
  },
  "judgment": {
    "equipment": "火警自動警報設備",
    "decision": "exempt_with_alternatives",
    "detail": "撒水頭得免設，但需增設紅外線火焰探測器",
    "effect": {
      "remove": ["撒水頭"],
      "add": ["紅外線火焰探測器"]
    }
  },
  "source_case": "Case_20260725_Taipei",
  "status": "active",
  "created": "2026-07-25T10:00:00+08:00",
  "approved": "2026-07-25T14:30:00+08:00",
  "approved_by": "○○○",
  "governance_log": "governance/註解紀錄/PN-20260725-001.md",
  "notice": "本實務註解為消防專業人員確認之實務見解，非法規條文；援引時須同時列出所補充的法條"
}
```

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `id` | string | ✓ | `PN-YYYYMMDD-NNN`，全域唯一，須等於檔名 |
| `ref_article` | string | ✓ | 條號，如 `"19"`、`"17-1"`；必須存在於 `rules/regulation_index.json` |
| `ref_rule_ids` | string[] | ✓ | 對應 `rules/equipment_rules.json` 的 `rule.id`，不得為空 |
| `scenario.summary` | string | ✓ | 一句話摘要觸發情境 |
| `scenario.conditions` | object | ✓ | 結構化觸發條件，非空 |
| `judgment.equipment` | string | ✓ | 涉及的設備名稱 |
| `judgment.decision` | enum | ✓ | `exempt`／`exempt_with_alternatives`／`strengthen`／`replace` |
| `judgment.detail` | string | ✓ | 人類可讀的判讀說明 |
| `judgment.effect` | object | | 具體設備增減（`remove`／`add` 陣列） |
| `source_case` | string | ✓ | 來源案件名稱 |
| `status` | enum | ✓ | `active`／`superseded`／`deprecated` |
| `created` | ISO 8601 | ✓ | 建立時間 |
| `approved`／`approved_by` | | | 由 `apply` 寫入 |
| `governance_log` | string | | 追溯紀錄相對路徑，由 `apply` 寫入 |

## 工具做什麼、不做什麼

`practice_note_engine.py` 只做**可機械驗證**的檢查：

- 必填欄位、型別、`id` 格式、檔名與 `id` 一致
- `（待填）` 佔位符未填實即阻擋（嚴禁 Agent 推測填充）
- `ref_article` 在法規索引中存在、`ref_rule_ids` 在規則庫中存在
- 與既有 active 註解的條號＋觸發條件重複偵測
- `decision` 屬免除／替換類或 `effect.remove` 非空 → 🔴 紅色警示，須 `--acknowledge-conflict` 具名確認
- staging → active 必須 `--confirm 確認納入`

它**不做**法規判斷——某則註解在法規上是否成立，是消防專業人員的職責。

## 三條鐵律

1. **未經使用者「確認納入」，禁止從 staging 移到 active**（工具在程式層強制）
2. **免除法定應設設備的註解一律紅色警示**，須人工確認法源後具名記錄
3. **註解不是法源**——引用時必須同時列出所補充的法條與註解 ID，供覆核

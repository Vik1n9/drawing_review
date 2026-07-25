# 訓練模式資料夾

本資料夾是**訓練模式**（`/train`，見 `skills/training-mode.md`）的投放入口與歸檔紀錄區。

訓練＝把新法源、實務表格與實案回饋，變成**規則即程式碼＋策展筆記＋知識圖譜**。
不是 LLM 權重微調——本專案刻意不信任模型記憶（見 `skills/red-green.md`）。

## 怎麼用

1. 把要「教」給系統的檔案丟進 `training/inbox/`
2. 跑 `python3 tools/training_intake.py classify` 看路由建議（乾跑，不動檔案）
3. 逐項與使用者確認後，跑 `apply` 歸檔並建立批次
4. 依 `skills/training-mode.md` 走完先紅再綠、索引重建與圖譜重建

## 目錄語意

```
training/
├── inbox/                     — 待歸檔素材投放區（歸檔後可清空）
├── registry.json              — 訓練批次總索引；工作流程用 training_intake.py status 查詢
├── graph_pending.json         — 圖譜待重建旗標（只在自動重建失敗時存在，補建後刪除）
└── {批次名}-{YYYYMMDD}/
    ├── manifest.json          — 歸檔紀錄：每件素材的 sha256、分類理由、目的地、確認人
    ├── sources/               — 原始素材不可變副本（追溯用，不得修改）
    ├── formats/               — 格式範本類素材（無既有正典位置者）
    └── NOTES.md               — 本批次產生了哪些測試／規則／筆記，圖譜是否已重建
```

## 歸檔目的地一律是既有正典位置

`training/` **只保存原始副本與紀錄**，訓練成果本身寫進既有位置，
既有工具零修改即可吃到：

| 素材類型 | 歸檔目的地 | 誰會讀到 |
|---|---|---|
| 法規全文 md | `rules/core/` | `tools/regulation_index.py build` → 逐條 JSON → 圖譜 |
| 條文附表圖 | `rules/core/*_assets/` | 逐條 JSON 的內嵌連結、圖譜的圖表附件節點 |
| 判斷基準／函釋 PDF | `rules/core/` | `/regulation-intake` 抄錄入庫 |
| §14~31 判斷表 xlsx | `rules/checklists/` | `tools/standard_checklist_html.py`、`tools/stage_report_xlsx.py` |
| 格式範本 | `training/{批次}/formats/` ＋ `registry.json` | `training_intake.py status` 查詢 |
| 實案回饋 | 人工追加到 `rules/review_corrections.md` | 每次審圖的必讀前置 |

## 三條邊界

1. **不繞過先紅再綠**——`training_intake.py` 在程式層拒絕寫入 `rules/equipment_rules.json`、
   `rules/mixed_use_rules.json`、`rules/rule_tests.json`。法規參數一律走 `skills/red-green.md`。
2. **不自動下法規判斷**——分類只看副檔名與檔名樣式，信心不足即標 `needs_confirmation` 交人工。
   回饋筆記不得記錄未經使用者確認的推定。
3. **入庫把關靠先紅再綠，不靠事後核定**——使用者本身即為消防專業人員；把關點是
   「測試對著法條原文逐字抄錄、看著它紅得正確、再轉綠」，不是另設一道核定關卡。

## 圖譜必須跟上

規則來源檔（`rules/equipment_rules.json`、`rules/mixed_use_rules.json`、
`rules/regulation_articles/article-*.json`）一有異動，`graphify-out/` 的圖譜就過期了；
`/train` 會自動重建，並以 `python3 tools/graph_status.py stamp` 蓋章。

自動重建失敗（例如 `graphify` 未安裝且無法安裝）時會寫下 `training/graph_pending.json`，
此後每次 `training_intake.py status` 都會紅字警告，CI 的 `graph_status.py check` 也會紅燈，
直到補建並蓋章為止。

# 法規資料取用格式

`rules/法規/*.md` 是依編章切分的法規原文，供換版與人工校對使用。審查案件時不要直接載入全部 Markdown；請先用索引查詢相關條文，再只讀需要的逐條 JSON。

## 產生索引

```bash
python3 tools/regulation_index.py build
```

輸出：

- `rules/regulation_index.json`：輕量索引，只含條號、來源檔、章節、設備標籤、短摘要與逐條 JSON 路徑。
- `rules/regulation_articles/article-*.json`：每條法規一個 JSON，含完整 Markdown 原文、法規版本、章節階層、設備標籤。

## 查詢方式

```bash
python3 tools/regulation_index.py lookup --article '§14'
python3 tools/regulation_index.py lookup --article '§115-§120'
python3 tools/regulation_index.py lookup --equipment '火警自動警報設備'
python3 tools/regulation_index.py lookup --keyword '無開口樓層'
```

審查結論引用法規時，先用 `equipment_rules.json` 的 `legal_basis` 查回條文，再把查詢得到的條號與原文片段放入報告或計算記錄。找不到條文時，不可憑記憶補法規，應標記為需人工確認或先修正索引來源。

## 主從用途對照表（mixed_use_rules.json）

- 來源文件：`rules/法規/建築物主用途及從屬用途關係對照表.pdf`（內政部消防署《複合用途建築物判斷基準》附表，使用者提供）
- `rules/mixed_use_rules.json`：附表 31 項逐列結構化（`subordinate-table` 規則），供 `fire_code_calc.py classify-mixed-use` 比對主從用途**候選**；全部 `verified: false`，抄錄疑字以 `transcription_note` 標注，核定時須對照 PDF 原件
- 判斷基準**本文**（從屬認定要件與面積比例門檻）尚未提供、未入庫——量化從屬判定一律「需人工判讀」（見 README 待補事項備忘）
- `rule_tests.json` 的測試可用選填欄位 `rules_file` 指向本檔；`run-tests --strict` 與 `self-test` 會一併檢查本檔

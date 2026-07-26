# 法規資料取用格式

`rules/core/1各類場所消防安全設備設置標準.md` 是法規全文正典來源（法務部全國法規資料庫，§1~§239 共 266 條；含附表的 20 條以 `_assets/` 內的官方附件圖檔內嵌）。審查案件時不要直接載入全文 Markdown；請先用索引查詢相關條文，再只讀需要的逐條 JSON。

> 註：早期曾以「依編章切分的多個 md」維護，現已整併為單一全文正典檔。`regulation_index.py build` 會 glob `rules/core/*.md`，故此資料夾請維持**單一**法規全文 md，避免重複條文。

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

- 來源文件：`rules/core/建築物主用途及從屬用途關係對照表.pdf`（內政部消防署《複合用途建築物判斷基準》附表，使用者提供）
- `rules/mixed_use_rules.json`：附表 31 項逐列結構化（`subordinate-table` 規則），供 `fire_code_calc.py classify-mixed-use` 比對主從用途**候選**；2026-07-25 已與附表原件（PDF 文字層）逐欄核對，`verified: true`。原件錯字經校讀更正者，原印字留存於各該項 `source_text`，校讀依據記於 `transcription_note`；第（28）（29）項之原件用字維持原樣，列於 `governance/待確認清單/` 待裁示
- 各項次的三個註記欄位分工：`source_text` 留存附表原件的原印字；`transcription_note` 是 `classify-mixed-use` 比對輸出會一併帶出的**短句**（例：「更氣室」經校讀更正為「電氣室」）；`verification_note` 是完整核對紀錄（校讀依據、跨頁欄位歸屬確認），只留在檔內供追溯，不進比對輸出
- 判斷基準**本文**（從屬認定要件與面積比例門檻）尚未提供、未入庫——量化從屬判定一律「需人工判讀」（見 README 待補事項備忘）
- `rule_tests.json` 的測試可用選填欄位 `rules_file` 指向本檔；`run-tests --strict` 與 `self-test` 會一併檢查本檔

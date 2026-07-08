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

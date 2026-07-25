# Governance — 規則與註解的確認追溯鏈

規則庫中每一條 `verified: true`、以及每一則生效的實務註解，都必須能追溯到**誰在什麼時候確認的**。
本目錄保存這條追溯鏈。

本專案使用者本身即為消防專業人員，**不需另外送外部核定**——把待確認清單列給使用者逐條審核即可。
紙本簽名流程仍然保留，供需要書面紀錄的場合使用。

## 目錄結構

```
governance/
├── 核定表/          — verification_sheet.py export 產出的 HTML（僅在需要書面紀錄時用）
│   └── 核定表-{YYYYMMDD}.html
├── 核定紀錄/        — 規則確認成果
│   ├── results-{YYYYMMDD}.json          — 確認結果 JSON（apply 的輸入）
│   └── 核定表-{YYYYMMDD}-簽名掃描.pdf   — 走紙本簽名流程時才有
└── 註解紀錄/        — 實務註解追溯紀錄（practice_note_engine.py apply 自動產生）
    └── PN-{YYYYMMDD}-{序號}.md
```

## 主路徑：對話中逐條確認

```bash
# 1. 列出待確認規則（條號｜設備｜參數｜法條原文摘要）
python3 tools/verification_sheet.py list

# 2. 使用者逐條回覆「正確」或「錯誤＋更正內容」，整理成 results JSON：
#    {"verified_by": "○○○", "verified_date": "2026-07-25",
#     "results": [{"rule_id": "extinguisher-count", "result": "correct"}]}
#    使用者本人確認時 evidence 可省略。

# 3. 回填
python3 tools/verification_sheet.py apply --results governance/核定紀錄/results-{YYYYMMDD}.json

# 4. 收尾驗證
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
```

**不要把整包規則 JSON 傾印到對話裡**——`list` 已經把每條規則攤平成短行，只列使用者要判斷的內容。
條數多時分批列出。

## 備用路徑：紙本簽名流程

需要書面存證，或由未接觸本系統的第三方核定時：

```
1. export 匯出核定表 HTML ──傳送──▶ 2. 對照法條逐條勾選、簽名、寫日期
4. 謄錄成 results JSON    ◀──回傳──  3. 紙本掃描／拍照回傳
5. apply 回填（此時 evidence 填掃描檔路徑）
```

## 實務註解的追溯

`practice_notes/active/` 的每則註解在 `apply` 時自動產生 `governance/註解紀錄/{id}.md`，
記錄引用法條、來源案件、建立與批准時間、批准人、牴觸檢查結果，以及紅色警示的人工確認理由。
詳見 `practice_notes/README.md`。

## 規則

1. **`verified: true` 只能經 `apply` 產生**——不得手改 JSON 跳過確認紀錄；
   `verified_by` 與 `verified_date` 為必填，這是責任追溯的最低要求
2. **確認為「錯誤」的規則不會被工具自動修正**——參數修正必須走先紅再綠
   （先改測試 `expected` →紅→改參數→綠），修正後回到「待確認」狀態，下一輪再確認
3. **走紙本流程時**，掃描檔命名對應核定表日期，results JSON 的 `evidence` 指向掃描檔路徑
4. 修法（法規換版）時，受影響規則的 `verified` 重置為 `false`，重新走一輪確認
5. **實務註解未經使用者輸入「確認納入」，禁止從 `staging` 移到 `active`**（工具在程式層強制）

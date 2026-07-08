# Governance — 規則核定的責任追溯鏈

規則庫中每一條 `verified: true` 都必須能追溯到一份**有消防專業人員簽名的核定紀錄**。本目錄保存這條追溯鏈。

## 目錄結構

```
governance/
├── 核定表/          — verification_sheet.py export 產出的核定表 HTML（送核定用）
│   └── 核定表-{YYYYMMDD}.html
└── 核定紀錄/        — 回收的核定成果（責任追溯依據）
    ├── 核定表-{YYYYMMDD}-簽名掃描.pdf   — 消防人員簽名的紙本掃描（或照片）
    └── results-{YYYYMMDD}.json          — 架構管理者依掃描內容謄錄的結果 JSON
```

## 核定循環（消防專業人員不需接觸 GitHub / AI）

```
架構管理者                          消防專業人員
────────────────────────────────────────────────────────
1. export 匯出核定表 HTML  ──傳送──▶  2. 對照法條清單逐條勾選
   （瀏覽器開啟或列印）                 正確／錯誤＋更正值＋備註
                                        簽名、寫日期
4. 謄錄成 results JSON     ◀──回傳──  3. 紙本掃描／拍照回傳
5. apply 回填 verified
6. 「錯誤」項走先紅再綠修正
7. 簽名掃描檔存入 核定紀錄/
8. commit ＋ 開 PR（CI 自動跑測試）
```

## 對應命令

```bash
# 1. 匯出（預設只含未核定規則）
python3 tools/verification_sheet.py export

# 5. 回填（verified_by / verified_date / evidence 缺一不可）
python3 tools/verification_sheet.py apply --results governance/核定紀錄/results-{YYYYMMDD}.json

# 8. 收尾驗證
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
```

## 規則

1. **`verified: true` 只能經 `apply` 產生**——不得手改 JSON 跳過核定紀錄
2. **核定為「錯誤」的規則不會被工具自動修正**——參數修正必須走先紅再綠（先改測試→紅→改參數→綠），修正後的規則回到「未核定」狀態，下一輪核定表再送核定
3. **掃描檔命名對應核定表日期**，results JSON 的 `evidence` 欄位指向掃描檔路徑
4. 修法（法條清單換版）時，受影響規則的 `verified` 重置為 `false`，重新走一輪核定循環

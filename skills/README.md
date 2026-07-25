# 兩階段審查工作流程——設計說明

本檔是**說明文件，不會被 skill 載入**。`skills/*.md` 與 `rules/*.md` 只放執行時需要的指令，
所有背景、理由與維護規範集中在這裡。

對應檔案：

| 檔案 | 執行時載入 | 內容 |
|------|:---:|------|
| `skills/first-stage-review.md` | ✅ | 第一階段執行指令 |
| `skills/stage-two-review.md` | ✅ | 第二階段執行指令 |
| `rules/review_corrections.md` | ✅ | 累積確認的通案修正條目 |
| `rules/stage_two_judgment_rules.md` | ✅ | §14~31 判斷差異 |
| `rules/article18_equipment_options.json` | ✅ | §18 各款可選設備對照 |
| `skills/README.md`（本檔） | ❌ | 設計說明、維護規範 |

---

## 一、兩階段與既有 pipeline 的對應

兩階段是**既有流程的包裝**，不是平行的第二套系統。內容與交付物 3、4 同源，
都以 `case.json` 為正典，差別只在交付格式為 Excel 工作簿。

### 第一階段

| 步驟 | 執行 | 產物 |
|------|------|------|
| 1. 收件與逐層萃取、證照文件萃取 | `/plan-intake` | `case.json` 草稿 |
| 2. §12 分類與主從用途定案（人工確認關卡） | `/mixed-use-review` | `case.json` 定案 |
| 3. 受控自動化關卡 | `tools/case_facts_gate.py --stage first` | ready／阻擋問題 |
| 4. 交付物產出 | `mixed_use_report.py` ＋ `stage_report_xlsx.py first-stage` | HTML ＋ Excel |

### 第二階段

| 步驟 | 執行 | 產物 |
|------|------|------|
| 1. §13 新舊標準適用判斷、門檻計算 | `/code-requirements` | 應設設備清單＋計算記錄 |
| 2. §14~31 逐條窮舉 | `tools/article_checklist.py` | `check_results.json` |
| 3. 受控自動化關卡 | `tools/case_facts_gate.py --stage second` | ready／阻擋問題 |
| 4. 人工定案勾選 | 人工填 `stage2_decisions.json` | 判斷結果 |
| 5. 交付物產出 | `checklist_html.py` ＋ `stage_report_xlsx.py stage-two` | HTML ＋ Excel |

---

## 二、為什麼規則庫不存條文原文與門檻數值

`rules/stage_two_judgment_rules.md` 刻意**不轉抄任何法條文字或門檻數值**。

原因是實測到的錯誤：本工作流程套件匯入時，規則檔中轉抄的法條與官方條文比對後出現三處
實質偏差——把「一千平方公尺**以上**」寫成「**超過**一千平方公尺」、漏列 §28 第 1 款的
戊3 與面積門檻、漏列 §24 第 3 款的「居室（學校教室除外）」限定。轉抄的複本會隨修法漂移，
而且漂移不會有人發現。

因此規則庫只保留**條文本身讀不出來的判斷差異**：容易誤讀的結構、範圍界定、預設值、
證據要求、輸出慣例。條文文字一律即時回查。

### 撰寫規範（新增或修改判斷規則時）

- **不得寫入條文原文或門檻數值。** 要表達「某個量算錯了」時，用**主詞與範圍**描述
  （「門檻的主詞是各居室，不是整棟」），不要寫死數字。
- 例外：刻意記錄的**錯誤值**可以寫（如「曾誤用 2,000 ㎡ 的整棟量」），因為它記的是
  已知誤判，不是法定門檻。
- 每則規則必附條號。引用不到條號的判斷降級為「建議事項」並標明無法源依據。
- 與條文字面可能有出入的解釋標 **⚠️ 待確認解釋**，套用前向使用者確認。
- 操作規則（執行順序、交叉核對、備註欄位、工作簿格式）一律以 `skills/*.md` 為準，
  規則庫不重複記載——兩份複本同樣會漂移。
- 法規換版後，判斷差異須逐條複核是否仍成立；條文文字本身由 `/regulation-intake` 與
  `/graphify rules` 更新，不必動規則庫。

---

## 三、法條調閱：先定位，再載入

```
圖譜（定位牽涉哪幾條）→ 索引（只載入那幾條原文）→ fire_code_calc（門檻與數量）→ 判斷
```

§14~§31 全文一次載入約 1.5 萬字；用圖譜定位後只載相關條，典型情況 3~4 千字，
`neighbors` 查詢本身僅約 0.5 千字。除了省 context，先定位也降低看錯條的機率。

```bash
python3 tools/regulation_graph.py neighbors --article §24        # 該條引用網＋附表圖檔＋實務註解
python3 tools/regulation_graph.py articles --equipment 排煙設備   # 哪些條文規範該設備
python3 tools/regulation_graph.py path --from 無開口樓層 --to 排煙設備
python3 tools/regulation_graph.py notes --article §24            # 專查該條的實務註解
python3 tools/regulation_index.py lookup --article '§24,§12'     # 逗號列舉／範圍皆可
```

圖譜含**兩層**：法典層（`rules/core/` 走 `/graphify rules`）與註解層
（`practice_notes/active/` 走 LLM 語意抽取 ＋ `tools/practice_note_graph.py merge`）。
查詢結果中的實務註解是**實務見解、非法規條文**，援引須同時列出所補充的法條與註解 ID。

`tools/regulation_graph.py` 只用標準庫直接讀 `graphify-out/graph.json`，**不需安裝 graphify**；
輸出會附上可直接貼用的 `lookup` 指令。裝了 graphify 時另可用 `graphify query/explain/path`。

**邊界（審圖最高原則 2、4）**：圖譜只是索引與導覽，不是門檻數值或計算結果的來源。
節點標題不得當作法規數值使用；應設／免設判斷與數量計算一律以 `tools/fire_code_calc.py`
＋人工確認後的 `case.json` 為準。

---

## 四、`rules/review_corrections.md` 的維護

該檔記錄**使用者（消防專業人員）已明確確認、可供未來案件重用的修正**。

### 法律位階

記載的是實務判斷慣例與輸出格式約定，**不是法條原文**。涉及法規解釋的條目已附條號；
該檔尚未經 `governance/` 核定流程簽署，等同 `verified: false`，援引其做成的結論輸出時
須附警語「本判斷慣例未經消防專業人員核定，以現行法規為準」。
`rules/stage_two_judgment_rules.md` 與 `rules/article18_equipment_options.json` 同此。

### 條目格式

```
### YYYY-MM-DD — 簡短標題

- Status: Active
- Last confirmed: YYYY-MM-DD
- Error: 原本錯誤的判斷或輸出方式。
- Correction: 使用者確認的正確做法。
- Scope: 適用的案件、文件、欄位或條件。
- Evidence: 使用者提供的依據；未提供外部依據時填「使用者明確確認」。
- Notes: 必要的例外或與其他條目的關係；無則填「無」。
```

### 增修規則

- **不得刪除既有條目。** 新規則以追加方式建立；相同規則僅更新 `Last confirmed`，
  並補充新增的適用範圍或依據。
- 新規則取代舊規則時，先追加新條目，再**僅修改**舊條目的 `Status` 與 `Notes`，
  標記為 `Superseded` 並指向新條目。
- 不得加入猜測、暫定建議、未解決的疑問，或未經使用者確認即推定的修正。
- 不記錄姓名、地址或非必要案件識別資料。
- 記錄新條目後簡短告知使用者。

---

## 五、移植自外部套件時的調整

本工作流程originally 在 Windows／Codex 環境執行，移入本專案時做了以下調整：

| 項目 | 原版 | 本專案 | 原因 |
|------|------|--------|------|
| 檔名 | `yyyy-MM-dd HH-mm_XXX.xlsx` 時間戳 | `{案件名}-XXX.xlsx` 固定檔名 | 輸出目錄 `output/` 已含日期；固定檔名重跑即覆蓋，符合「只保留最後確認正式版」的修正條目 |
| 案件資料夾 | `01_審圖所需文件/`、`04_審圖結果輸出/` | `input/{案件名}/`、`output/` | 對齊專案的統一輸入／輸出契約 |
| Excel 產生 | `@oai/artifact-tool`（Node） | `openpyxl`（`tools/stage_report_xlsx.py`） | 原依賴為 Codex 內建套件，本環境不可用 |
| 事實關卡 | 另建 `tmp/{案件名}-case-facts.json` | 直接讀 `case.json` | 最高原則 4：正典資料是 `case.json`，不另建平行事實檔 |
| §12 款目缺漏 | 只印分類代碼 | 標「⚪需人工判讀：§12 款目未載」 | 最高原則 1：法條可追溯 |
| §18 條文轉錄 | 散在 SKILL.md、mjs、xlsx 三處 | 僅 `rules/article18_equipment_options.json` | 多份複本會隨修法漂移 |

`rules/checklists/` 的法條判斷表已更新為含第 18 條完整 9 款的版本；原專案版本缺 §18，
`tools/stage_report_xlsx.py` 保留自規則檔補入的安全網。

### 待複核事項

「所有地上樓層一律列為`無開口樓層`」是通案樓層屬性規則，會改變 §14~31 的判斷基礎。
目前將其適用範圍限定在兩階段工作流程，**未**擴及專案原本的 `/code-requirements` 路線。
此範圍界定尚待消防專業人員確認。

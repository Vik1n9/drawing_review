# 訓練模式（法規知識注入＋實案回饋學習）

對 $ARGUMENTS（訓練批次名，例如「第18條附表補件」「主從用途判斷基準」）執行一次完整訓練：
把使用者投放到 `training/inbox/` 的素材確定性歸類到既有正典位置，走先紅再綠把法規參數入庫、
依既有格式追加實案回饋筆記，最後重建法規索引與知識圖譜，讓後續工作流程自動調用得到這次的訓練結果。

**訓練不是模型微調。** 本專案刻意不信任模型記憶（見 `skills/red-green.md`）；
訓練成果的載體是**規則即程式碼 ＋ 策展 markdown ＋ 知識圖譜**，全部可追溯、可重跑、可覆核。

## 前置檢查

1. 讀 `rules/review_corrections.md` 全文——已確認的通案修正是本次訓練的既有事實，不得與之衝突
2. 讀 `skills/red-green.md`——本次若要動任何法規參數，紀律以該檔為準，無例外
3. 跑 `python3 tools/training_intake.py status`——確認起點狀態（現有批次、現有實務註解數、圖譜新鮮度）
4. `training/inbox/` 有素材，或使用者以口述提供實案回饋；兩者皆無則本次無事可訓練，直接結束

## 執行流程

| 步驟 | 執行 | 產物 |
|------|------|------|
| 一 | 讀前置檢查的兩份文件 | 紀律前提 |
| 二 | `training_intake.py classify` → 逐項確認 | 確認後的路由表 |
| 三 | `training_intake.py apply` | `training/{批次}/` ＋ 歸檔到正典位置 |
| 四 | 法源類 → `skills/regulation-intake.md` ＋ `skills/red-green.md` | 新測試＋新規則 |
| 五 | 回饋類 → `/practice-note`（結構化）或追加 markdown 筆記 | `practice_notes/active/` ／ `review_corrections.md` 新條目 |
| 六 | `regulation_index.py build` | 重建逐條索引 |
| 七 | 自動重建圖譜 ＋ 併入實務註解層 ＋ 蓋章 | 新 `graphify-out/` ＋ `source_fingerprint.json` |
| 八 | `self-test` ＋ `run-tests --strict` | 綠燈驗收 |
| 九 | 回填 `NOTES.md`／`manifest.json`，總結本次學到什麼 | 批次收尾 |

不重造輪子：第四步完全委派既有的 `/regulation-intake` 與先紅再綠流程，第五步沿用
`rules/review_corrections.md` 自訂的筆記格式與使用規則。本 skill 只負責把它們串成一次可交付的訓練。

### 第一步 建立紀律前提

讀完 `rules/review_corrections.md` 與 `skills/red-green.md` 後，向使用者一句話覆述本次要訓練什麼、
預期會動到哪些正典檔案。使用者未確認範圍前不要開始搬檔案。

### 第二步 分類（乾跑，不動任何檔案）

```bash
python3 tools/training_intake.py classify
```

輸出每件素材的 `kind`／`destination`／`reason`／`needs_confirmation`。分類是**確定性**的
（只看副檔名、檔名樣式與輕量內容探測），不做任何法規解讀。

**逐項與使用者確認**標記 `⚠️ 需人工確認` 的項目。特別注意兩類：

- `regulation-fulltext`：**永遠需要確認**。`regulation_index.py build` 會 glob `rules/core/*.md`，
  該資料夾必須維持**單一**法規全文 md（見 `rules/README.md`）。新全文是「替換」不是「並存」——
  確認要替換哪一份，且替換後全部 266 條逐條 JSON 都會重建。
- `unknown`：不要猜。問使用者這份檔案是什麼、該歸到哪裡，或先擱置在 `sources/unclassified/`。

確認時**在對話中列出簡短清單即可**（檔名｜判定類型｜要放到哪），不要把整包 classify JSON
傾印給使用者看。使用者確認後，把 `classify --format json` 的輸出存成路由表，
為每個 `needs_confirmation` 項加上 `"confirmed_by": "{使用者}"`，作為第三步的 `--plan`。

### 第三步 歸檔

```bash
python3 tools/training_intake.py apply --batch "{批次名}" --operator "{歸檔人}" \
  --plan {確認後的路由表.json}
```

工具會：把原始素材複製一份到 `training/{批次}-{YYYYMMDD}/sources/`（不可變，追溯用）、
再複製到正典目的地、寫 `manifest.json`（含每件 sha256、分類理由、確認人）與 `NOTES.md`、
更新 `training/registry.json`。

**工具在程式層拒絕**把素材寫進 `rules/equipment_rules.json`、`rules/mixed_use_rules.json`、
`rules/rule_tests.json`、`rules/regulation_articles/`、`governance/`、`input/`、`output/`。
出現這類阻擋不是工具壞掉，是流程走錯——法規參數要走第四步，不是複製檔案。

### 第四步 法規參數入庫（先紅再綠，無例外）

只要本次訓練要讓系統「多會判斷一條法規」，就走 `skills/regulation-intake.md` ＋ `skills/red-green.md`：

1. **RED**：在 `rules/rule_tests.json` 新增測試，`expected` 對著本次歸檔的法條原文**逐字抄錄**，
   `source.pdf` 指向 `rules/core/` 內的來源檔，`source.page` 與 `source.quote` 必填
2. **Verify RED**：`python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}`——
   必須看著它 FAIL（不是 INVALID）
3. **GREEN**：只把讓該測試轉綠所需的最小參數寫入 `rules/equipment_rules.json`，附 `legal_basis` 條號
4. **Verify GREEN**：`python3 tools/fire_code_calc.py run-tests --strict`——轉綠且沒弄破其他測試

把測試 ID 與規則 ID 回填到本批次 `NOTES.md` 的下游產物清單。

紅旗：使用者說「這條很簡單直接寫參數就好」——回 `skills/red-green.md` 的鐵律，不得妥協。

### 第五步 實案回饋學習（三個去處，依回饋性質分流）

使用者指出某次審查結果錯誤、並提供或確認正確做法時，順序固定：
**先把修正套用到當前工作 → 再記錄 → 簡短告知使用者已記錄**。

記錄到哪裡，看回饋的性質：

| 回饋性質 | 去處 | 途徑 |
|---|---|---|
| **法典未涵蓋的個案情境判讀**（某條號＋某情境該怎麼判） | `practice_notes/` | `/practice-note`（結構化 JSON，後續案件由 `check-gap` 自動比對命中） |
| **通案性工作流程修正**（樓層屬性通案、文件欄位、交付物格式…） | `rules/review_corrections.md` | 依既有筆記格式追加 |
| **§14~31 逐款判斷慣例** | `rules/stage_two_judgment_rules.md` | 依既有逐條結構追加 |

判斷準則：**回饋若能表述成「§X 的 Y 情境 → Z 判讀」，就走 `/practice-note`**——
結構化後下一個案件會自動命中，比自由文字筆記可靠。
無法掛在特定條號上的（格式、欄位、流程），才寫 markdown 筆記。

若使用者的回饋其實是「這條法規我們沒入庫」，回第四步走先紅再綠，不要用註解或筆記繞過。

markdown 筆記依 `rules/review_corrections.md` 自訂的格式追加（`Status` / `Last confirmed` /
`Error` / `Correction` / `Scope` / `Evidence` / `Notes`），並遵守該檔的使用規則：

- **既有筆記永遠不刪**。要取代舊規則時，追加新筆記，只把舊筆記的 `Status` 改為 `Superseded`
  並在 `Notes` 指向新筆記
- **不得記錄未經使用者確認的推定**；使用者沒給外部依據時，`Evidence` 填「使用者明確確認」
- 不寫姓名、地址與非必要的案件識別資訊

這兩份筆記與實務註解都是**實務判斷慣例，不是法規條文**。使用者本身即為消防專業人員，
其確認就是專業判斷的表示；但援引其結論時，必須同時列出所補充的法條（與註解 ID），
讓覆核者能回溯到條文本身。

### 第六步 重建法規索引

`rules/core/` 有任何變更（新全文、新附表圖、新判斷基準文件）時：

```bash
python3 tools/regulation_index.py build
```

重建 `rules/regulation_index.json` 與 `rules/regulation_articles/article-*.json`。
沒動到 `rules/core/` 就跳過這步，並在 `NOTES.md` 註明「本批次未變更法規全文」。

### 第七步 自動重建知識圖譜（本 skill 的核心保證）

```bash
python3 tools/graph_status.py check
```

結束碼 `0`＝新鮮（跳過重建）、`2`＝過期、`3`＝尚未建立指紋基準。

結束碼 `2` 有兩種成因，處理方式不同——訊息會直接寫明是哪一種：

- **來源檔異動**（`已過期`）→ 重建圖譜（下方）
- **實務註解未納入**（`註解未納入`）→ 只需補做註解層合併（下方第 3 行起）

過期或無基準時，**自動**執行重建，不要等使用者開口：

```bash
/graphify rules --update      # 增量：只重抽變更條文（一般情況）
/graphify rules               # 大改：法規換版、全文替換時
python3 tools/practice_note_graph.py plan     # 註解層：0=齊備 2=有待語意抽取
python3 tools/practice_note_graph.py merge    # 把實務註解併回圖譜
python3 tools/graph_status.py stamp
```

**`/graphify rules` 只掃 `rules/`，而且會覆寫 `graph.json`**——重建等於把實務註解層沖掉，
所以每次重建後都必須重跑 `practice_note_graph.py merge`。`plan` 回報有待抽取的註解時，
依 `skills/practice-note.md` 第七步做 LLM 語意抽取後再 merge；
註解沒併回去，`graph_status.py stamp` 會拒絕蓋章（避免蓋出查不到註解的假綠燈）。

法規是文字語料，必須走 skill 的語意抽取（子代理依編/章切塊）；CLI 的 `graphify update`
（純 AST、免 LLM）**不適用**於法條語意圖譜。跨塊抽取後須以 `graphify.ids.make_id`
統一正規化 node id（條號感知）再合併，避免共用概念無法去重。

**降級路徑（不得靜默跳過）**：`graphify` 未安裝時先試 `bash tools/setup.sh --with-graph`；
仍失敗（離線、無安裝權限）則：

1. 寫 `training/graph_pending.json`，記錄批次名、日期、待重建原因與待重建的來源檔清單
2. 在本批次 `NOTES.md` 的圖譜項目保留未勾選狀態並註明原因
3. **明確告知使用者**：「圖譜自動重建失敗，下次工作前必須補建，否則查圖譜會查到舊資料」

此後每次 `training_intake.py status` 都會紅字警告、CI 的 `graph_status.py check` 也會紅燈，
直到補建並 `stamp` 為止。補建完成後刪除 `training/graph_pending.json`。

圖譜的邊界不因訓練而改變：**它只是索引與導覽，不是門檻數值或計算結果的來源**
（呼應 `AGENTS.md` 底線 1「禁止憑記憶引法規數值」與底線 2「case.json 是正典」）。

### 第八步 綠燈驗收

```bash
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/practice_note_engine.py test --strict
python3 -m unittest discover tests
```

任一紅燈：**本批次不得收尾**。修參數（不是修測試），除非重查原文發現當初抄錄錯誤——
此時修 `quote` 與 `expected` 並重走 Verify RED。

### 第九步 收尾

1. 回填本批次 `NOTES.md`：新增的測試 ID、規則 ID、筆記日期標題、索引與圖譜是否已重建
2. 更新 `training/{批次}/manifest.json` 的 `downstream` 欄位與 `training/registry.json`
   的 `graph_rebuilt`
3. 本批次若新增或改動規則，**直接在對話中列給使用者逐條確認**：

```bash
python3 tools/verification_sheet.py list
```

把輸出整理成對話中的簡短清單（條號｜設備｜關鍵參數｜法條原文摘要），請使用者逐條回覆
「正確」或「錯誤＋更正內容」。使用者本身即為消防專業人員，**不需另外送外部核定**。

- **不要傾印整包 JSON 或整份規則庫**到對話裡——只列出他要判斷的那幾行
- **不要主動匯出 HTML 核定表**（`export` 只在使用者明確要求書面紀錄時才跑）
- 條數多時分批列出，一次不超過使用者能一眼看完的量

使用者回覆後回填：

```bash
python3 tools/verification_sheet.py apply --results {結果JSON}
# 結果 JSON 只需 verified_by、verified_date、results[]；使用者本人確認時 evidence 可省略
```

判為「錯誤」的項目**不自動改參數**——回第四步走先紅再綠（先改測試 `expected` 轉紅，再改參數轉綠）。

4. 向使用者總結：這次系統「多學會了什麼」、哪些條號從此判得出結論、
   哪些仍是「需人工判讀」、圖譜是否已跟上

## 後續工作流程如何調用訓練結果

不需要特別做什麼——訓練成果都落在既有正典位置：

| 訓練成果 | 落點 | 誰自動讀到 |
|---|---|---|
| 法規全文／附表圖 | `rules/core/` → `rules/regulation_articles/` | `tools/regulation_index.py lookup`、知識圖譜 |
| 法規參數 | `rules/equipment_rules.json` | `fire_code_calc.py check-threshold` 等全部子指令 |
| 主從用途對照 | `rules/mixed_use_rules.json` | `fire_code_calc.py classify-mixed-use` |
| §14~31 判斷表 | `rules/checklists/` | `standard_checklist_html.py`、`stage_report_xlsx.py` |
| 實務註解 | `practice_notes/active/` ＋ `index.json` ＋ 圖譜註解層 | `fire_code_calc.py check-gap` 自動比對命中；`regulation_graph.py notes／neighbors／articles` 查得到（需先語意抽取並 `practice_note_graph.py merge`） |
| 通案修正筆記 | `rules/review_corrections.md` | `/first-stage-review`、`/stage-two-review` 的必讀前置 |
| 逐款判斷慣例 | `rules/stage_two_judgment_rules.md` | `/stage-two-review`、`tools/case_facts_gate.py` |
| 格式範本 | `training/{批次}/formats/` ＋ `registry.json` | `training_intake.py status` |
| 條號關聯導覽 | `graphify-out/graph.json` | `tools/regulation_graph.py neighbors／articles／path／notes`（免安裝） |

各 pipeline skill 的前置檢查會跑 `python3 tools/training_intake.py status`
（結束碼 `2` ＝ 圖譜未跟上規則庫），確保開場就知道有沒有新訓練成果、圖譜是否可信。

## 重要注意事項

1. **訓練不得繞過先紅再綠**——這是本專案的防幻覺核心。訓練模式讓入庫更順，不讓入庫更鬆
2. **入庫把關靠先紅再綠，不靠事後核定**——使用者本身即為消防專業人員；
   把關點是「測試對著法條原文逐字抄錄、看著它紅、再轉綠」，不是另設一道核定關卡
3. **不得記錄未經確認的推定**——回饋筆記只寫使用者明確確認過的內容
4. **既有筆記不刪**——取代靠 `Superseded` 標記，歷史是責任追溯的一部分
5. **圖譜過期即告知**——寧可吵，不要讓後續案件靜默地查到舊圖譜
6. `input/` 只讀不改；訓練素材投 `training/inbox/`，產出寫 `training/` 與 `rules/`
7. 遵守 `AGENTS.md` 五條底線；本 skill 的任何步驟與底線衝突時，以底線為準

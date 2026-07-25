# 實務註解（法典未涵蓋情境的補充見解）

對 $ARGUMENTS（案件名）執行實務註解流程：找出法典（`rules/`）給不出應設／免設的情境，
把使用者確認的實務見解結構化為 Practice Note 存入 `practice_notes/`，供後續案件自動比對調用。

觸發時機：使用者說「把這個見解納入實務補充」「這種情況我們實務上是這樣處理」，
或審查中出現 `check-threshold` 判「需人工判讀」而使用者當場給了判讀結論。

**你的任務是協助使用者「註解法典」，不是「修改法典」。**
偵測到案件結論與既有法典有出入時，必須優先假設是「實務補充情境」，草擬 Practice Note 供審閱；
若查證後發現是條文根本沒入庫，那是 `/regulation-intake` ＋ `skills/red-green.md` 的事，不是註解的事。

## 前置檢查

1. `case.json` 已人工確認，且已跑過 `/code-requirements`
2. 讀 `practice_notes/README.md` 的 Schema 與三條鐵律
3. `python3 tools/practice_note_engine.py test --strict` 綠燈（既有註解庫一致）

## 執行流程

### 第一步 找出法典缺口

```bash
python3 tools/fire_code_calc.py check-gap \
  --case output/case.json \
  --output output/gap_candidates.json
```

輸出每個「需人工判讀」的門檻結果，並比對 `practice_notes/index.json`：
`suggested_action` 為 `reuse_practice_note`（已有註解涵蓋）或 `draft_practice_note`（無）。

### 第二步 先排除「規則未入庫」

**這步不可跳過。** gap candidate 只表示既有規則庫給不出結論，**不表示法規真的沒規定**。
逐項查證：

```bash
python3 tools/regulation_graph.py neighbors --article §17   # 先定位：該條引用網與關聯條號
python3 tools/regulation_index.py lookup --article '§17'    # 再載入：只讀相關條文原文
```

- 條文**有**規定但規則未入庫 → 停止本流程，改走 `/regulation-intake` ＋ `skills/red-green.md` 入庫。
  註解不能拿來補法典的懶。
- 條文**確實未涵蓋**此情境（實務上以但書、解釋令或個案協商處理）→ 繼續第三步。

向使用者說明查證結果：「§17 查得的條文只規範 X，本案的 Y 情境無條文可套用。是否草擬實務註解？」

### 第三步 草擬

```bash
python3 tools/practice_note_engine.py draft \
  --gap output/gap_candidates.json \
  --case "{案件名}" --rule-id {指定的 rule_id}
```

產出 `practice_notes/staging/PN-{日期}-{序號}.json`，判讀欄位一律是 `（待填）`。

**逐欄與使用者確認並填實**，嚴禁自行推測填充（`CLAUDE.md` 最高原則 5）。
確認時在對話中直接問那幾個欄位就好，**不要把整份草案 JSON 傾印給使用者**：

- `scenario.conditions`：把使用者口述的情境結構化成可比對的鍵值（如
  `{"space_type": "挑空區", "ceiling_height_gt_m": 12, "occupancy": "none"}`）。
  鍵名要能讓下一個案件命中——太籠統會誤命中，太細會永遠命不中
- `judgment.decision`：`exempt`／`exempt_with_alternatives`／`strengthen`／`replace` 擇一
- `judgment.detail`：使用者的原話為準；有法源（但書、解釋令、函釋字號）一併寫入
- `judgment.effect`：具體的設備增減

### 第四步 牴觸檢查

```bash
python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/{id}.json
```

結束碼 `2` ＝ 有阻擋問題（欄位缺漏、`（待填）` 未填、引用的條號或規則不存在、與既有註解完全重複），
**停止並修正**，不得續行。

出現 🔴 紅色警示（註解免除或替換法定應設設備）時：**停止並等待使用者明確指示**。
向使用者說明「本註解會免除 §X 要求的 Y 設備，法典本身仍要求設置」，請其提供免除的法源。
使用者未給出法源前，不要 apply。

### 第五步 套用（需使用者「確認納入」）

使用者輸入**「確認納入」**四字後才可執行：

```bash
python3 tools/practice_note_engine.py apply \
  --draft practice_notes/staging/{id}.json \
  --approved-by "{批准人}" \
  --confirm 確認納入 \
  --acknowledge-conflict "{有紅色警示時，記錄確認理由與法源}"
```

工具會：搬到 `active/`、寫 `approved`／`approved_by`、產生
`governance/註解紀錄/{id}.md` 追溯紀錄、重建 `practice_notes/index.json`。

**嚴禁**在使用者說出「確認納入」以外的話時代為套用；工具的 `--confirm` 關卡是最後防線，不是可繞過的形式。

### 第六步 迴歸驗收

```bash
python3 tools/practice_note_engine.py test --strict
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
```

三者全綠才算完成，接著做第七步（圖譜納入）。

### 第七步 語意抽取並併入知識圖譜（本步驟不得省略）

註解是新的知識節點。**沒有做完這步，後續案件查圖譜就查不到這則訓練成果**——
`/graphify rules` 只掃 `rules/`，不會把 `practice_notes/` 抽進圖譜。

註解的 `scenario.summary`／`judgment.detail` 是自由文字、沒有固定格式，
「這則註解牽涉哪些概念、關聯到哪些既有條文與設備」**只能靠語意理解抽取**——
關鍵字比對會漏抽也會誤抽。所以這步由**你（LLM）做語意抽取**，工具只負責確定性合併。

```bash
python3 tools/practice_note_graph.py plan          # 0=齊備 2=有待抽取
python3 tools/practice_note_graph.py contract --note {註解 id}
```

`contract` 會印出註解原文、可用的關聯類型與輸出格式。依它產出抽取檔
`practice_notes/graph_extractions/{註解 id}.json`：

- `concepts[]`——從註解讀出的概念（觸發條件、設備、場所用途…）。
  名稱用**審圖時會拿來查的詞**（「挑空區」而非「本案特殊空間」），
  `rationale` 必須引註解原文，說明這個概念是從哪句話讀出來的
- `edges[]`——註解與圖譜節點的關聯，`target` **優先用既有節點 label**
  （先跑 `regulation_graph.py neighbors --article §X` 查既有節點名稱，
  能掛既有節點就不要新造概念，否則會長出查不到的孤島）：
  `supplements`（補充條文）／`concerns_equipment`（涉及設備）／
  `applies_when`（觸發條件）／`conceptually_related_to`（語意關聯）
- **只抽註解真的說了的東西**。不確定就不要抽——寧可少一條邊，
  不可讓圖譜長出註解沒說過的關聯（`CLAUDE.md` 最高原則 5）

```bash
python3 tools/practice_note_graph.py validate --extraction practice_notes/graph_extractions/{id}.json
python3 tools/practice_note_graph.py merge         # 冪等，可重複執行
python3 tools/graph_status.py check                # 應為 ✅ 新鮮 ＋ 實務註解已納入
python3 tools/graph_status.py stamp
```

工具的把關（都會擋下，不要繞過）：

- 抽取檔以 `note_sha256` 綁定當時的註解內容——**註解改了就必須重新語意抽取**，
  否則 `merge` 拒絕合併、`check` 標「過期」
- `concepts` 與 `edges` 全空、`rationale` 留白、`target` 在圖譜與 concepts 都找不到 → 驗證不過
- 有任何 active 註解沒抽取 → `merge` 整批拒絕、`graph_status.py stamp` 拒絕蓋章
  （避免蓋出「燈是綠的但註解不在圖譜裡」的假綠燈）

無法完成時**不得靜默跳過**：寫 `training/graph_pending.json` 並明確告知使用者
「本註解尚未併入圖譜，後續案件查圖譜查不到它」。

### 第八步 回報使用者

回報：註解 ID、涵蓋的條號與情境、`index.json` 現有註解數、**圖譜納入狀態**
（`practice_note_graph.py check` 的結果）與抽出的概念、關聯條號。

## 後續案件如何自動調用

三條路都會通到同一則註解：

- **check-gap**：每次都會比對 `practice_notes/index.json`，命中即標 `reuse_practice_note` 並列出摘要
- **索引直查**：`index.json` 提供 `by_article`／`by_equipment`／`by_rule_id` 三種查法
- **圖譜查詢**（第七步併入後才有）：
  ```bash
  python3 tools/regulation_graph.py notes --article §19        # 該條的實務註解
  python3 tools/regulation_graph.py notes --equipment 排煙設備   # 該設備的實務註解
  python3 tools/regulation_graph.py neighbors --article §19    # 條文引用網會一併帶出註解
  ```

審查報告引用註解時，**必須**同時列出所補充的法條與註解 ID，供覆核者回溯到條文與當初的判讀理由。

## 重要注意事項

1. **註解只補充、不推翻法典**——免除法定設備一律紅色警示，須具名確認法源
2. **未經「確認納入」不得 staging → active**——這是使用者的決定權，不是 Agent 的
3. **不得推測填充判讀欄位**——`（待填）` 必須由使用者填實
4. **先排除「規則未入庫」**——能走先紅再綠入庫的，就不該用註解繞過
5. **註解不是法源**——使用者的「確認納入」即為專業判斷，不另設核定關卡；
   但援引時必須同時列出所補充的法條與註解 ID，讓結論可回溯到條文
6. 修訂既有註解：新增一則並把舊註解 `status` 改為 `superseded`，不刪除歷史
7. 遵守 `CLAUDE.md` 的審圖最高原則；任何步驟與最高原則衝突時，以最高原則為準

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
  --case output/{案件名}-{日期}/case.json \
  --output output/{案件名}-{日期}/gap_candidates.json
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
  --gap output/{案件名}-{日期}/gap_candidates.json \
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

三者全綠才算完成。回報使用者：註解 ID、涵蓋的條號與情境、`index.json` 現有註解數。

### 第七步 提醒更新圖譜

註解是新的知識節點。本次若新增了 active 註解：

```bash
python3 tools/graph_status.py check
```

過期則依 `skills/training-mode.md` 第七步自動重建圖譜並 `stamp`；
無法重建時寫 `training/graph_pending.json` 並明確告知使用者。

## 後續案件如何自動調用

- `check-gap` 每次都會比對 `practice_notes/index.json`，命中即標 `reuse_practice_note` 並列出註解摘要
- `index.json` 提供 `by_article`／`by_equipment`／`by_rule_id` 三種查法
- 審查報告引用註解時，**必須**同時列出所補充的法條與註解 ID，供覆核者回溯到條文與當初的判讀理由

## 重要注意事項

1. **註解只補充、不推翻法典**——免除法定設備一律紅色警示，須具名確認法源
2. **未經「確認納入」不得 staging → active**——這是使用者的決定權，不是 Agent 的
3. **不得推測填充判讀欄位**——`（待填）` 必須由使用者填實
4. **先排除「規則未入庫」**——能走先紅再綠入庫的，就不該用註解繞過
5. **註解不是法源**——使用者的「確認納入」即為專業判斷，不另設核定關卡；
   但援引時必須同時列出所補充的法條與註解 ID，讓結論可回溯到條文
6. 修訂既有註解：新增一則並把舊註解 `status` 改為 `superseded`，不刪除歷史
7. 遵守 `CLAUDE.md` 的審圖最高原則；任何步驟與最高原則衝突時，以最高原則為準

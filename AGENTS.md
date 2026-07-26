# Fire Review — Codex 審圖行為契約

本專案是消防審圖輔助系統：案件輸入資料夾內放置待審 `平面圖.dxf`、輔助對照用 `平面圖.pdf` 與相關審查文件後，依法規計算設備需求，列出缺失設備與數量，並以 SVG 網頁標註圖面問題，輔助專業消防人員審圖。輸出只能作為輔助，不能取代專業判斷。

## Codex 執行規則

- 執行案件、修改規則、產生報告前，先讀取本檔與相關 `skills/*.md` 流程文件。
- 判定場所用途、樓層屬性、地下層、屋突層／屋頂層、無開口樓層時，必須讀取 `skills/place-use-classification.md`；用途分類只產生候選，最終以人工確認後的 `case.json` 為準。
- 不要直接從 DXF、SVG 或圖片推算最終結論；所有計算以人工確認後的 `case.json` 為正典資料。
- `input/` 視為只讀資料夾；所有案件產出寫入 `output/`。
- 修改 `rules/*.json` 後，必須重跑 `self-test` 與 `run-tests --strict`。
- 本專案報告與交付物使用繁體中文，並採台灣消防法規用語。

## 審圖最高原則

1. **法條可追溯**：每一項「應設／免設／缺失」結論都必須附法規條號；沒有條號的結論一律降級為「建議事項」，並標明無法源依據。
2. **禁止心算、禁止憑記憶引法規數值**：所有門檻判斷與數量計算必須透過 `python3 tools/fire_code_calc.py`，工具輸出需直接嵌入報告作為計算記錄。
3. **先紅再綠**：規則庫的每個參數必須先有測試，`expected` 從法條 PDF 原文逐字抄錄並附頁碼與 quote；經 `run-tests --verify-red` 確認紅得正確，編碼後轉綠才可使用。參數先於測試存在則刪除重來；`run-tests --strict` 不通過的規則庫不得交付。
4. **正典資料是 `case.json`**：所有計算以人工確認後的 `case.json` 為準；DXF、SVG 與圖片只是證據來源，不得跳過確認關卡直接從圖面推算。
5. **需人工判讀原則**：圖面判讀不確定、需大樣圖或現場才能確認的項目，例如防火區劃、排煙開口、夾層面積等，一律標註「需人工判讀」，嚴禁用推測填充。
6. **待確認規則必標示**：`rules/*.json` 中 `verified: false` 的規則參數，輸出時必須標明「本參數尚未逐條確認」。本專案使用者本身即為消防專業人員，不需另外送外部核定：把待確認清單列給使用者（`python3 tools/verification_sheet.py list`）逐條審核，回覆結果以 `apply` 回填即可。
7. **法規版本注記**：報告標頭必須注明所依據的法規版本，也就是 `rules` 檔案的 `regulation_version` 欄位。
8. **呈現正反兩面**：判定「免設」時同樣列出計算過程與條文依據，讓審查者可以覆核，不只列缺失。
9. **法典與實務註解分離**：`rules/` 為法典層，只能經先紅再綠變更；法典未涵蓋情境的實務見解只能以 Practice Note 寫入 `practice_notes/`（`/practice-note`），不得直接改規則參數。`check-gap` 偵測到案件結論無法被既有規則涵蓋時，先查證是否只是「規則未入庫」（是則走先紅再綠），確為法典未涵蓋才草擬註解供使用者審閱；未經使用者「確認納入」的註解禁止從 `staging` 移到 `active`。

## 目錄結構

```text
drawing_review/
├── input/                       — 統一輸入資料夾（只讀不改）
│   └── {案件名}/                — 案件輸入資料夾（只讀不改）
│       ├── 平面圖.dxf           — 需要審核的主圖面
│       ├── 平面圖.pdf           — 輔助對照用圖面 PDF
│       └── 相關審查文件          — 申請書、審查表、說明書等案件文件
├── output/                      — 統一輸出資料夾（單一案件平放，不再分案件子目錄）
│   ├── case.json                — 圖說底稿（正典資料）
│   ├── annotations.json         — SVG 標註定義
│   ├── check_results.json       — 檢核結果（供 HTML 產生）
│   ├── {案件名}-圖面審查.html    — 交付物1：DXF 轉 SVG 標註＋缺失導覽
│   ├── {案件名}-問題清單.md      — 交付物2：缺失清單（詳列違反法條）
│   └── {案件名}-法條檢核清單.html — 交付物3：打勾檢核表
├── rules/                       — 結構化法規規則庫
│   ├── equipment_rules.json     — 規則（每條附條號、verified 旗標）
│   ├── article18_equipment_options.json — §18 各款可選設備對照（選擇設置，非僅泡沫）
│   ├── stage_two_judgment_rules.md — §14~31 逐款實務判斷慣例（未核定，須附警語）
│   ├── review_corrections.md    — 累積確認的通案修正筆記（審圖前必讀，不得刪除歷史）
│   ├── checklists/              — 法條判斷表 xlsx（§14~31，已含第18條完整9款）
│   ├── rule_tests.json          — 先紅再綠測試案例
│   ├── core/                    — 法規全文正典（單一全文 md ＋ _assets 附表圖檔、主從用途 PDF；非每案輸入）
│   ├── regulation_index.json    — 輕量條文索引（266 條，不含完整條文）
│   └── regulation_articles/      — 逐條文 JSON（266 條，含章/節階層與附表圖；按需載入）
├── graphify-out/                — 法規知識圖譜（可查詢／導覽，見下方「法規圖譜」）
├── training/                    — 訓練模式（`/train`）：inbox/ 投放、registry.json 索引、每批次歸檔紀錄
├── practice_notes/              — 實務註解層：active/ 現行註解、staging/ 待確認、index.json 索引
├── governance/                  — 規則核定責任追溯鏈
├── skills/                      — 審圖 workflow 文件（只放執行指令；設計說明見 skills/README.md）
└── tools/                       — 確定性工具
```

## 固定交付物

| # | 交付物 | 產生方式 |
|---|--------|---------|
| 1 | **圖面審查 HTML** | `skills/gap-analysis.md` 產出 `annotations.json`，再用 `tools/dxf_svg_review.py` 將 DXF 轉 SVG 並標註缺失 |
| 2 | **問題清單** | 缺失四級分類，每項詳列違反法條、應設要求、圖面現況、缺口 |
| 3 | **法條檢核清單 HTML** | `tools/checklist_html.py` 依 `check_results.json` 產出標準表格，逐項打勾 |

## 兩階段審查工作流程（Excel 交付，與固定交付物並行）

實務交付另有一條兩階段 Excel 路線，內容與交付物 3 及複合用途檢討表同源（皆以 `case.json` 為正典）。
完整規則見 `skills/first-stage-review.md` 與 `skills/stage-two-review.md`。

| 階段 | skill | 串接既有流程 | Excel 交付物 |
|------|-------|------------|-------------|
| 第一階段 | `/first-stage-review` | `/plan-intake` → `/mixed-use-review` | 複合用途建築物及樓層屬性檢討（4 分頁） |
| 第二階段 | `/stage-two-review` | `/code-requirements` → `article_checklist.py` | 設置標準檢討（3 分頁） |

四條鐵律：

1. **第一階段未完成不得執行第二階段**；第一階段結果修正時必須從頭重跑完整第二階段。
2. **受控自動化關卡**：兩階段匯出前都必須跑 `tools/case_facts_gate.py`；`ready: false`（結束碼 2）時不得輸出最終交付物，逐項問使用者補齊 `case.json` 後重跑。**不得以猜測、預設值或未提供的圖說補足資料。**
3. **審圖前必讀** `rules/review_corrections.md`（兩階段皆是）與 `rules/stage_two_judgment_rules.md`（第二階段）；兩者皆未經 `governance/` 核定，援引其結論必附「本判斷慣例未經消防專業人員核定，以現行法規為準」。
4. **規則庫不存條文原文與門檻數值**——轉抄會隨修法漂移。條文一律走下方「法規圖譜」的標準調閱流程即時回查（圖譜定位 → `lookup` 只載入相關條文，不要一次載入 §14~§31 全文）；新增規則時用主詞與範圍描述判斷差異，不寫死數字。

第二階段的勾選一律來自人工定案的 `stage2_decisions.json`——**工具不代為做法規判斷**。

## 訓練模式與實務註解（讓系統「學會」新東西的唯一入口）

系統要多會判斷一條法規、或記住一個實務見解，一律走這兩條路，**不得直接改規則參數**。

| 目的 | skill | 入口 | 成果落點 |
|------|-------|------|---------|
| 注入新法源／實務表格／格式範本 | `/train` | 檔案丟 `training/inbox/` | `rules/core/`、`rules/checklists/`、`rules/equipment_rules.json`（先紅再綠） |
| 記住法典未涵蓋情境的判讀 | `/practice-note` | `check-gap` 找出缺口 | `practice_notes/active/` ＋ `index.json` |
| 記住通案性工作流程修正 | `/train` 第五步 | 使用者口述確認 | `rules/review_corrections.md`、`rules/stage_two_judgment_rules.md` |

四條鐵律：

1. **不繞過先紅再綠**——`training_intake.py` 在程式層拒絕寫入 `equipment_rules.json`／`mixed_use_rules.json`／`rule_tests.json`；法規參數一律走 `skills/red-green.md`
2. **不自動下法規判斷**——歸檔分類只看副檔名與檔名樣式，信心不足即標 `needs_confirmation` 交人工；註解草案的判讀欄位一律留「（待填）」，嚴禁推測填充
3. **註解只補充、不推翻法典**——免除法定應設設備的註解一律紅色警示，須具名確認法源；未經使用者「確認納入」禁止 `staging` → `active`
4. **圖譜必須跟上**——訓練寫入後 `/train` 第七步自動重建圖譜並 `graph_status.py stamp`；自動重建失敗則寫 `training/graph_pending.json`，此後 `training_intake.py status` 與 CI 的 `graph_status.py check` 持續紅燈，直到補建

各 pipeline skill 的前置檢查跑 `python3 tools/training_intake.py status`（結束碼 `2` ＝ 圖譜未跟上規則庫），
開場即知有無新訓練成果、圖譜是否可信。

## 法規圖譜（查詢調閱法規先看這裡）

法規全文已建成可查詢的知識圖譜；後續案件需要查詢／調閱法規時，**先查圖譜以定位條號與關聯，再回原文核對**。

- **位置**：`graphify-out/`（`graph.json` 可查詢圖譜、`graph.html` 互動視覺化、`GRAPH_REPORT.md` 樞紐與社群導覽）
- **規模**：482 節點／830 邊——條號、設備、場所用途分類、**圖表附件**為節點；`依第X條`／`準用`／設備↔條文／條文↔附表圖為邊。
- **來源**：以 `rules/core/` 法規全文 md（各類場所消防安全設備設置標準，§1~§239 共 266 條，含附表圖）與主從用途對照表 PDF 語意抽取。
- **邊界（呼應最高原則 2、4）**：圖譜只是**索引與導覽**，用來定位條號與關聯，**不是門檻數值或計算結果的來源**。任何應設／免設判斷與數量計算，一律仍以 `python3 tools/fire_code_calc.py` ＋人工確認後的 `case.json` 為準，數值須回法條原文核對；圖表附件節點只作導覽，表內數字不得直接引用，須經先紅再綠抄錄入庫。
- **查詢（免安裝，優先用這個）**：`python3 tools/regulation_graph.py neighbors --article §24`、`… articles --equipment 排煙設備`、`… path --from 無開口樓層 --to 排煙設備`（純標準庫，直接讀 graph.json，輸出附可貼的 lookup 指令）。裝了 graphify 時另可用 `graphify query/explain/path`。
- **標準調閱流程**：圖譜（定位牽涉哪幾條）→ `regulation_index.py lookup`（只載入那幾條原文，支援 `'§24,§12'` 逗號列舉與 `'§20-§22'` 範圍）→ `fire_code_calc`（門檻與數量）→ 判斷。**不要一次載入 §14~§31 全文**（全載約 1.5 萬字，定位後通常 3~4 千字）。
- **法規更新後重建**：改動 `rules/core/` 全文後，重跑 `/graphify rules`（大改）或 `/graphify rules --update`（增量）刷新圖譜；法規為文字語料須走 skill 的語意抽取（依編/章切塊），CLI 的 `graphify update`（純 AST）不適用。圖表附件為確定性節點，可由 `regulation_articles` 的圖片連結重建。 重建完成後務必 `python3 tools/graph_status.py stamp` 蓋章——`graph_status.py check` 以 sha256 逐檔指紋判斷圖譜是否跟上規則庫與註解庫，CI 也跑這一步，來源檔改了卻沒重建即紅燈。走 `/train` 時第七步會自動完成重建與蓋章。

## 報告語言與分類

- 報告使用繁體中文與台灣法規用語。
- 缺失分級固定為：`重大缺失`、`一般缺失`、`配置疑義`、`需人工判讀`。
- `建議事項` 只用於無強制法源的內容，且必須明確標明。
- 面積、距離、數量等數字必須標注來源，例如圖面標注、人工輸入或工具計算。

## 常用命令

```bash
# 首次使用：一鍵安裝交付物所需套件（ezdxf/openpyxl/pymupdf）並自檢
bash tools/setup.sh && python3 tools/check_env.py
# 選：連同法規圖譜 graphify 一起裝 → bash tools/setup.sh --with-graph
#     graphify 首頁 https://github.com/Graphify-Labs/graphify

# 法規全文轉逐條索引（法規換版或 rules/core/ 全文更新後執行）
python3 tools/regulation_index.py build

# 只取用相關條文，不要一次載入全部法規
python3 tools/regulation_index.py lookup --article '§19'
python3 tools/regulation_index.py lookup --article '§115-§120'
python3 tools/regulation_index.py lookup --equipment '滅火器'

# 先紅再綠：規則測試（規則庫交付前必須全綠）
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}

# 引擎與規則庫自檢（修改 rules/*.json 後必跑）
python3 tools/fire_code_calc.py self-test

# 門檻判斷：逐層逐設備 應設/免設/需人工判讀
python3 tools/fire_code_calc.py check-threshold --case output/case.json

# 數量計算
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40
python3 tools/fire_code_calc.py calc --expr '450 / 100'

# 交付物產生
python3 tools/dxf_svg_review.py --annotations output/annotations.json
python3 tools/checklist_html.py --results output/check_results.json

# 法規調閱：先定位，再載入（免安裝 graphify）
python3 tools/regulation_graph.py neighbors --article §24
python3 tools/regulation_graph.py articles --equipment 排煙設備
python3 tools/regulation_index.py lookup --article '§24,§12'

# 兩階段審查工作流程（匯出前關卡結束碼 2 = 阻擋，不得續行）
python3 tools/case_facts_gate.py --stage first  --case output/case.json
python3 tools/case_facts_gate.py --stage second --case output/case.json
python3 tools/stage_report_xlsx.py first-stage --case output/case.json
python3 tools/stage_report_xlsx.py stage-two --decisions output/stage2_decisions.json --case output/case.json

# 訓練模式（素材歸檔 → 先紅再綠 → 重建索引與圖譜）
python3 tools/training_intake.py classify                       # 乾跑：印出 inbox 素材的路由建議
python3 tools/training_intake.py apply --batch {批次名} --operator {歸檔人}
python3 tools/training_intake.py status                          # 工作流程前置檢查（2 = 圖譜需補建）
python3 tools/graph_status.py check                              # 0=新鮮 2=過期 3=尚未建立基準
python3 tools/graph_status.py stamp                              # 重建圖譜後蓋章

# 實務註解（法典未涵蓋情境）
python3 tools/fire_code_calc.py check-gap --case output/case.json \
  --output output/gap_candidates.json
python3 tools/practice_note_engine.py draft --gap output/gap_candidates.json --case {案件名}
python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/{id}.json
python3 tools/practice_note_engine.py apply --draft practice_notes/staging/{id}.json \
  --approved-by {批准人} --confirm 確認納入
python3 tools/practice_note_engine.py test --strict

# 規則逐條確認（使用者本身即為消防專業人員，不需另送外部核定）
python3 tools/verification_sheet.py list                                              # 列出待確認規則
python3 tools/verification_sheet.py discrepancies                                     # 列出與現行條文比對出的差異，逐則裁示
python3 tools/verification_sheet.py apply --results governance/核定紀錄/results-{日期}.json
```

## 注意事項

- 本專案輸出僅供審圖輔助，最終判斷歸屬專業消防人員。
- 案件 `input/{案件名}/` 不放法規檔；法規來源固定維護於 `rules/core/` 與規則索引中。
- SVG 標註網頁的圈選位置為 AI 推定時（`position_confidence: low`），以問題清單文字說明為準。
- 判定「符合」與「不適用」時，也要保留可覆核的計算過程與條文依據。
- 查法規依據時，優先使用 `rules/regulation_index.json` 與 `tools/regulation_index.py lookup` 載入相關條文；避免把 `rules/core/` 全文 md 全部載入上下文。
- 交付物工具缺套件時，先跑 `bash tools/setup.sh`（或看 `python3 tools/check_env.py` 指引）；核心計算與索引工具只用標準庫，無需安裝。

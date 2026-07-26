# Fire Review — 審圖行為契約

## 專案定位

消防審圖輔助 Agent 系統：DXF 向量圖面與審查依據文件輸入 → 依法規計算設備需求 → 列出缺失設備及數量 → 以 SVG 網頁標註圖面問題，輔助專業消防人員審圖。**輔助，不取代。**

## 審圖最高原則（最高優先級，所有 skill 執行時必須遵守）

1. **法條可追溯**——每一項「應設／免設／缺失」結論必須附法規條號；引用不到條號的結論一律降級為「建議事項」並標明無法源依據
2. **禁止心算、禁止憑記憶引法規數值**——所有門檻判斷與數量計算必須透過 `python3 tools/fire_code_calc.py`，工具輸出直接嵌入報告作為計算記錄
3. **先紅再綠（防幻覺核心，完整紀律見 `skills/red-green.md`）**——規則庫的每個參數必須先有測試（expected 從法條 PDF 原文逐字抄錄、附頁碼與 quote），經 `run-tests --verify-red` 確認紅得正確，編碼後轉綠才可使用；參數先於測試存在則刪除重來；`run-tests --strict` 不通過的規則庫不得交付
4. **正典資料是 case.json**——所有計算以人工確認後的 `case.json` 為準；DXF、SVG 與圖片只是證據來源，不得跳過確認關卡直接從圖面推算
5. **需人工判讀原則（安全底線）**——圖面判讀不確定、需大樣圖／現場才能確認的項目（防火區劃、排煙開口、夾層面積等），一律標註「需人工判讀」，嚴禁用推測填充
6. **待確認規則必標示**——`rules/*.json` 中 `verified: false` 的規則參數，輸出時必須標明「本參數尚未逐條確認」。本專案使用者本身即為消防專業人員，**不需另外送外部核定**：把待確認清單列給使用者（`python3 tools/verification_sheet.py list`）逐條審核，回覆結果以 `apply` 回填即可
7. **法規版本注記**——報告標頭必須注明所依據的法規版本（`rules` 檔案的 `regulation_version` 欄位）
8. **呈現正反兩面**——判定「免設」時同樣列出計算過程與條文依據，讓審查者可以覆核，不是只列缺失
9. **法典與實務註解分離**——`rules/` 為法典層，只能經先紅再綠變更；法典未涵蓋情境的實務見解只能以 Practice Note 寫入 `practice_notes/`（`/practice-note`），不得直接改規則參數。`check-gap` 偵測到案件結論無法被既有規則涵蓋時，先查證是否只是「規則未入庫」（是則走先紅再綠），確為法典未涵蓋才草擬註解供使用者審閱；未經使用者「確認納入」的註解禁止從 `staging` 移到 `active`

用途分類、樓層屬性、地下層、屋突層／屋頂層與無開口樓層判定，必須讀取 `skills/place-use-classification.md`；第 12 條用途分類只產生候選，最終以人工確認後的 `case.json` 為準。複合用途建築物的主從用途判定依 `skills/mixed-use-review.md`（`/mixed-use-review`）：以 `rules/mixed_use_rules.json`（《複合用途建築物判斷基準》附表結構化）比對產生候選，§12 分類經人工定案後才可進入 `/code-requirements`。案件涉及增建、改建、室內裝修或變更用途時，必須先跑 `check-applicability`（§13）判斷各設備適用新舊標準。走兩階段 Excel 交付路線時，另須先讀 `rules/review_corrections.md`——其中含通案樓層屬性規則（該工作流程下所有地上樓層一律列為`無開口樓層`），會改變 §14~31 的判斷基礎。

## 目錄結構（統一輸入／統一輸出）

```
drawing_review/
├── input/                       — 統一輸入資料夾（只讀不改）
│   ├── {案件名}/                — DXF 圖面資料夾與審查依據文件
│   │   └── drawings/            — DXF 圖面（只讀不改）
│   └── 法規/                    — 核對用法條清單 PDF
├── output/                      — 統一輸出資料夾（單一案件平放，不再分案件子目錄）
│   ├── case.json                           — 圖說底稿（正典資料）
│   ├── annotations.json                    — SVG 標註定義
│   ├── check_results.json                  — 檢核結果（供 HTML 產生）
│   ├── {案件名}-圖面審查.html               — 交付物1：DXF 轉 SVG 標註＋缺失導覽
│   ├── {案件名}-問題清單.md                 — 交付物2：缺失清單（詳列違反法條）
│   ├── {案件名}-法條檢核清單.html           — 交付物3：打勾檢核表（§14~§31 逐條窮舉）
│   ├── {案件名}-複合用途及樓層屬性檢討.html — 交付物4：主從用途／樓層屬性檢討表
│   ├── stage2_decisions.json               — 第二階段人工定案勾選（/stage-two-review 輸入）
│   ├── {案件名}-第一階段-複合用途及樓層屬性檢討.xlsx — 兩階段工作流程：第一階段工作簿
│   └── {案件名}-第二階段-設置標準檢討.xlsx           — 兩階段工作流程：第二階段工作簿
├── rules/                       — 結構化法規規則庫
│   ├── equipment_rules.json     — 規則（每條附條號、verified 旗標）
│   ├── mixed_use_rules.json     — 主從用途對照表（判斷基準附表結構化、verified 旗標）
│   ├── article18_equipment_options.json — §18 各款可選設備對照（選擇設置，非僅泡沫）
│   ├── rule_tests.json          — 先紅再綠測試案例（expected 抄錄自法條 PDF；選填 rules_file 指向第二規則檔）
│   ├── stage_two_judgment_rules.md — §14~31 逐款實務判斷慣例（未核定，須附警語）
│   ├── review_corrections.md    — 累積確認的通案修正筆記（審圖前必讀，不得刪除歷史）
│   ├── checklists/              — 法條判斷表 xlsx（§14~31，已含第18條完整9款）
│   └── regulation-checklist.html — 法條清單 HTML（由法條 PDF 轉換，格式不變，逐條錨點）
├── training/                    — 訓練模式（`/train`）：素材投放、歸檔紀錄
│   ├── inbox/                   — 待歸檔素材投放區
│   ├── registry.json            — 訓練批次總索引（工作流程查詢入口）
│   └── {批次名}-{YYYYMMDD}/     — manifest.json／sources/／formats/／NOTES.md
├── practice_notes/              — 實務註解層（法典未涵蓋情境的實務見解）
│   ├── active/                  — 現行有效註解（每則一個 PN-{日期}-{序號}.json）
│   ├── staging/                 — 草擬中，待使用者「確認納入」
│   └── index.json               — 註解索引（by_article／by_equipment／by_rule_id）
├── governance/                  — 規則核定責任追溯鏈（核定表／簽名紀錄，見 governance/README.md）
├── skills/                      — 審圖 skill 定義（只放執行指令；設計說明見 skills/README.md）
└── tools/                       — 確定性工具
```

## 四項固定交付物（每案件必產出）

| # | 交付物 | 產生方式 |
|---|--------|---------|
| 1 | **圖面審查 HTML** | `/gap-analysis` 產出 `annotations.json`（缺失位置＋簡短解釋＋嚴重度），`dxf_svg_review.py` 將 DXF 轉 SVG 並標註缺失 |
| 2 | **問題清單** | 缺失四級分類（重大／一般／配置疑義／需人工判讀），每項詳列違反法條、應設要求、圖面現況、缺口 |
| 3 | **法條檢核清單 HTML** | `article_checklist.py` 依 case.json 產出 §14~§31 **逐條窮舉**的 `check_results.json`（規則未入庫條號列「⚪需人工判讀（規則未入庫）」），`/gap-analysis` 更新比對結果後由 `checklist_html.py` 產出標準表格，逐項打勾（☑符合／☒不符合／⚪需人工判讀／—不適用），條號深連結到 `regulation-checklist.html` 錨點 |
| 4 | **複合用途及樓層屬性檢討 HTML** | `/mixed-use-review` 人工確認主從用途後，`mixed_use_report.py` 依 case.json 產出（格式對齊 `input/範例/` 實務範例：樓層／各層用途／樓地板面積／本次申請範圍／樓層屬性＋合計＋判定結論） |

## 兩階段審查工作流程（Excel 交付，與四項固定交付物並行）

實務交付另有一條**兩階段** Excel 路線，內容與交付物 3、4 同源（皆以 `case.json` 為正典），
只是格式為工作簿。完整規則見 `skills/first-stage-review.md` 與 `skills/stage-two-review.md`。

| 階段 | skill | 串接既有流程 | Excel 交付物 |
|------|-------|------------|-------------|
| 第一階段 | `/first-stage-review` | `/plan-intake` → `/mixed-use-review` | 複合用途建築物及樓層屬性檢討（4 分頁） |
| 第二階段 | `/stage-two-review` | `/code-requirements` → `article_checklist.py` | 設置標準檢討（3 分頁） |

四條鐵律：

1. **第一階段未完成不得執行第二階段**；第一階段結果修正時必須從頭重跑完整第二階段
2. **受控自動化關卡**：兩階段匯出前都必須跑 `tools/case_facts_gate.py`，`ready: false`
   （結束碼 2）時不得輸出最終交付物，逐項問使用者補齊 `case.json` 後重跑
3. **審圖前必讀** `rules/review_corrections.md`（兩階段皆是）與
   `rules/stage_two_judgment_rules.md`（第二階段）；兩者皆未經 `governance/` 核定，
   援引其結論必附「本判斷慣例未經消防專業人員核定，以現行法規為準」
4. **規則庫不存條文原文與門檻數值**——轉抄會隨修法漂移。條文一律走下方「法規圖譜」的
   標準調閱流程即時回查（圖譜定位 → `lookup` 只載入相關條文，不要一次載入 §14~§31 全文）；
   新增規則時用主詞與範圍描述判斷差異（「門檻的主詞是各居室，不是整棟」），不寫死數字

格式權威為 `input/範例/` 內的兩份格式範本，`tools/stage_report_xlsx.py` 以程式複製其版面。
第二階段的勾選一律來自人工定案的 `stage2_decisions.json`——**工具不代為做法規判斷**。

## 報告語言與風格

- 報告使用**繁體中文**（台灣法規用語）
- 缺失分級固定四級：`重大缺失`（法定應設而未設）／`一般缺失`（數量不足或配置不符）／`配置疑義`（需圖面逐點量測）／`需人工判讀`；另有 `建議事項`（無強制法源，必須標明）
- 面積、距離、數量等數字必須標注來源（圖面標注／人工輸入／工具計算）

## 常用命令

```bash
# 首次使用：一鍵安裝交付物所需套件（ezdxf/openpyxl/pymupdf）並自檢
# 核心計算與索引工具只用標準庫；圖譜重建／查詢另需 graphify（--with-graph）
bash tools/setup.sh && python3 tools/check_env.py

# 先紅再綠：規則測試（規則庫交付前必須全綠）
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}   # Verify RED：驗證新測試「紅得正確」

# 引擎與規則庫自檢（修改 rules/*.json 後必跑）
python3 tools/fire_code_calc.py self-test

# 門檻判斷：逐層逐設備 應設/免設/需人工判讀（--format json 供工具串接）
python3 tools/fire_code_calc.py check-threshold --case output/case.json

# §13 新舊標準適用判斷（增建/改建/裝修/變更用途案件必跑）
python3 tools/fire_code_calc.py check-applicability --case output/case.json

# 主從用途對照表比對（只產候選，最終人工確認；/mixed-use-review 使用）
python3 tools/fire_code_calc.py classify-mixed-use --case output/case.json

# 數量計算
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40
python3 tools/fire_code_calc.py calc --expr '450 / 100'

# 交付物產生
python3 tools/dxf_svg_review.py --annotations output/annotations.json
python3 tools/article_checklist.py --case output/case.json      # §14~31 逐條窮舉 check_results.json
python3 tools/checklist_html.py --results output/check_results.json
python3 tools/mixed_use_report.py --case output/case.json       # 交付物4：複合用途及樓層屬性檢討

# 法規調閱：先定位，再載入（免安裝 graphify）
python3 tools/regulation_graph.py neighbors --article §24
python3 tools/regulation_graph.py articles --equipment 排煙設備
python3 tools/regulation_index.py lookup --article '§24,§12'      # 支援逗號列舉與範圍

# 兩階段審查工作流程
python3 tools/case_facts_gate.py --stage first  --case output/case.json   # 匯出前關卡（結束碼 2 = 阻擋）
python3 tools/case_facts_gate.py --stage second --case output/case.json
python3 tools/stage_report_xlsx.py first-stage --case output/case.json    # 第一階段工作簿
python3 tools/stage_report_xlsx.py stage-two \
  --decisions output/stage2_decisions.json \
  --case output/case.json                                                 # 第二階段工作簿

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

法規全文已建成可查詢的知識圖譜，**後續案件需要查詢／調閱法規時，先查圖譜以定位條號與關聯，再回原文核對**，可大幅加快「哪一條、關聯到哪些設備／用途／條文」的定位。

- **圖譜位置**：`graphify-out/`
  - `graph.json`——可查詢圖譜（482 節點／830 邊：條號、設備、場所用途分類、**圖表附件**為節點；`依第X條`／`準用`／設備↔條文／條文↔附表圖為邊）
  - `graph.html`——互動式視覺化（瀏覽器直接開，免伺服器）
  - `GRAPH_REPORT.md`——樞紐節點（§12 用途分類、避難器具、自動撒水設備…）、社群分群與跨編關聯導覽
- **來源**：以 `rules/core/` 法規全文 md（各類場所消防安全設備設置標準，§1~§239 共 266 條，含附表圖檔）與主從用途對照表 PDF 語意抽取；`regulation_version` 見 `rules/regulation_index.json`
- **查詢方式（免安裝，優先用這個）**——`tools/regulation_graph.py` 直接讀 `graph.json`，只用標準庫：
  ```bash
  python3 tools/regulation_graph.py neighbors --article §24        # 該條引用網＋附表圖檔
  python3 tools/regulation_graph.py articles --equipment 排煙設備   # 哪些條文規範該設備
  python3 tools/regulation_graph.py path --from 無開口樓層 --to 排煙設備
  ```
  輸出直接附上可貼的 `lookup` 指令。裝了 graphify 時另可用
  `graphify query/explain/path`（先 `uv tool install graphifyy && graphify install`）。
- **標準調閱流程（省 context 且降低看錯條的機率）**：
  ```
  圖譜（定位牽涉哪幾條）→ regulation_index.py lookup（只載入那幾條原文）→ fire_code_calc（門檻與數量）→ 判斷
  ```
  `lookup --article` 支援單條、範圍與**逗號／頓號列舉**（`'§24,§12'`、`'§20-§22,§28'`）。
  **不要一次載入 §14~§31 全文**——全載約 1.5 萬字，定位後只載相關條通常 3~4 千字。
- **邊界（呼應最高原則 2、4）**：圖譜只是**索引與導覽**，用來定位條號與關聯，**不是門檻數值或計算結果的來源**。任何應設／免設判斷與數量計算，一律仍以 `python3 tools/fire_code_calc.py` ＋人工確認後的 `case.json` 為準，數值須回法條原文核對，不得直接引用圖譜節點標題當作法規數值。
- **法規更新後重建**：改動 `rules/core/` 全文後，重跑 `/graphify rules`（大改）或 `/graphify rules --update`（增量，只重抽變更條文）刷新圖譜。註：法規為文字語料，須走 skill 的語意抽取（子代理依編/章切塊）；CLI 的 `graphify update`（純 AST、免 LLM）不適用於法條語意圖譜。跨塊抽取後須以 `graphify.ids.make_id` 統一正規化 node id（條號感知）再合併，避免共用概念無法去重。 重建完成後務必 `python3 tools/graph_status.py stamp` 蓋章——`graph_status.py check` 以 sha256 逐檔指紋判斷圖譜是否跟上規則庫與註解庫，CI 也跑這一步，來源檔改了卻沒重建即紅燈。走 `/train` 時第七步會自動完成重建與蓋章。

## 注意事項

- 本專案輸出僅供審圖輔助，最終判斷歸屬專業消防人員
- `input/` 只讀不改；所有產出寫入 `output/`
- 修改 `rules/*.json` 後必須重跑 `self-test` 與 `run-tests --strict`
- SVG 標註網頁的圈選位置為 AI 推定時（`position_confidence: low`），以問題清單文字說明為準

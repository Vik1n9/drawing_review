# Drawing Review — 消防審圖輔助 Agent 系統

本專案是消防審圖輔助系統：案件輸入以 **待審 `平面圖.dxf`** 為主，搭配輔助對照用 `平面圖.pdf` 與相關審查文件；AI 依人工確認後的 `case.json` 與固定法規資料夾中的結構化規則庫進行工具計算，最後輸出缺失清單、法條檢核表，以及可互動導覽的 SVG 圖面標註網頁。

> **定位：輔助專業消防人員審圖，不取代專業判斷。** 每一項「應設／免設／缺失」結論都必須可追溯到法規條文；凡圖面或資料不足以判定之處，一律標註「需人工判讀」。

---

## 兩種取得方式，挑一種就好

| | 給誰 | 怎麼拿 |
|---|---|---|
| **線2：安裝程式**（建議） | 消防專業人員，不必懂 git | 到 [Releases](https://github.com/Vik1n9/drawing_review/releases) 下載 `FireReview-{版本}-setup.exe`（自解壓縮檔），雙擊執行、自己選一個安裝資料夾。**沒裝過 Python 也沒關係**——偵測不到時它會自動下載官方安裝程式（會先驗證是 Python 官方簽章的檔案才執行）。裝完打開資料夾裡的「安裝完成-請把這段貼給你的AI.txt」，照著把那段話貼給你的 AI，它就會把那個資料夾當專案資料夾。不想安裝的話，同一頁也有免安裝的 `.zip` |
| **線1：`git clone`** | 技術人員、要送 PR 的人 | 見下方「快速開始」 |

> **Windows 會跳「已保護您的電腦」的藍色警告。** 那是因為安裝程式沒有買程式碼簽章憑證，
> 不是偵測到病毒——點「其他資訊」→「仍要執行」即可。
>
> **如果防毒軟體直接把它擋掉或刪掉**：自解壓縮檔這種格式常被防毒視為可疑（惡意程式
> 也愛用這種殼），企業電腦尤其容易被隔離。這時請改用同一頁的 `.zip`——**內容完全相同**，
> 只是要自己選資料夾、自己裝 Python。

> **不論走哪一條，你的審圖成果都只存在你這台電腦。** 規則裁示、實務見解、案件圖面、
> 交付物，全部在那個資料夾裡，沒有上傳到任何地方——所以**更新的方式錯了就救不回來**。
> 要更新請看下面的「要更新到最新版？」。

---

## 第一次使用？把這行貼給你的 AI

不論你用的是 **Claude Code、Codex、OpenCode 或其他任何 AI 工具**，載入本倉庫後先跑這一行：

```bash
python3 tools/onboarding.py status
```
（Windows 若沒有 `python3`，改用 `python tools/onboarding.py status`）

它會診斷目前狀態並列出待處理步驟；接著跟你的 AI 說**「照 `skills/onboarding.md` 帶我開始」**，
它就會依序引導你裁示疑義表、確認法規圖譜、說明目前的環境能力，最後印出操作簡介。
只想直接看操作簡介的話：`python3 tools/onboarding.py intro`。

> **不必安裝任何套件。** 審圖主線——法規門檻計算、DXF 圖面標註（交付物1）、
> PDF／DOCX／XLSX 判讀——全部零安裝。只有兩階段 Excel 匯出等少數交付物格式需要
> 第三方套件，而它們都有替代路徑。跑 `python3 tools/check_env.py` 會列出這台電腦
> 現在能做什麼、做不到的怎麼繞。
>
> **唯一無法迴避的前置條件是 Python 本身。** 上面那行如果回報「找不到 python3／python」，
> 請先安裝 Python（<https://www.python.org/downloads/>，Windows 安裝時記得勾選
> 「Add python.exe to PATH」）。在那之前**不要讓 AI 用聊天代替法規數值計算**——
> 本系統禁止心算，沒有工具就只能做不涉及數值的協助。
>
> **圖面是 `.dwg`？** DWG 是二進位格式，AI 讀不了。跑
> `python3 tools/dwg_guide.py check --path input/` 會告訴你怎麼用自己的 CAD
> 另存成 DXF（`DXFOUT` 指令，版本選 2013 以上、不要勾二進位）——零安裝，
> 而且原生匯出的品質比任何轉檔器都好。

> **給 AI 代理**：這是你載入本倉庫後的**第一個動作**，不需使用者要求。結束碼 `2` ＝ 有待處理步驟，
> 請依 `skills/onboarding.md` 逐步引導——**唯讀命令可直接跑，標「寫入」的先說明並取得同意，
> 且不得代替使用者裁示任何法規事項**。Claude Code 已設 SessionStart hook 自動執行這一步。

---

## 要更新到最新版？先看這裡

**你的訓練成果只存在你這台電腦，覆蓋掉不可逆。** 更新之前先跑這一行看看有什麼會被影響：

```bash
python3 tools/update_guard.py check      # 唯讀，隨時可跑
python3 tools/update_guard.py snapshot --note "更新前"   # 備份到這個資料夾的外面
```

接著照你的取得方式：

- **線2（安裝程式）**：到 Releases 下載新版，**裝到同一個資料夾**。安裝程式會先備份，
  你沒改過的檔案直接更新，**你改過的檔案一律保住原檔**、上游新版另存成 `.上游新版`
  讓你自己比對；你新增的案件圖面與實務見解完全不動。裝完會有一份「更新報告-日期.txt」。
  （安裝程式是先解壓到暫存區再逐檔判斷，**在判斷跑起來之前你的資料夾一個位元組都不會被碰到**）
- **線1（git）**：`python3 tools/update_guard.py commit` 之後再 `git pull --ff-only`

> **給 AI 代理**：使用者說「更新」「拉最新的」「重新下載」時，**先讀 `skills/safe-update.md`**。
> 在 `update_guard.py snapshot` 成功之前，`git reset --hard`、`git checkout -- .`、
> `git restore`、`git clean`、以及刪目錄重新 clone **一律禁止**——那會抹掉使用者數月的成果，
> 而且未提交的改動連 reflog 都救不回。Claude Code 另有 `PreToolUse` hook 會擋下這些命令。

---

## 快速開始（任意 AI 代理 / 本地皆適用）

> **給 AI 代理**：貼上本倉庫網址後，先讀 `AGENTS.md`（行為契約正本，跨 AI 工具共用；`CLAUDE.md` 只是指向它的指標），再依其中的路由表載入該階段的 `skills/*.md`。契約只放「載入任何 skill 之前就必須生效」的五條底線；**所有法規門檻與數量計算一律呼叫 `tools/fire_code_calc.py`，不得憑記憶或心算**。

> 不熟終端機的話不必逐步照做——上面的「第一次使用？」一行會把下面這些檢查一次做完並引導你。

1. **取得專案**
   ```bash
   git clone https://github.com/Vik1n9/drawing_review.git && cd drawing_review
   ```
   （不想碰 git 的話走線2 安裝程式，見最上方「兩種取得方式」。
   之後要更新時**不要**用 `git pull` 以外的方式，程序見 `skills/safe-update.md`。）
2. **確認環境能力**（不需要安裝任何東西——審圖主線全部零安裝）
   ```bash
   python3 tools/check_env.py   # 列出現在能做什麼、做不到的替代路徑
   ```
   裝得起套件的環境可另外補齊少數交付物格式所需套件（選用，非門檻）：
   ```bash
   bash tools/setup.sh
   # 需重建或 CLI 查詢法規圖譜時，另加：bash tools/setup.sh --with-graph
   ```
3. **驗證環境**（應全綠）
   ```bash
   python3 tools/fire_code_calc.py self-test
   python3 tools/fire_code_calc.py run-tests --strict
   ```
4. **處理待確認事項**（規則參數與現行條文比對出的差異，未裁示前不得作為審查依據）
   ```bash
   python3 tools/pending_review.py status   # 結束碼 2 ＝ 有待確認事項
   python3 tools/pending_review.py list     # 逐則列給具消防專業的使用者裁示
   ```
   AI 代理的開場診斷已改由 `python3 tools/onboarding.py status` 統一涵蓋（疑義表是它的第一步）；
   有待確認事項就把 `list` 的內容列給使用者，
   逐則取得「採納更正／維持現值／另有更正」後執行
   `python3 tools/pending_review.py decide` 與 `apply --all`——工具會自動走先紅再綠
   完成更正、回填 `verified`、更新 README 並移除疑義檔。詳見下方待確認區塊。
5. **開始審一個案件**
   - 把待審 `平面圖.dxf`（＋輔助 `平面圖.pdf`、審查文件）放到 `input/{案件名}/`
   - 只有 `.dwg`？跑 `python3 tools/dwg_guide.py check --path input/`，照它的步驟用自己的 CAD 另存 DXF
   - 依 `skills/review-team.md`（總流程）或逐步 `plan-intake → place-use-classification → code-requirements → gap-analysis` 執行
   - 產出四項固定交付物到 `output/`
   - 查法規先看知識圖譜：瀏覽器直接開 `graphify-out/graph.html`，或
     `python3 tools/regulation_graph.py neighbors --article §24`（免安裝），定位後再
     `python3 tools/regulation_index.py lookup --article '§24,§12'` 只載入相關條文

> 能力矩陣與選用套件一覽見 §五「工具層／環境」；完整目錄結構見 §三。法規計算、DXF 圖面標註與文件判讀都無需安裝即可執行。

---

<!-- PENDING-REVIEW:BEGIN -->
### ⚠️ 有 14 則待確認事項——請先處理再開始審圖

規則參數與現行條文（各類場所消防安全設備設置標準 民國 113 年 04 月 24 日修正）比對出 14 則差異，其中 14 則尚未裁示。受影響的規則：`18-8`、`18-9`、`detector-coverage`、`emergency-light-threshold`、`exit-light-threshold`、`extinguisher-count`、`extinguisher-threshold`、`fire-alarm-threshold`、`indoor-hydrant-coverage`、`indoor-hydrant-threshold`、`smoke-exhaust-threshold`、`sprinkler-head-spacing`、`sprinkler-threshold`、`subordinate-table`。

完整內容見 **[`待確認事項.md`](待確認事項.md)**。

```bash
python3 tools/pending_review.py status   # 開場檢查（有待確認事項會回結束碼 2）
python3 tools/pending_review.py list     # 逐則列出，交給具消防專業的使用者裁示
python3 tools/pending_review.py apply --all --by "○○○（消防設備師）"
```

裁示完成後 `apply` 會自動走先紅再綠更正參數、回填 `verified`、更新本區塊並移除疑義檔。在此之前，這些規則的輸出一律附「本參數尚未逐條確認」警語。
<!-- PENDING-REVIEW:END -->

---

## 一、目標與範圍

| 項目 | 內容 |
|------|------|
| 輸入 | `input/{案件名}/平面圖.dxf` 為審核主圖面，搭配同資料夾內的 `平面圖.pdf` 與相關審查文件；法規不放入案件輸入資料夾 |
| 正典資料 | 人工確認後的 `output/case.json`；DXF 與 PDF/文件只作為證據來源 |
| 核心能力 1 | 依法條清單計算各類消防設備的應設需求（種類、數量、免設或需人工判讀） |
| 核心能力 2 | 比對圖面既有設備配置與應設需求，列出缺項、數量不足、配置疑義與需人工判讀項目 |
| 輸出 | `output/` 下四項固定交付物：① 圖面審查 HTML（DXF 轉 SVG＋缺失導覽）② 問題清單 Markdown ③ 法條檢核清單 HTML（§14~§31 逐條窮舉）④ 複合用途及樓層屬性檢討 HTML |
| 防幻覺機制 | 規則庫採先紅再綠：測試 expected 必須逐字抄錄法條來源，紅燈確認後才編碼規則參數 |
| 使用者 | 消防設備師（士）、消防審查人員、建築師事務所 |

本系統輸出為審圖輔助草稿，最終審查判斷與法律責任歸屬專業消防人員。所有 `verified: false` 的法規參數都必須在輸出中附警語。

---

## 二、工作流程

```text
input/{案件名}/平面圖.dxf
input/{案件名}/平面圖.pdf
input/{案件名}/相關審查文件
        │
        ▼
/regulation-intake（首次建庫或法規換版；來源固定在 rules/core/）
        │  先紅再綠：測試 → verify-red → 規則 → strict 綠燈
        ▼
rules/equipment_rules.json
rules/regulation_index.json
        │
        ▼
/plan-intake
        │  讀取待審 DXF、輔助 PDF 與審查文件（使用執照、室內裝修申請書具名盤點＋證照萃取），
        │  依 skills/place-use-classification.md 建立第12條用途候選與圖說底稿
        ▼
【關卡1：人工確認】
        │  面積、用途、構造、樓層、既有設備、證照萃取欄位、低信心欄位逐項確認
        ▼
output/case.json
        │
        ▼
/mixed-use-review
        │  classify-mixed-use 依《複合用途建築物判斷基準》附表比對主從用途候選
        │  【人工確認：主用途／從屬配對／是否複合】→ §12 分類定案回填 case.json
        │  mixed_use_report.py 產出 ④ 複合用途及樓層屬性檢討 HTML
        ▼
/code-requirements
        │  check-applicability（§13 新舊標準適用，增改建/裝修/變更用途案件）
        │  fire_code_calc.py 門檻判斷與數量計算；工具輸出原文嵌入報告
        ▼
/gap-analysis
        │  應設 vs 既有比對；article_checklist.py 產生 §14~§31 逐條窮舉 check_results.json
        │  與 annotations.json
        ▼
【關卡2：准出】
        │  self-test、run-tests --strict、抽檢重算、法條可追溯檢查
        ▼
output/
├── {案件名}-圖面審查.html                  ① DXF→SVG 圖面標註＋缺失導覽
├── {案件名}-問題清單.md                    ② 缺失四級分類，詳列違反法條
├── {案件名}-法條檢核清單.html              ③ §14~§31 逐條窮舉打勾檢核表，條號連結法條原文
└── {案件名}-複合用途及樓層屬性檢討.html    ④ 主從用途／樓層屬性檢討表＋判定結論
```

大型或複雜案件可走 `/review-team`：滅火設備、警報設備、避難逃生設備、消防搶救必要設備並行審查，由 Team Lead 統整後仍產出同三項交付物。

### 兩階段 Excel 交付路線

實務上另有一條**兩階段**工作流程，內容與交付物 ③④ 同源（都以 `case.json` 為正典），交付格式為 Excel 工作簿：

```
/first-stage-review                          第一階段：複合用途建築物及樓層屬性檢討
        │  串接 /plan-intake → /mixed-use-review
        │  【必讀】rules/review_corrections.md（累積確認的通案修正）
        ▼
【關卡：case_facts_gate --stage first】       ready:false（結束碼 2）→ 不得匯出，逐項問使用者
        ▼
{案件名}-第一階段-複合用途及樓層屬性檢討.xlsx   複合用途檢討／用途判斷依據／來源資料／各樓層高度
        │
        ▼
/stage-two-review                            第二階段：消防安全設備設置標準檢討
        │  串接 /code-requirements → article_checklist.py
        │  【必讀】rules/stage_two_judgment_rules.md（§14~31 逐款判斷慣例，附條號）
        ▼
【關卡：case_facts_gate --stage second】       另檢查第一階段 §12 分類與判定已人工定案
        │  人工填 stage2_decisions.json（勾選一律由人工定案，工具不代為判斷）
        ▼
{案件名}-第二階段-設置標準檢討.xlsx            消防安全設備設置標準／應設置設備／待釐清事項
```

第一階段未完成不得執行第二階段；第一階段結果修正時必須從頭重跑完整第二階段。
`rules/stage_two_judgment_rules.md` 與 `rules/review_corrections.md` 均未經 `governance/` 核定，
援引其結論必附「本判斷慣例未經消防專業人員核定，以現行法規為準」。

兩階段的規則庫**刻意不存放條文原文與門檻數值**（轉抄會隨修法漂移），條文一律即時回查，
且先用圖譜把範圍縮到實際牽涉的幾條再載入：

```bash
python3 tools/regulation_graph.py neighbors --article §28        # 定位：引用網＋附表圖檔
python3 tools/regulation_index.py lookup --article '§28,§12'     # 載入：只取相關條文原文
```

§14~§31 全文一次載入約 1.5 萬字；定位後只載相關條通常 3~4 千字。

---

## 三、目錄結構

```text
drawing_review/
├── 待確認事項.md                     — 規則參數 vs 現行條文的待裁示差異（自動產生，全部裁示後自動移除）
├── input/
│   └── {案件名}/
│       ├── 平面圖.dxf                — 需要審核的主圖面（只讀不改）
│       ├── 平面圖.pdf                — 輔助對照用圖面 PDF（只讀不改）
│       └── 相關審查文件               — 申請書、審查表、說明書等案件文件
├── output/                           — 統一輸出資料夾（單一案件平放，不再分案件子目錄）
│   ├── case.json                     — 圖說底稿（正典資料）
│   ├── annotations.json              — SVG 標註定義
│   ├── check_results.json            — 檢核結果（供 HTML 產生）
│   ├── {案件名}-圖面審查.html
│   ├── {案件名}-問題清單.md
│   └── {案件名}-法條檢核清單.html
├── rules/                            — 固定法規資料夾與結構化法規規則庫
│   ├── equipment_rules.json
│   ├── rule_tests.json
│   ├── core/                         — 法規全文正典（單一全文 md ＋ _assets 附表圖檔、主從用途 PDF；非每案輸入）
│   ├── regulation_index.json         — 逐條索引（266 條）
│   └── regulation_articles/          — 逐條 JSON（含章/節階層、附表圖）
├── training/                         — 訓練模式（`/train`）
│   ├── inbox/                        — 待歸檔訓練素材投放區
│   ├── registry.json                 — 訓練批次總索引
│   └── {批次名}-{YYYYMMDD}/          — manifest.json／sources/／formats/／NOTES.md
├── practice_notes/                   — 實務註解層（法典未涵蓋情境的實務見解）
│   ├── active/                       — 現行有效註解（PN-{日期}-{序號}.json）
│   ├── staging/                      — 草擬中，待使用者「確認納入」
│   └── index.json                    — 註解索引（by_article／by_equipment／by_rule_id）
├── graphify-out/                     — 法規知識圖譜（含 source_fingerprint.json 指紋、node_ledger.json id 台帳）
├── governance/                       — 規則確認紀錄
│   ├── 待確認清單/                   — 疑義檔（rule-discrepancies-{日期}.json）＋ 已裁示/ 封存
│   ├── 核定表/                       — 核定表 HTML（需書面紀錄時）
│   ├── 核定紀錄/                     — verified 回填的 results JSON
│   └── 註解紀錄/                     — 實務註解追溯紀錄
├── skills/                           — 審圖 workflow 文件（只放執行指令）
│   └── README.md                     — 兩階段工作流程設計說明（不被 skill 載入）
├── tests/                            — Python 單元測試
└── tools/                            — 確定性工具
```

`input/` 一律視為只讀；每案輸入資料夾只放案件圖面與審查文件，不放法規檔。法規固定維護於 `rules/core/`，所有案件共用同一套經索引與測試的規則庫。所有案件產出寫入新的 `output/` 目錄。

---

## 四、核心設計決策

### 1. `case.json` 是正典，不是 DXF

DXF 提供座標、圖層、符號與標註位置，但消防設備應設需求與缺失結論仍以人工確認後的 `case.json` 為準。任何從圖面萃取的面積、用途、樓層、既有設備數量與低信心欄位，都必須經人工確認後才進入計算。

### 2. 計算交給工具，不交給 LLM

「是否應設」「應設多少」「缺口多少」必須透過 `tools/fire_code_calc.py` 或其他確定性工具計算。LLM 負責萃取、整理、分類與撰寫，不得心算或憑記憶引用法規數值。

### 3. SVG 是標註呈現，不是最終判定來源

`tools/dxf_svg_review.py` 以標準庫解析 DXF（`tools/dxf_parse.py`，零安裝），將常見實體轉成 SVG，並把 `annotations.json` 的缺失位置畫在圖上；`ezdxf` 只在二進位 DXF 等後備情形才用得到。消防設備符號多為圖塊（`INSERT`），圖面上以插入點標記呈現、幾何不展開——足以定位與清點，但**圖塊數不等於實際設置數量**。圖面不足以判定配置時，輸出「配置疑義」或「需人工判讀」，不得用視覺推測取代專業審圖。

### 4. 法規參數先紅再綠

規則庫的每個門檻、係數與數量參數都必須先有測試；測試 expected 需逐字抄錄法條來源並附頁碼與 quote。`run-tests --verify-red` 確認紅得正確後，才可編碼最小規則讓 `run-tests --strict` 轉綠。

### 5. 訓練模式：法典層與註解層雙軌

系統要「學會」新東西，只有兩條路，都不允許直接改規則參數：

| 學什麼 | 走哪條 | 落到哪 | 後續怎麼被叫到 |
|---|---|---|---|
| 新法源、實務表格、格式範本 | `/train`（丟 `training/inbox/`） | `rules/core/`、`rules/checklists/`、`rules/equipment_rules.json`（先紅再綠） | 既有工具零修改即讀得到 |
| 法典未涵蓋情境的判讀 | `/practice-note` | `practice_notes/active/` ＋ `index.json` | `check-gap` 下次自動比對命中 |
| 通案性工作流程修正 | `/train` 第五步 | `rules/review_corrections.md` 等 | 每次審圖的必讀前置 |

`training_intake.py` 在**程式層**拒絕把素材寫進 `equipment_rules.json`／`mixed_use_rules.json`／
`rule_tests.json`——訓練模式讓入庫更順，不讓入庫更鬆。實務註解只補充法典、不推翻法典：
免除法定應設設備的註解一律紅色警示，且未經使用者輸入「確認納入」禁止從 `staging` 移到 `active`。

訓練寫入後，`/train` 會**自動更新知識圖譜**。圖譜有兩個、各自獨立更新：

| | 法規圖譜 | 訓練圖譜 |
|---|---|---|
| 檔案 | `graphify-out/graph.json`（與上游共編） | `training/graph.json`（**純使用者所有**，不進版控） |
| 內容 | 條文節點、附表圖、法規術語概念 | 實務註解、審圖修正筆記、第二階段判斷慣例 |
| 更新 | `tools/regulation_graph_build.py`（零安裝、不需 API key） | `tools/training_graph_build.py build`（毫秒級） |
| 把關 | sha256 逐檔指紋 ＋ `verify` 差異關卡 | 節點內的語意摘要自證，不需指紋檔 |

**為什麼分家**：混在同一個檔時，法典層一重建就會把訓練層沖掉，於是每次重建都被迫
「先把註解併回去才准蓋章」，鏈上任一環卡住訓練成果就進不了圖譜；而 `graphify-out/*` 又被
`update_guard` 標為與上游共編，等於使用者的訓練成果住在會被覆寫的地段。分家後兩者互不阻擋，
`regulation_graph.py` 在**查詢時**合併，審圖指令完全不必改。

訓練圖譜指向法規圖譜的關聯以 **label 為耐久鍵**（`target_label`），node id 只是快取——
法規圖譜重建後 id 若對不上，關聯會標記為「懸空」留在圖譜裡等修，**絕不因為解析不到就
刪掉使用者的訓練成果**。

法規圖譜的**來源檔**是 `rules/core/`（法規全文 md、附表 PDF 與附表圖檔）、`rules/README.md`
與 `rules/regulation_articles/`——也就是圖譜真的從中抽出節點的檔案。`rules/equipment_rules.json`
與 `rules/mixed_use_rules.json` **不在**追蹤範圍：圖譜的節點沒有一個出自它們，追蹤只會讓每次
先紅再綠改參數都誤報過期。這個前提由 `check` 的 `untracked_graph_sources` 不變式持續驗證。

---

## 五、工具層

| 工具 | 用途 | 依賴 |
|------|------|------|
| `tools/onboarding.py` | 開場導引：載入倉庫後的狀態診斷（五步驟，結束碼 2 ＝ 有待處理）與操作簡介 | stdlib |
| `tools/fire_code_calc.py` | 法規門檻、數量計算、§13 適用判斷、主從用途比對、規則測試、自檢 | stdlib |
| `tools/regulation_index.py` | 法規 Markdown 轉逐條索引與按需查詢 | stdlib |
| `tools/regulation_graph.py` | 圖譜查詢：條文引用網／設備對應條文／概念關聯路徑／實務見解（查詢時自動合併法規與訓練兩個圖譜，免安裝 graphify） | stdlib |
| `tools/regulation_graph_build.py` | 法規圖譜重建：確定性骨架＋保留式語意層＋`verify` 差異關卡（零安裝、不需 API key） | stdlib |
| `tools/training_graph_build.py` | 訓練圖譜建置：實務註解、審圖修正筆記與判斷慣例 → `training/graph.json` | stdlib |
| `tools/graph_labels.py` | 圖譜 label 與條號的唯一解析器（`§19`／`第 19 條`／`第十九條` 收斂為正典寫法） | stdlib |
| `tools/article_checklist.py` | 依 case.json 產出 §14~§31 逐條窮舉 `check_results.json` | stdlib |
| `tools/mixed_use_report.py` | case.json 轉複合用途及樓層屬性檢討 HTML（交付物4） | stdlib |
| `tools/case_facts_gate.py` | 兩階段交付物匯出前的案件事實齊備關卡（不齊備結束碼 2） | stdlib |
| `tools/stage_report_xlsx.py` | 兩階段 Excel 工作簿產生（第一階段 4 分頁／第二階段 3 分頁） | `openpyxl` |
| `tools/checklist_html.py` | `check_results.json` 轉法條檢核清單 HTML | stdlib |
| `tools/standard_checklist_html.py` | 消防人員標準 Excel 表 + 答案 JSON 轉紅勾檢核 HTML | `openpyxl` |
| `tools/dxf_parse.py` | 零相依 ASCII DXF 解析（含 cp950 中文與版本判定），交付物1 的預設路徑 | stdlib |
| `tools/dwg_guide.py` | DWG 收件檢查（magic bytes 判格式）與各家 CAD 另存 DXF 引導 | stdlib |
| `tools/dxf_svg_review.py` | `annotations.json` + DXF 轉互動式 SVG 圖面審查 HTML | stdlib（二進位 DXF 才需 `ezdxf`） |
| `tools/pdf_annotate.py` | legacy：舊版 PDF 紅圈標註輸出 | `pymupdf` |
| `tools/verification_sheet.py` | 規則核定表匯出與回填 | stdlib |
| `tools/setup.sh` | 選用：一鍵安裝相依套件（`--with-graph` 併裝 graphify）。裝不起來不影響審圖主線，也不影響圖譜重建 | bash + pip |
| `tools/check_env.py` | 環境自檢：能力矩陣——現在能做什麼、做不到的替代路徑 | stdlib |

### 環境（預設什麼都不用裝）

本倉庫的使用者多半只裝了一個 AI 桌面版就開始用，沙盒與安全限制讓 `pip install` 往往失敗。所以審圖主線刻意做成零安裝：

| 能力 | 需要安裝嗎 | 說明 |
|---|---|---|
| 法規門檻計算、法條查詢 | **不用** | 核心工具只用 Python 標準庫 |
| 交付物1：DXF 圖面標註 | **不用** | 文字 DXF 由 `tools/dxf_parse.py` 以標準庫解析 |
| PDF／DOCX／XLSX 判讀 | **不用** | 由 AI 直接讀取檔案 |
| DWG 圖面 | 不用（但要手動一步） | 用你的 CAD 另存 DXF，見 `tools/dwg_guide.py check` |
| 兩階段 Excel 交付物匯出 | `openpyxl` | 缺套件時改用 HTML 版法條檢核清單，內容相同 |
| 平面圖 PDF 紅圈標註（legacy） | `pymupdf` | 缺套件時改用交付物1 的 HTML／SVG 標註，功能更完整 |
| 二進位 DXF | `ezdxf` | 或請使用者改存 ASCII DXF（工具會直接這樣指引） |

```bash
python3 tools/check_env.py   # 這台電腦現在能做什麼、做不到的怎麼繞
```

裝得起套件的環境（自架 Linux、有 WSL 的進階使用者）可以一次補齊，但**這是加分項不是門檻**：

```bash
bash tools/setup.sh          # 安裝 requirements.txt 並自檢
```

工具在缺套件時一律給出替代路徑，不會靜默失敗，也不會把使用者卡在「還不能開始」。

#### graphify（選用，純加值）

`graphify-out/graph.html` 直接用瀏覽器開即可瀏覽，**無需安裝任何東西**。
**查詢與重建都不需要 graphify**——`tools/regulation_graph.py` 與
`tools/regulation_graph_build.py` 都只用標準庫。裝了它只多兩件事：重繪 `graph.html`
視覺化，以及 `graphify query/explain/path` CLI。（重建後 `graph.html` 會是舊版視覺化，
查詢請以 `regulation_graph.py` 為準。）

- 專案首頁：<https://github.com/Graphify-Labs/graphify>
- 安裝（擇一）：

```bash
bash tools/setup.sh --with-graph                 # 隨本專案一起裝（自動偵測 uv / pip）
# 或手動：
uv tool install graphifyy && graphify install    # 建議（uv）
python3 -m pip install graphifyy                  # 或用 pip
```

---

## 六、資料介面

### `case.json` 圖面來源

```json
{
  "source_drawings": [
    {
      "drawing_id": "1F",
      "path": "input/示範案件/平面圖.dxf",
      "floor": "1F",
      "unit": "mm",
      "model_bbox": [0, 0, 50000, 32000],
      "layers": ["WALL", "DOOR", "FIRE_EQUIPMENT"]
    }
  ],
  "source_documents": [
    {"type": "輔助平面圖", "path": "input/示範案件/平面圖.pdf"},
    {"type": "審查文件", "path": "input/示範案件/消防安全設備審查表.pdf"}
  ],
  "floors": [
    {
      "floor": "1F",
      "layout_index": {
        "drawing_id": "1F",
        "bbox": [1200, 1800, 8500, 6200],
        "position_confidence": "medium"
      }
    }
  ]
}
```

### `annotations.json` 標註來源

```json
{
  "case_name": "示範案件",
  "output_html": "output/示範案件-圖面審查.html",
  "source_drawings": [
    {"drawing_id": "1F", "path": "input/示範案件/平面圖.dxf", "floor": "1F", "unit": "mm"}
  ],
  "annotations": [
    {
      "issue_id": 1,
      "drawing_id": "1F",
      "bbox": [1200, 1800, 8500, 6200],
      "label": "滅火器數量不足",
      "note": "1F 甲類場所應設滅火效能值 5，圖面僅 2 具（§14、§31）",
      "severity": "一般缺失",
      "position_confidence": "medium"
    }
  ]
}
```

---

## 七、常用命令

```bash
# 開場導引（載入倉庫的第一件事；結束碼 2 ＝ 有待處理步驟）
python3 tools/onboarding.py status
python3 tools/onboarding.py status --format json   # 供工具串接
python3 tools/onboarding.py intro                  # 操作簡介（印在終端機）

# 一鍵安裝相依套件並自檢（等同 pip install -r requirements.txt）
bash tools/setup.sh
python3 tools/check_env.py

# 法規調閱：先用圖譜定位條號與關聯，再只載入那幾條原文
python3 tools/regulation_graph.py neighbors --article §24      # 該條引用網＋附表圖＋實務註解
python3 tools/regulation_graph.py articles --equipment 排煙設備  # 哪些條文規範該設備
python3 tools/regulation_graph.py path --from 無開口樓層 --to 排煙設備
python3 tools/regulation_graph.py notes --article §24           # 專查該條的實務註解

# 法規索引（lookup 支援單條、範圍與逗號列舉；不要一次載入 §14~§31 全文）
python3 tools/regulation_index.py build
python3 tools/regulation_index.py lookup --article '§19'
python3 tools/regulation_index.py lookup --article '§24,§12'
python3 tools/regulation_index.py lookup --article '§20-§22,§28'
python3 tools/regulation_index.py lookup --equipment '滅火器'

# 規則庫自檢與先紅再綠測試
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}

# 門檻判斷與數量計算
python3 tools/fire_code_calc.py check-threshold --case output/case.json
python3 tools/fire_code_calc.py check-applicability --case output/case.json   # §13 新舊標準
python3 tools/fire_code_calc.py classify-mixed-use --case output/case.json    # 主從用途候選
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40

# 交付物產生
python3 tools/dxf_svg_review.py --annotations output/annotations.json
python3 tools/article_checklist.py --case output/case.json     # §14~31 逐條窮舉
python3 tools/checklist_html.py --results output/check_results.json
python3 tools/mixed_use_report.py --case output/case.json      # 交付物4

# 兩階段 Excel 交付路線
python3 tools/case_facts_gate.py --stage first  --case output/case.json
python3 tools/case_facts_gate.py --stage second --case output/case.json
python3 tools/stage_report_xlsx.py first-stage --case output/case.json
python3 tools/stage_report_xlsx.py stage-two --decisions output/stage2_decisions.json --case output/case.json

python3 tools/standard_checklist_html.py --input rules/checklists/各類場所消防安全設備設置標準14~31條判斷用.xlsx --answers output/standard_checklist_answers.json --output output/{案件名}-標準表檢核.html

# 產生標準表答案範本（審核時只填 checked ID）
python3 tools/standard_checklist_html.py --input rules/checklists/各類場所消防安全設備設置標準14~31條判斷用.xlsx --dump-answer-template output/standard_checklist_answers.template.json --output output/{案件名}-標準表檢核.html

# 訓練模式（讓系統學會新東西的入口）
python3 tools/training_intake.py classify                     # 乾跑：inbox 素材路由建議
python3 tools/training_intake.py apply --batch {批次名} --operator {歸檔人}
python3 tools/training_intake.py status                       # 工作流程前置檢查（2 = 圖譜需補建）
python3 tools/graph_status.py check                           # 0=新鮮 2=過期 3=尚未建立基準
python3 tools/graph_status.py stamp                           # 重建圖譜後蓋章

# 實務註解（法典未涵蓋情境）
python3 tools/fire_code_calc.py check-gap --case output/case.json
python3 tools/practice_note_engine.py draft --gap output/gap_candidates.json --case {案件名}
python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/{id}.json
python3 tools/practice_note_engine.py apply --draft practice_notes/staging/{id}.json --approved-by {批准人} --confirm 確認納入
python3 tools/practice_note_engine.py test --strict

# 實務註解 → 訓練圖譜（LLM 語意抽取 ＋ 確定性建層；沒做完，後續查圖譜查不到訓練成果）
python3 tools/practice_note_graph.py plan                     # 0=齊備 2=有待語意抽取
python3 tools/practice_note_graph.py contract --note {註解 id} # 印出抽取契約給 LLM 填
python3 tools/practice_note_graph.py validate --extraction practice_notes/graph_extractions/{id}.json
python3 tools/training_graph_build.py build                   # 建 training/graph.json（冪等）
python3 tools/training_graph_build.py check                   # 0=已納入 2=未納入

# 待確認事項（開場必做）
python3 tools/pending_review.py status                        # 結束碼 2 = 有待確認事項
python3 tools/pending_review.py list                          # 逐則列給使用者裁示
python3 tools/pending_review.py decide --id D-015-01 --decision 採納更正 --by "{確認人}"
python3 tools/pending_review.py apply --all --by "{確認人}"    # 先紅再綠自動更正＋回填 verified
python3 tools/pending_review.py render                        # 重產 待確認事項.md 並同步 README

# 規則逐條確認（使用者本身即為消防專業人員，不需另送外部核定）
python3 tools/verification_sheet.py list                      # 列出待確認規則，於對話中逐條確認
python3 tools/verification_sheet.py discrepancies             # 列出與現行條文比對出的差異，逐則裁示
python3 tools/verification_sheet.py apply --results {結果JSON}

# 測試
python3 -m unittest discover tests
```

---

## 八、缺失分類與報告語言

報告與交付物使用繁體中文與台灣消防法規用語。缺失分級固定為：

- `重大缺失`：法定應設之設備類別完全未設。
- `一般缺失`：設備已設但數量不足或規格不符。
- `配置疑義`：數量達標但配置可能不符法定距離，需圖面逐點量測。
- `需人工判讀`：依現有資料無法判定。
- `建議事項`：無強制法源的實務建議，必須標明「無強制法源」。

判定「符合」與「不適用／免設」時，也要保留可覆核的計算過程與條文依據。

---

## 九、建置路線圖

| 階段 | 內容 | 狀態 |
|------|------|------|
| Phase 0 法規編碼 | 設置標準逐條結構化為 rules JSON，消防專業人員逐條核定 | 示例子集已建；2026-07-25 完成與現行條文（113.04.24 修正）逐條比對：**已確認** §13 適用標準、主從用途對照表 31 項、§18 附表項目一~七與註一~五（`verified: true`）；**待裁示** equipment_rules 其餘 11 條，差異逐則列於 `governance/待確認清單/`（`verification_sheet.py discrepancies`） |
| Phase 1 規則引擎 MVP | 人工確認 `case.json` → 應設需求計算 | 已具備 |
| Phase 2 DXF/SVG 工具層 | DXF 轉 SVG 圖面審查 HTML，缺失清單導覽與高亮定位 | 已導入工具骨架 |
| Phase 3 圖面萃取 | 從 DXF 圖層、符號與審查文件萃取 `case.json`，並經人工確認 | 流程定義中 |
| Phase 4 配置幾何檢核 | 將步行距離、水平距離、涵蓋半徑從疑義升級為座標幾何檢核 | 待建 |
| Phase 5 多 Agent 編排 | 四類設備審查員並行，Team Lead 彙整 | skill 已建 |
| Phase 6 品管准出 | 抽檢重算、法條引用逐項可追溯性檢查、自動化 CI | 部分已建 |
| Phase 7 實戰迭代 | 實案回饋轉成規則、測試、工具檢查點 | 已建（`/train` 訓練模式 ＋ `/practice-note` 實務註解），持續累積 |

---

## 十、待補事項備忘（後續跟進清單）

> 本節為待補文件與待辦事項的備忘錄，完成一項勾銷一項（`[ ]` → `[x]` 並注記日期）。

| # | 狀態 | 事項 | 觸發條件／後續動作 |
|---|------|------|-------------------|
| 1 | [ ] 待文件 | **《複合用途建築物判斷基準》本文**（從屬認定要件：管理權、使用形態、面積比例門檻等文字規定）尚未提供，目前僅有附表 | 文件放入 `rules/core/` 後：先紅再綠補 `mixed_use_rules.json` 的 `subordinate-criteria`／`subordinate-thresholds` 規則，`classify-mixed-use` 量化判定由「需人工判讀」升級為工具計算 |
| 2 | [ ] 待文件 | 「14~31 條判斷用」勾選表**實務範例**尚未提供 | 取得後對齊 `checklist_html.py` 檢核表版面與欄位 |
| 3 | [ ] 2026-07-26 部分完成 | **空白官方表單已入庫**：建築物室內裝修 E1 系列五份（E1-1 圖說審查表、E1-2 圖說申請書、E1-4 竣工材料書、E1-5 簽證表、E1-6 竣工查驗表）置於 `input/範例/室內裝修表單範本/`（.doc 原件＋.md 文字轉錄＋欄位對照）。**仍缺**：實際案件的使用執照與已填寫之室內裝修申請書樣本（可去識別化）、E1-3 表單 | 已依 E1-2 欄位核對 `interior_renovation`／`change_of_use`／`use_permit` schema：對照結果見該資料夾 README；發現【原有樓地板面積】、【合格證明字號】、【核發日期】、【歷次合格證明字號】現行 schema 無對應欄位，需要時走先紅再綠擴充。取得已填寫樣本後再驗證萃取信心度與版面辨識 |
| 4 | [ ] 待入庫 | **§16、§18、§20、§21、§22、§25、§26、§27、§29、§30 規則尚未入庫**——檢核表以「⚪需人工判讀（規則未入庫）」逐條呈現 | 逐條先紅再綠入 `equipment_rules.json`（條文原文已在 `rules/regulation_articles/`，可隨時進行） |
| 5 | [x] 2026-07-25 部分完成 | **已確認**：`applicability-article-13`（§13）、`subordinate-table`（對照表 31 項）、§18 附表項目一~七＋註一~五＋二氧化碳限制，均已 `verified: true`（紀錄見 `governance/核定紀錄/results-20260725-*.json`）。對照表疑字經原件文字層核對後校讀更正（更氣室→電氣室、視廳→視聽、百貨適場→百貨商場、超集市場→超級市場、診療至→診療室、物品食庫→物品倉庫），並補回第（7）項漏抄之「遊戲室」，原印字留存於各項 `source_text` | 剩餘 **equipment_rules 11 條**維持 `verified: false`：比對出錯值／適用範圍不符／款次未涵蓋，14 則差異列於 `governance/待確認清單/rule-discrepancies-20260725.json`。下一步：`python3 tools/verification_sheet.py discrepancies` 逐則裁示 → 採納者走先紅再綠更正 → `apply` 回填 |
| 5-1 | [x] 2026-07-26 | **圖譜新鮮度關卡追蹤錯檔案**：`graph_status.py` 把 `equipment_rules.json`／`mixed_use_rules.json` 列為圖譜來源，但圖譜 482 個節點無一出自它們（`node.source_file` 只有 `rules/core/` 與 `rules/README.md`），導致每次先紅再綠改參數都誤報「圖譜過期」 | 已修正 `SOURCE_GLOBS` 為圖譜真正的來源檔，並新增 `untracked_graph_sources` 不變式：日後重建出的圖譜若含這些檔的節點，`check` 會紅燈要求加回清單。基準已重新蓋章（`stamp_reason` 記錄事由），`training/graph_pending.json` 移除 |
| 6 | [ ] 待實作 | 戊類複合用途之 §12-1 面積合計方式（以各目為單元合計）尚未進 `check-threshold` 引擎 | 判定為戊類的案件目前由 `/code-requirements` 報告注記、人工調整面積合計；後續先紅再綠入引擎 |

## 十一、免責聲明

本專案為審圖輔助工具研究，內建法規參數為開發示例。未經主管機關或消防專業人員核定前，不得作為正式審查依據；實際審查以現行法規條文、主管機關解釋與專業消防人員判斷為準。

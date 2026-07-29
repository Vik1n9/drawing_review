# AI 作業流程（半自動化）

**行為契約正本是 [`AGENTS.md`](../AGENTS.md)**（跨 AI 工具共用，`CLAUDE.md` 只是指向它的指標）。
契約只放「載入任何 skill 之前就必須生效」的六條底線與路由；本檔是它的展開——
**每個階段做什麼、卡在哪個關卡、跑哪一行命令**。

- [1. 開場程序](#1-開場程序)
- [2. 半自動化的邊界](#2-半自動化的邊界)
- [3. skill 路由](#3-skill-路由)
- [4. 人工關卡](#4-人工關卡)
- [5. 命令速查](#5-命令速查)

---

## 1. 開場程序

載入倉庫後的**第一個動作**，不需使用者要求：

```bash
python3 tools/onboarding.py status              # 結束碼 0 ＝ 可直接開始；2 ＝ 有待處理步驟
python3 tools/onboarding.py status --format json  # 供工具串接
```

- 結束碼 **0**：直接開始審圖，**不要讀 `skills/onboarding.md`**
- 結束碼 **2**：讀 `skills/onboarding.md`，依其流程逐步引導使用者

Claude Code 已設 SessionStart hook 自動執行這一步；其他工具由 `AGENTS.md` 的開場條文觸發。

規則差異未裁示前照常審圖是允許的，但**受影響規則的輸出必須附「本參數尚未逐條確認」警語**。

---

## 2. 半自動化的邊界

「半自動」的界線只有三條，每條都對應一個具體行為：

| 界線 | 具體行為 |
|------|----------|
| **唯讀命令可直接跑** | `status`／`list`／`check`／`neighbors`／`lookup`／`self-test` 等不寫檔的命令，不必先問 |
| **會改動系統的動作先取得同意** | 安裝套件、回填裁示、重建圖譜、寫入 `rules/`／`governance/`／`practice_notes/`——先說明再做 |
| **法規事項不得代替使用者裁示** | 疑義裁示、§12 主從用途定案、第二階段勾選，一律由具消防專業的使用者決定 |

另外三條硬紅線（完整版見 `AGENTS.md` 六條底線）：

1. **禁止心算、禁止憑記憶引法規數值**——一律 `python3 tools/fire_code_calc.py`，工具輸出原文嵌入報告
2. **`case.json` 是正典**——圖面只是證據，不得跳過人工確認直接推算
3. **不確定就標「需人工判讀」**——嚴禁以推測、預設值或未提供的圖說填充

`input/` 只讀，產出寫 `output/`；報告用繁體中文與台灣消防法規用語。

> **更新／重裝倉庫前必讀 `skills/safe-update.md`。** 使用者說「更新」「拉最新的」
> 「重新下載」時，在 `update_guard.py snapshot` 成功之前，`git reset --hard`、
> `git checkout -- .`、`git restore`、`git clean`、以及刪目錄重新 clone **一律禁止**——
> 那會抹掉使用者數月的成果，未提交的改動連 reflog 都救不回。

---

## 3. skill 路由

`skills/` 下的檔名。Claude Code 可用斜線指令，**其他工具用自然語言＋檔名**——
面向使用者的文字不得只給斜線指令。

| 情境 | 載入 |
|------|------|
| 審圖主線 | `plan-intake` → `mixed-use-review`（§12 定案）→ `code-requirements`（含 §13）→ `gap-analysis`（三項交付物） |
| 用途與樓層屬性判定 | `place-use-classification` |
| 大型案件分工 | `review-team`（四類設備並行，Team Lead 統整） |
| 兩階段 Excel 交付 | `first-stage-review` → `stage-two-review` |
| 改規則參數 | `red-green` ＋ `regulation-intake` |
| 訓練素材／實務見解 | `training-mode`／`practice-note` |
| 更新或重裝倉庫 | `safe-update` |
| 開場引導（僅結束碼 2 時） | `onboarding` |

**查法規的順序固定**：先用圖譜定位，再只載入那幾條原文。

```bash
python3 tools/regulation_graph.py neighbors --article §28     # 定位：引用網＋附表圖＋實務註解
python3 tools/regulation_index.py lookup --article '§28,§12'  # 載入：只取相關條文原文
```

§14~§31 全文一次載入約 1.5 萬字；定位後只載相關條通常 3~4 千字。

---

## 4. 人工關卡

關卡的定義是：**沒過就不准往下走**，不是「建議確認一下」。

| 關卡 | 位置 | 沒過會怎樣 |
|------|------|-----------|
| 待確認事項 | 開場 | 照常審圖，但受影響規則輸出必附警語 |
| 案件事實確認 | `/plan-intake` 之後 | 面積、用途、構造、樓層、既有設備、低信心欄位逐項確認才寫進 `case.json` |
| §12 分類定案 | `/mixed-use-review` | 主用途／從屬配對／是否複合由使用者定案，工具只給候選 |
| 兩階段齊備關卡 | 匯出 Excel 前 | `case_facts_gate.py` 回結束碼 2 → **不得匯出**，逐項問使用者 |
| 第二階段勾選 | `stage2_decisions.json` | 勾選一律由人工定案，工具不代為判斷 |
| 准出 | 交付前 | `self-test`、`run-tests --strict`、抽檢重算、法條可追溯檢查 |
| 實務註解納入 | `practice_note_engine.py apply` | 未輸入「確認納入」不得從 `staging` 移到 `active` |

---

## 5. 命令速查

工具用法一律 `--help`。以下為常用集合。

### 開場與環境

```bash
python3 tools/onboarding.py status                 # 開場診斷（結束碼 2 ＝ 有待處理）
python3 tools/onboarding.py intro                  # 操作簡介
python3 tools/check_env.py                         # 能力矩陣：能做什麼、做不到的替代路徑
bash tools/setup.sh                                # 選用：安裝相依套件（--with-graph 併裝 graphify）
python3 tools/update_guard.py check                # 本機成果保護（唯讀）
python3 tools/update_guard.py snapshot --note "更新前"
```

### 法規調閱（先圖譜定位，再載入條文）

```bash
python3 tools/regulation_graph.py neighbors --article §24        # 引用網＋附表圖＋實務註解
python3 tools/regulation_graph.py articles --equipment 排煙設備   # 哪些條文規範該設備
python3 tools/regulation_graph.py path --from 無開口樓層 --to 排煙設備
python3 tools/regulation_graph.py notes --article §24            # 專查該條的實務註解

python3 tools/regulation_index.py build
python3 tools/regulation_index.py lookup --article '§19'
python3 tools/regulation_index.py lookup --article '§24,§12'
python3 tools/regulation_index.py lookup --article '§20-§22,§28'
python3 tools/regulation_index.py lookup --equipment '滅火器'
```

### 規則庫自檢與先紅再綠

```bash
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}
```

### 門檻判斷與數量計算

```bash
python3 tools/fire_code_calc.py check-threshold --case output/case.json
python3 tools/fire_code_calc.py check-applicability --case output/case.json   # §13 新舊標準
python3 tools/fire_code_calc.py classify-mixed-use --case output/case.json    # 主從用途候選
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40
```

### 交付物產生

```bash
python3 tools/dxf_svg_review.py --annotations output/annotations.json   # ①
python3 tools/article_checklist.py --case output/case.json              # §14~31 逐條窮舉
python3 tools/checklist_html.py --results output/check_results.json     # ③
python3 tools/mixed_use_report.py --case output/case.json               # ④

# 兩階段 Excel 路線
python3 tools/case_facts_gate.py --stage first  --case output/case.json
python3 tools/case_facts_gate.py --stage second --case output/case.json
python3 tools/stage_report_xlsx.py first-stage --case output/case.json
python3 tools/stage_report_xlsx.py stage-two --decisions output/stage2_decisions.json --case output/case.json

# 消防人員標準表檢核 HTML（--dump-answer-template 產生只填 checked ID 的答案範本）
python3 tools/standard_checklist_html.py \
    --input rules/checklists/各類場所消防安全設備設置標準14~31條判斷用.xlsx \
    --answers output/standard_checklist_answers.json \
    --output output/{案件名}-標準表檢核.html
```

### 待確認事項與規則確認

```bash
python3 tools/pending_review.py status                        # 結束碼 2 ＝ 有待確認事項
python3 tools/pending_review.py list                          # 逐則列給使用者裁示
python3 tools/pending_review.py decide --id D-015-01 --decision 採納更正 --by "{確認人}"
python3 tools/pending_review.py apply --all --by "{確認人}"    # 先紅再綠自動更正＋回填 verified
python3 tools/pending_review.py render                        # 重產 待確認事項.md 並同步 README

python3 tools/verification_sheet.py list                      # 待確認規則，於對話中逐條確認
python3 tools/verification_sheet.py discrepancies             # 與現行條文比對出的差異
python3 tools/verification_sheet.py apply --results {結果JSON}
```

### 訓練模式與實務註解

```bash
python3 tools/training_intake.py classify                     # 乾跑：inbox 素材路由建議
python3 tools/training_intake.py apply --batch {批次名} --operator {歸檔人}
python3 tools/training_intake.py status                       # 前置檢查（2 ＝ 圖譜需補建）
python3 tools/graph_status.py check                           # 0=新鮮 2=過期 3=尚未建立基準
python3 tools/graph_status.py stamp                           # 重建圖譜後蓋章

python3 tools/fire_code_calc.py check-gap --case output/case.json
python3 tools/practice_note_engine.py draft --gap output/gap_candidates.json --case {案件名}
python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/{id}.json
python3 tools/practice_note_engine.py apply --draft practice_notes/staging/{id}.json \
        --approved-by {批准人} --confirm 確認納入
python3 tools/practice_note_engine.py test --strict

# 實務註解 → 訓練圖譜（沒做完，後續查圖譜查不到訓練成果）
python3 tools/practice_note_graph.py plan                     # 0=齊備 2=有待語意抽取
python3 tools/practice_note_graph.py contract --note {註解 id}  # 印出抽取契約給 LLM 填
python3 tools/practice_note_graph.py validate --extraction practice_notes/graph_extractions/{id}.json
python3 tools/training_graph_build.py build                   # 建 training/graph.json（冪等）
python3 tools/training_graph_build.py check                   # 0=已納入 2=未納入
```

### 測試

```bash
python3 -m unittest discover tests
```

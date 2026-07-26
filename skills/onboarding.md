# 開場導引（載入本倉庫後的第一件事）

把剛載入本倉庫的使用者帶到「可以開始審圖」的狀態：診斷環境與資料狀態，
依序引導他裁示疑義表、確認法規圖譜、補齊環境套件，最後印出操作簡介。

觸發時機：**只有 `python3 tools/onboarding.py status` 的結束碼為 `2` 時才需要讀本檔。**
結束碼 `0` 代表導引已經走完，直接開始審圖即可——不要載入本檔、不要把導引內容講給使用者。
`AGENTS.md`（正本）因此只留一行開場檢查與紅線，把流程細節集中在這裡：
這些內容只有導引當下用得到，不該每個工作階段都佔用 context。

Claude Code 由 SessionStart hook 自動跑出診斷；其他 AI 工具（Codex、OpenCode …）
依 `AGENTS.md` 的開場條文自行執行下面的第零步。使用者說「帶我開始」「這個怎麼用」
「我第一次用」時同樣走本流程。

**使用者是消防專業人員，不是工程師。** 他懂法規，但不一定懂終端機、git 或 AI 工具。
你的任務是把技術細節擋在他前面，只把「需要他做法規判斷的事」端到他面前。

## 前置檢查

1. 本流程**不做任何法規判斷**（審圖最高原則 2／4／5）——只做狀態診斷與流程引導
2. 本流程**不得代替使用者裁示**任何規則參數（見第一步）
3. 不需要先安裝任何東西：`tools/onboarding.py` 只用 Python 標準庫

## 工具中立條款（每一步都適用）

使用者可能用任何 AI 工具載入本倉庫，所以：

- **不要假設有斜線指令。** `/gap-analysis`、`/train` 這類指令只有 Claude Code 有。
  引導時一律給「可複製的命令」＋「一句自然語言請求」，斜線指令最多只能當附註。
- **不要硬貼 `python3`。** 照 `status --format json` 回報的 `interpreter` 改寫所有命令
  （Windows 常只有 `python`）。同理，`bash tools/setup.sh` 只在 `has_bash` 為真時建議。
- **不要假設你有結構化選項提問的能力。** 逐則裁示一律以**純文字編號清單**提問，
  任何工具都做得到。
- **繁體中文**（台灣法規用語），對象是不熟電腦的使用者：講「你要做什麼」，
  不要複述工具內部術語。

## 唯讀自動、寫入先問（本流程的安全底線）

| 可直接執行，不必先問 | 必須先說明並取得使用者同意 |
|---|---|
| `onboarding.py status` / `intro` | `bash tools/setup.sh`（安裝套件，動到他的電腦） |
| `check_env.py` | `bash tools/setup.sh --with-graph`（安裝 graphify） |
| `pending_review.py list` / `show` | `pending_review.py decide` / `apply`（改規則庫） |
| `graph_status.py check` | `pending_review.py render`（改倉庫檔案） |
| `fire_code_calc.py self-test` / `run-tests --strict` | 圖譜重建與 `graph_status.py stamp` |
| `verification_sheet.py list` / `discrepancies` | 任何 `git` 寫入操作 |

`status` 的輸出已把每條命令標成`（唯讀，可直接跑）`或`（寫入，需你同意）`——照著標記走即可。

## 執行流程

### 第零步 跑診斷

```bash
python3 tools/onboarding.py status
```

結束碼 `0` ＝ 全部就緒（輸出只有三行），跟使用者說可以開始審圖，並問他要不要看操作簡介。
結束碼 `2` ＝ 有待處理步驟，照輸出的順序往下走。

**只把待處理的步驟講給使用者**，已就緒（✅）的不必逐項朗誦——他不需要知道系統內部有幾個檢查。
需要精確欄位時用 `--format json`。

### 第一步 待確認事項裁示（最先處理）

規則庫裡有些參數與現行條文比對出差異，差異寫在 `governance/待確認清單/`，
並以 `待確認事項.md` 呈現。這些**必須由使用者本人（他就是消防專業人員）逐則裁示**。
未裁示前照常審圖是允許的，但受影響規則的輸出必須附「本參數尚未逐條確認」警語，
且不得把該規則的結論當成已核定的法源依據。

```bash
python3 tools/pending_review.py list
```

把每一則整理成使用者讀得懂的形式問他，**一次問一則或分小批，不要一次倒 14 則**：

```
第 1 則（共 14 則）  滅火器設置門檻 §14
  條文原文：{逐字引述}
  規則現值：{現值}
  差異：{差異描述}
  請問要「採納更正」、「維持現值」，還是「另有更正」（請給正確值與理由）？
```

使用者回覆後才記錄，並在批次結束時執行修正：

```bash
python3 tools/pending_review.py decide --id {ID} --decision {採納更正|維持現值|另有更正} --by "{確認人}"
# 多則可用 --results {裁示JSON} 一次記錄
python3 tools/pending_review.py apply --all --by "{確認人}"
```

`apply` 會自動走先紅再綠（把條文原文寫進 `rule_tests.json` 的 expected → 確認轉紅 →
才改參數 → 確認轉綠），接著回填 `verified: true`、重產 `待確認事項.md`、同步 README 區塊；
全部裁示完畢時自動移除 `待確認事項.md` 並把疑義檔封存到 `governance/待確認清單/已裁示/`。

三條紀律，一條都不能省：

- **不得代替使用者裁示**——工具只執行已記錄的裁示。你不得自行決定採納或維持，
  也不得因為「條文原文看起來就是這樣」就幫他勾。看不出他的意思就再問一次。
- **不得跳過先紅再綠**——`apply` 內建 Verify RED 關卡（把條文原文寫進測試 expected →
  確認轉紅 → 才改參數 → 確認轉綠），測試沒紅或紅得不對即整批回滾。不要繞過它改參數。
- **`apply` 是寫入操作**——執行前告知使用者它會改動 `rules/` 與 `rule_tests.json`。

收尾：

```bash
python3 tools/fire_code_calc.py self-test && python3 tools/fire_code_calc.py run-tests --strict
```

### 第二步 法規圖譜

**先講清楚「查詢不用裝任何東西」**——`graphify-out/graph.json` 已在倉庫內，
`tools/regulation_graph.py` 只用標準庫。使用者只是要查法規的話，這一步什麼都不用做：

```bash
python3 tools/regulation_graph.py neighbors --article §24
```

只有兩種情況才需要安裝 `graphify`（**不要對只查詢的使用者推銷安裝**）：

1. 他改了 `rules/core/` 的法規全文，需要重建圖譜
2. 他想用 `graphify query/explain/path` 的 CLI 查詢

要裝的話先取得同意，再依 `status` 給的命令執行（有 bash 用 `bash tools/setup.sh --with-graph`，
沒有 bash 用 `{interpreter} -m pip install graphifyy`）。

`status` 顯示圖譜新鮮度為 `stale`／`notes_missing`／`no_baseline` 時，代表來源檔改了
但圖譜沒跟上，此時查到的關聯可能不是最新的——照 `status` 印出的 `REBUILD_HINT` 處理，
重建後必須重跑 `practice_note_graph.py merge` 再 `graph_status.py stamp`。

**邊界**：圖譜只是索引與導覽，用來定位條號與關聯。門檻數值與計算一律回法條原文與
`fire_code_calc.py`，不得引用圖譜節點標題當作法規數值。

### 第三步 環境工具

核心計算與法規查詢只用標準庫，什麼都不裝也能跑；缺套件只影響**特定交付物**：

| 缺的套件 | 影響 |
|---|---|
| `ezdxf` | 交付物1（DXF 轉 SVG 圖面標註）產不出來 |
| `openpyxl` | 兩階段 Excel 交付物與 xlsx 標準表檢核產不出來 |
| `pymupdf` | 平面圖 PDF 紅圈標註產不出來 |

這樣講給使用者聽，讓他知道「現在能做什麼、裝了以後多能做什麼」，再問他要不要裝。
**同意後**才執行 `status` 給的安裝命令，裝完重跑 `python3 tools/check_env.py` 確認。

### 第四步 規則庫健康

`status` 已跑過 `self-test` 與 `run-tests --strict`。

- 兩者皆通過 → 一句話帶過即可
- 任一失敗 → **這是阻擋項**：規則測試沒全綠的規則庫不得用來交付審圖結果。
  把失敗訊息給使用者看，並說明在修好之前產出的結論不可信

另外 `status` 會報「還有 N 條規則尚未逐條確認」——這些不阻擋審圖，但輸出時必須附
「本參數尚未逐條確認」警語。使用者想一次清掉的話走 `verification_sheet.py list`。

### 第五步 顯示操作簡介

```bash
python3 tools/onboarding.py intro
```

**流程的最後一件事。** 把輸出完整給使用者看，不要改寫或摘要——這份簡介是寫給他讀的。
然後問他要不要現在就開一個案件，並告訴他圖面要放進 `input/{案件名}/drawings/`。

## 完成契約

- 使用者知道：他要做什麼（放圖 → 說要審哪個案件 → 收 `output/` 交付物）、會拿到什麼四項交付物、哪些事情系統不會替他猜
- 所有寫入操作都是在他明確同意後才執行的
- 疑義表的每一則裁示都出自他本人，沒有任何一則是你代勞的
- 導引**可以中斷**：`status` 是冪等診斷，沒走完的步驟下次開場會再次出現，不必一次做完
- 走完後 `python3 tools/onboarding.py status` 的結束碼為 `0`（或剩下的項目是使用者主動選擇擱置的，且你已告知擱置的後果）
- **導引完成即退場**：結束碼轉 `0` 之後的工作階段不必再載入本檔，開場輸出也自動縮成三行。
  後續若環境、疑義表或圖譜再有變動，`status` 會重新轉 `2`，屆時才需要回到本檔的對應步驟

## 常見錯誤

- **一次倒 14 則疑義給使用者**——他會直接放棄。一次一則或分小批。
- **幫使用者勾裁示**——即使條文原文看起來很明確也不行。這是最高原則的紅線。
- **對只想查法規的使用者推銷 graphify 安裝**——查詢本來就不用裝，講反了會讓他以為系統壞了。
- **未經同意就跑 `setup.sh`**——那會動到他自己的電腦環境。
- **硬貼 `python3` 或斜線指令**——先看 `status` 回報的 `interpreter`；斜線指令只有 Claude Code 有。
- **把 ✅ 的步驟也逐項朗誦**——使用者只需要知道還有什麼要做。
- **跳過第五步**——操作簡介是整條流程的目的，不是可選的收尾。
- **在導引過程中做法規判斷**——本流程只診斷狀態，任何應設／免設判斷都要走
  `/code-requirements`（或跟 AI 說「幫我算這個案件的設備需求」）與 `fire_code_calc.py`。

# Fire Review — 審圖行為契約

消防審圖輔助系統：DXF 圖面＋審查文件 → 算應設設備 → 列缺失 → SVG 標註。**輔助，不取代。**
本檔是唯一正本（任何 AI 工具適用），只放「載入 skill 之前就必須生效」的內容。

## 開場檢查

第一件事跑 `python3 tools/onboarding.py status`：結束碼 `0` 直接開始審圖、
**不要讀 `skills/onboarding.md`**；`2` 才讀該檔依其流程引導（改動系統的動作先取得同意）。
Claude Code 由 SessionStart hook 自動執行。規則差異未裁示前照常審圖，但受影響規則的
輸出必須附「本參數尚未逐條確認」警語。

## 五條底線

1. 禁止心算、禁止憑記憶引法規數值——一律 `python3 tools/fire_code_calc.py`，輸出嵌入報告
2. `case.json` 是正典——圖面只是證據，不得跳過人工確認直接推算
3. 不確定就標「需人工判讀」——嚴禁以推測、預設值或未提供的圖說填充
4. `input/` 只讀，產出寫 `output/`；報告用繁體中文與台灣消防法規用語
5. 僅供審圖輔助，最終判斷歸屬專業消防人員

## 路由（`skills/` 下的檔名）

審圖主線：`plan-intake` → `mixed-use-review`（§12 定案）→ `code-requirements`（含 §13）
→ `gap-analysis`（三項交付物）；用途與樓層屬性判定見 `place-use-classification`，
大型案件分工見 `review-team`。兩階段 Excel 交付：`first-stage-review` → `stage-two-review`。
改規則參數走 `red-green` ＋ `regulation-intake`，訓練素材與實務見解走 `training-mode`／`practice-note`。
查法規先 `tools/regulation_graph.py neighbors --article §X` 定位，再 `regulation_index.py lookup` 只載入那幾條。
目錄結構、完整命令與設計背景見 `README.md`、`skills/README.md`、`CONTRIBUTING.md`；工具用法一律 `--help`。

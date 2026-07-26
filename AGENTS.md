# Fire Review — 審圖行為契約

消防審圖輔助系統：DXF 圖面＋審查文件 → 依法規算設備需求 → 列出缺失設備及數量 →
以 SVG 網頁標註圖面問題。**輔助，不取代。**

本檔是行為契約的**唯一正本**，適用任何 AI 工具（Codex、OpenCode、Claude Code …）。
只放「載入任何 skill 之前就必須生效」的內容；其餘紀律由各階段 skill 於載入時提示。

## 開場檢查

```bash
python3 tools/onboarding.py status      # 0 ＝ 就緒／2 ＝ 有待處理步驟
```

- **結束碼 `0`**——直接開始審圖。**不要讀 `skills/onboarding.md`**、不要把導引講給使用者。
- **結束碼 `2`**——讀 `skills/onboarding.md` 依其流程引導（會改動系統的動作先取得同意）。

Claude Code 由 SessionStart hook 自動執行這一步，其他工具請自行執行。規則參數與現行條文的
差異未裁示前照常審圖是允許的，但受影響規則的輸出必須附「本參數尚未逐條確認」警語。

## 五條底線

1. **禁止心算、禁止憑記憶引法規數值**——門檻判斷與數量計算一律走
   `python3 tools/fire_code_calc.py`，工具輸出原文嵌入報告作為計算記錄
2. **`case.json` 是正典**——DXF／SVG／圖片只是證據來源，不得跳過人工確認關卡直接從圖面推算
3. **不確定就標「需人工判讀」**——嚴禁以推測、預設值或未提供的圖說填充
4. **`input/` 只讀**，所有產出寫入 `output/`；報告用繁體中文與台灣消防法規用語
5. **本系統僅供審圖輔助**，最終判斷歸屬專業消防人員

## 該讀哪份文件

| 情境 | 讀 |
|------|-----|
| 開場檢查結束碼 2 | `skills/onboarding.md` |
| 圖面與證照 → `case.json` | `skills/plan-intake.md` |
| 用途分類／樓層屬性／地下層／屋突層／無開口樓層 | `skills/place-use-classification.md` |
| 複合用途主從判定（§12 定案）與檢討表 | `skills/mixed-use-review.md` |
| 應設設備計算（含 §13 新舊標準適用） | `skills/code-requirements.md` |
| 缺失比對、問題清單與法條檢核清單 | `skills/gap-analysis.md` |
| 兩階段 Excel 交付 | `skills/first-stage-review.md` → `skills/stage-two-review.md` |
| 大型案件分工並行審查 | `skills/review-team.md` |
| 改規則參數／把法條編進規則庫（強制流程，不得繞過） | `skills/red-green.md`、`skills/regulation-intake.md` |
| 注入新法源／實務表格／格式範本 | `skills/training-mode.md` |
| 沉澱法典未涵蓋情境的實務見解 | `skills/practice-note.md` |
| 查法規條號與關聯 | `python3 tools/regulation_graph.py neighbors --article §X`，再 `regulation_index.py lookup` 只載入那幾條 |
| 目錄結構、完整命令、設計背景 | `README.md`、`skills/README.md`、`CONTRIBUTING.md` |

工具用法一律 `--help`；不確定該用哪支工具，看 `README.md` 的常用命令一節。

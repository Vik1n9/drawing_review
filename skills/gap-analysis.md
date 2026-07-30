# 缺失比對分析（產出三項交付物）

對 $ARGUMENTS（案件名）執行「應設 vs 既有」比對，產出三項固定交付物到 `output/`：

1. **圖面審查 HTML**——DXF 轉 SVG，於向量圖面上標出有問題的部分並提供缺失導覽
2. **問題清單**——缺失四級分類，詳列違反哪些法條
3. **法條檢核清單 HTML**——標準表格格式，逐項打勾

## 前置檢查

1. `output/case.json` 已定稿（人工確認完成）
2. 應設設備清單（`{案件名}-requirements.md`）已產出；若無，先執行 `/code-requirements`
3. `run-tests --strict` 全綠（先紅再綠關卡，紅則停止）
4. `python3 tools/training_intake.py status` ——結束碼 `2` ＝ 法規圖譜未跟上規則庫**或實務註解未併入圖譜**，先補齊再續行
5. `python3 tools/fire_code_calc.py check-gap --case output/case.json` ——「需人工判讀」項若已有實務註解涵蓋，於問題清單引用註解 ID 與所補充的法條；確為法典未涵蓋且使用者當場給出判讀者，走 `/practice-note` 沉澱下來

## 執行流程

### 第一步：逐層逐項比對

對每一樓層、每一設備類別，比對三個維度：

| 維度 | 比對內容 | 工具 |
|------|---------|------|
| **有無** | 應設而圖面完全未見 | 直接比對 |
| **數量** | 圖面數量 < 應設需求數量 | `python3 tools/fire_code_calc.py calc --expr '{應設} - {既有}'` |
| **配置** | 數量夠但配置疑似不符（步行距離、水平距離、涵蓋範圍） | 標「配置疑義」，列出需圖面逐點檢核的法定距離 |

### 第二步：缺失分級（固定四級）

| 等級 | 定義 | 範例 |
|------|------|------|
| 🔴 **重大缺失** | 法定應設之設備類別完全未設 | 應設火警自動警報設備而圖面無任何探測器 |
| 🟠 **一般缺失** | 設備已設但數量不足或規格不符 | 探測器應設 6 只、圖面僅 4 只 |
| 🟡 **配置疑義** | 數量達標但配置可能不符法定距離，需圖面逐點量測 | 滅火器步行距離是否 ≤20m 需依動線量測 |
| ⚪ **需人工判讀** | 依現有資料無法判定 | 排煙區劃、無開口樓層認定 |

另設 🔵 **建議事項**：無強制法源但實務上建議改善的項目，必須明確標注「無強制法源」。

### 第三步：輸出缺失清單

三項交付物的標頭一律注明**法規版本**（`rules/equipment_rules.json` 的 `regulation_version`）、
`case.json` 確認日期，以及本次援引規則中 `verified: false` 的比例——審查者要能看出結論
是依哪一版法規、哪些參數尚未逐條確認做成的。

固定格式：

```
## 缺失清單
（標頭：法規版本 ○○○｜case.json 確認日期 ○○○｜未核定參數比例 ○○）

### 🔴 重大缺失（N 項）

| # | 樓層 | 設備 | 法條 | 應設 | 圖面現況 | 缺口 | 說明 |
|---|------|------|------|------|---------|------|------|
| 1 | B1 | 火警自動警報 | §19 | 偵煙式 4 只 | 未見 | -4 | 地下層面積達門檻 |

### 🟠 一般缺失（N 項）
...（同格式）

### 🟡 配置疑義（N 項）
| # | 樓層 | 設備 | 法定距離 | 檢核方式 |
...

### ⚪ 需人工判讀（N 項）
| # | 項目 | 缺什麼資料 | 建議補件 |
...
```

### 第四步：反向自檢（防漏判）

比對完成後強制自問並在報告中記錄：

1. **「這張圖最可能騙過 AI 的地方是什麼？」**——夾層未計入面積？複合用途只算了主用途？隔間變更導致探測區域劃分改變？
2. **既有設備數是否可信？**——圖例辨識信心度低的樓層，其「一般缺失」判定要加注「既有數量以圖面辨識為準，建議人工複點」
3. **免設判定複查**——所有「免設」結論重新過一遍門檻條件，確認沒有因欄位缺漏而誤判免設

### 第五步：抽檢准出（關卡）

1. `python3 tools/fire_code_calc.py run-tests --strict` 必須全綠（先紅再綠）
2. 隨機抽取 15%（至少 3 項）的檢核項，用 `fire_code_calc.py` 重算一次，比對結果一致才准出
3. 逐項檢查缺失清單的法條欄位：每項必須有條號，且條號存在於 `rules/equipment_rules.json` 的 `legal_basis` 中
4. 任一項不通過 → 打回修正後重審

### 第六步：產出三項交付物

全部寫入 `output/`：

**交付物 1：圖面審查 HTML（DXF 轉 SVG＋缺失導覽）**

1. 依缺失清單、case.json 的 `source_drawings` 與 `layout_index`，產出 `annotations.json`：頂層含 `case_name`、`output_html`、`source_drawings`；每筆標註含 `issue_id`（對應問題清單編號）、`drawing_id`、`bbox`（DXF model-space 座標）、`label`（簡短解釋）、`note`（完整說明＋法條）、`severity`、`position_confidence`
2. 位置只能來自 `layout_index` 或 DXF/審查文件明確標注；推定位置一律標 `position_confidence: low`
3. 執行：`python3 tools/dxf_svg_review.py --annotations {輸出目錄}/annotations.json`（**零安裝即可執行**——文字 DXF 由 `tools/dxf_parse.py` 以標準庫解析；只有二進位 DXF 才需要 `ezdxf`，屆時工具會直接指引改存 ASCII DXF）
3-1. 圖面來源若是 **DWG**，先跑 `python3 tools/dwg_guide.py check --path input/{案件名}/` 取得另存 DXF 的操作步驟；轉檔而來的圖面，`case.json` 對應欄位一律標 `source: derived` 並於報告註明「幾何來自格式轉換，圖層與符號已人工複核」
4. 產出的 `{案件名}-圖面審查.html` 必須顯示 DXF 轉成的 SVG、缺失清單導覽、點選定位與高亮；若有 `position_confidence: low`，頁面須顯示「位置僅供參考，以問題清單文字說明為準」
5. 消防設備符號是圖塊（`INSERT`），SVG 上以插入點標記呈現、幾何不展開——足以定位缺失，但不會畫出符號本身；報告不得據此描述符號外觀
6. 若警告區出現「實際圖元範圍比圖面宣告範圍大 N 倍」，代表圖框外有殘留圖元、整張圖會縮得很小。**不得自行裁切**——圖框外的東西有可能正是缺失本身；請使用頁面的縮放控制，並在報告標「需人工判讀」

**交付物 2：問題清單（`{案件名}-問題清單.md`）**

依第三步格式輸出，每項缺失**詳細說明違反哪些法條**（條號＋應設要求＋圖面現況＋缺口），附 AI 審圖局限性聲明與計算記錄附錄。

**交付物 3：法條檢核清單 HTML（§14~§31 逐條窮舉、逐項打勾）**

1. 先以工具產生 §14~§31 **逐條窮舉**的 `check_results.json` 骨架（窮舉性由工具保證，每條至少一列；規則未入庫的條號自動列「⚪需人工判讀（規則未入庫）」並帶條文原文 snippet）：

   ```bash
   python3 tools/article_checklist.py --case {輸出目錄}/case.json
   ```

2. 依本 skill 第一~四步的比對結果**更新**各已入庫項的 `status`（pass/fail/manual/na）與 `finding`（數量缺口、配置疑義說明）——只可更新既有項目內容，**不得刪除任何條號列**
3. 執行：`python3 tools/checklist_html.py --results {輸出目錄}/check_results.json`
4. 產出的 HTML 維持標準表格格式，逐項打勾（☑／☒／⚪／—），條號深連結到 `rules/regulation-checklist.html` 的條文錨點供對照原文；摘要列顯示「規則未入庫 N 條」

**可選交付物：法條檢核 Excel 與審查摘要報告**

完成上述三項交付物後，可額外產出：

```bash
# 法條檢核清單 Excel（需 openpyxl）
python3 tools/review_checklist_xlsx.py --results output/check_results.json

# 審查摘要報告 HTML（列印友善，可存 PDF；零安裝）
python3 tools/review_summary_pdf.py --case output/case.json --results output/check_results.json \
    --annotations output/annotations.json  # 可選，加入缺失摘要
```

## 重要注意事項

1. **缺口數字必須工具計算**，禁止心算
2. **配置疑義不升級也不降級**——AI 沒有能力從圖面精確量測距離時，就停在「疑義」，不判定合格或不合格
3. **報告必含「AI 審圖局限性聲明」**——列明本次分析中信心度低的環節
4. 遵守 `AGENTS.md` 五條底線

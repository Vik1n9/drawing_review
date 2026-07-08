# Fire Review — 審圖行為契約

## 專案定位

消防審圖輔助 Agent 系統：平面圖 PDF 輸入 → 依法規計算設備需求 → 列出缺失設備及數量，輔助專業消防人員審圖。**輔助，不取代。**

## 審圖最高原則（最高優先級，所有 skill 執行時必須遵守）

1. **法條可追溯**——每一項「應設／免設／缺失」結論必須附法規條號；引用不到條號的結論一律降級為「建議事項」並標明無法源依據
2. **禁止心算、禁止憑記憶引法規數值**——所有門檻判斷與數量計算必須透過 `python3 tools/fire_code_calc.py`，工具輸出直接嵌入報告作為計算記錄
3. **先紅再綠（防幻覺核心）**——規則庫的每個參數必須先有測試（expected 從法條 PDF 原文逐字抄錄、附頁碼與 quote），測試先紅、編碼後轉綠才可使用；`run-tests --strict` 不通過的規則庫不得交付
4. **正典資料是 case.json**——所有計算以人工確認後的 `case.json` 為準；圖片只是證據來源，不得跳過確認關卡直接從圖片推算
5. **需人工判讀原則（安全底線）**——圖面判讀不確定、需大樣圖／現場才能確認的項目（防火區劃、排煙開口、夾層面積等），一律標註「需人工判讀」，嚴禁用推測填充
6. **未核定規則必附警語**——`rules/*.json` 中 `verified: false` 的規則參數，輸出時必須附「本參數未經消防專業人員核定，以現行法規為準」
7. **法規版本注記**——報告標頭必須注明所依據的法規版本（`rules` 檔案的 `regulation_version` 欄位）
8. **呈現正反兩面**——判定「免設」時同樣列出計算過程與條文依據，讓審查者可以覆核，不是只列缺失

## 目錄結構（統一輸入／統一輸出）

```
drawing_review/
├── input/                       — 統一輸入資料夾（只讀不改）
│   ├── {案件名}/                — 平面圖 PDF 等待審資料
│   └── 法規/                    — 核對用法條清單 PDF
├── output/                      — 統一輸出資料夾
│   └── {案件名}-{YYYYMMDD}/     — 每次審查建立新目錄分類
│       ├── case.json                       — 圖說底稿（正典資料）
│       ├── annotations.json                — 紅圈標註定義
│       ├── check_results.json              — 檢核結果（供 HTML 產生）
│       ├── {案件名}-標註圖.pdf              — 交付物1：原圖紅圈標註＋簡短解釋
│       ├── {案件名}-問題清單.md             — 交付物2：缺失清單（詳列違反法條）
│       └── {案件名}-法條檢核清單.html       — 交付物3：打勾檢核表（標準表格格式）
├── rules/                       — 結構化法規規則庫
│   ├── equipment_rules.json     — 規則（每條附條號、verified 旗標）
│   ├── rule_tests.json          — 先紅再綠測試案例（expected 抄錄自法條 PDF）
│   └── regulation-checklist.html — 法條清單 HTML（由法條 PDF 轉換，格式不變，逐條錨點）
├── skills/                      — 審圖 skill 定義
└── tools/                       — 確定性工具
```

## 三項固定交付物（每案件必產出）

| # | 交付物 | 產生方式 |
|---|--------|---------|
| 1 | **標註圖 PDF** | `/gap-analysis` 產出 `annotations.json`（缺失位置＋簡短解釋＋嚴重度），`pdf_annotate.py` 在原圖上畫紅圈輸出 |
| 2 | **問題清單** | 缺失四級分類（重大／一般／配置疑義／需人工判讀），每項詳列違反法條、應設要求、圖面現況、缺口 |
| 3 | **法條檢核清單 HTML** | `checklist_html.py` 依 `check_results.json` 產出標準表格，逐項打勾（☑符合／☒不符合／⚪需人工判讀／—不適用），條號深連結到 `regulation-checklist.html` 錨點 |

## 報告語言與風格

- 報告使用**繁體中文**（台灣法規用語）
- 缺失分級固定四級：`重大缺失`（法定應設而未設）／`一般缺失`（數量不足或配置不符）／`配置疑義`（需圖面逐點量測）／`需人工判讀`；另有 `建議事項`（無強制法源，必須標明）
- 面積、距離、數量等數字必須標注來源（圖面標注／人工輸入／工具計算）

## 常用命令

```bash
# 先紅再綠：規則測試（規則庫交付前必須全綠）
python3 tools/fire_code_calc.py run-tests --strict

# 引擎與規則庫自檢（修改 rules/*.json 後必跑）
python3 tools/fire_code_calc.py self-test

# 門檻判斷：逐層逐設備 應設/免設/需人工判讀
python3 tools/fire_code_calc.py check-threshold --case output/{案件名}-{日期}/case.json

# 數量計算
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40
python3 tools/fire_code_calc.py calc --expr '450 / 100'

# 交付物產生
python3 tools/pdf_annotate.py --annotations output/{案件名}-{日期}/annotations.json   # 需 pip install pymupdf
python3 tools/checklist_html.py --results output/{案件名}-{日期}/check_results.json
```

## 注意事項

- 本專案輸出僅供審圖輔助，最終判斷歸屬專業消防人員
- `input/` 只讀不改；所有產出寫入 `output/{案件名}-{YYYYMMDD}/`
- 修改 `rules/*.json` 後必須重跑 `self-test` 與 `run-tests --strict`
- 標註圖的圈選位置為 AI 推定時（`position_confidence: low`），以問題清單文字說明為準

# Fire Review — 消防審圖輔助 Agent 系統

消防審圖輔助系統：DXF 平面圖 + 審查文件 → 依《各類場所消防安全設備設置標準》計算設備需求 → 列出缺失 → SVG 圖面標註。**輔助專業消防人員審圖，不取代專業判斷。**

## 審圖最高原則

1. **法條可追溯**：每項結論必須附法規條號；無條號降級為「建議事項」並標明無法源依據
2. **禁止心算**：所有門檻判斷與數量計算必須透過 `tools/fire_code_calc.py`，工具輸出嵌入報告
3. **先紅再綠**：規則參數先有測試（expected 逐字抄錄法條、附頁碼與 quote）→ `run-tests --verify-red` → 編碼 → `run-tests --strict` 轉綠。見 `skills/red-green.md`
4. **正典資料是 `case.json`**：所有計算以人工確認後的 `case.json` 為準；DXF/SVG/圖片只是證據來源
5. **需人工判讀原則**：圖面判讀不確定項目一律標註「需人工判讀」，嚴禁推測填充
6. **未核定規則必附警語**：`verified: false` 的規則參數輸出時必須附警語
7. **法規版本注記**：報告標頭注明 `regulation_version`
8. **呈現正反兩面**：判定「免設」時同樣列出計算過程與條文依據

## 目錄結構

```
drawing_review/
├── input/                       — 統一輸入（只讀不改）
│   └── {案件名}/                — 平面圖.dxf + 平面圖.pdf + 審查文件
├── output/                      — 統一輸出
│   └── {案件名}-{YYYYMMDD}/     — case.json / annotations.json / check_results.json / 交付物
├── rules/                       — 結構化法規規則庫
│   ├── core/                    — 法規全文正典（單一 md + _assets/ 附表圖檔）
│   ├── equipment_rules.json     — 設備規則（附條號、verified 旗標）
│   ├── mixed_use_rules.json     — 主從用途對照表
│   ├── rule_tests.json          — 先紅再綠測試案例
│   ├── article18_equipment_options.json — §18 各款可選設備對照
│   ├── review_corrections.md    — 累積確認的通案修正條目
│   ├── stage_two_judgment_rules.md — §14~31 判斷差異（不轉抄法條數值）
│   ├── regulation_index.json    — 輕量條文索引
│   ├── regulation_articles/     — 逐條文 JSON（審查時按需載入）
│   └── checklists/              — 法條判斷用 Excel 表
├── governance/                  — 規則核定責任追溯鏈
├── skills/                      — 審圖 workflow 文件
├── tools/                       — 確定性工具（Python）
├── tests/                       — Python 單元測試
├── training/                    — 訓練教材與圖譜（inbox/ + registry.json）
├── practice_notes/              — 實務見解筆記（active/ + staging/ + index.json）
└── docs/                        — 使用手冊、架構說明、AI 作業流程、路線圖
```

## 四項固定交付物

| # | 交付物 | 產生方式 |
|---|--------|---------|
| 1 | 圖面審查 HTML | `skills/gap-analysis.md` → `annotations.json` → `tools/dxf_svg_review.py` |
| 2 | 問題清單 MD | 缺失四級分類（重大缺失／一般缺失／配置疑義／需人工判讀） |
| 3 | 法條檢核清單 HTML | `tools/article_checklist.py` → `check_results.json` → `tools/checklist_html.py` |
| 4 | 複合用途及樓層屬性檢討 HTML | `tools/mixed_use_report.py` 依 case.json 產出 |

## 兩階段審查流程

| 階段 | 步驟 | 產物 |
|------|------|------|
| **第一階段** | 收件萃取 → §12 分類（人工確認）→ 事實關卡 → 交付物 | case.json + HTML + Excel |
| **第二階段** | §13 適用判斷 → §14~31 逐條窮舉 → 事實關卡 → 人工定案 → 交付物 | check_results.json + HTML + Excel |

事實關卡：`tools/case_facts_gate.py --stage first|second`

## 常用命令

```bash
# 載入倉庫後第一件事
python3 tools/onboarding.py status

# 法規圖譜定位（先定位再載入，省 context）
python3 tools/regulation_graph.py neighbors --article §24
python3 tools/regulation_graph.py articles --equipment 排煙設備
python3 tools/regulation_index.py lookup --article '§14'
python3 tools/regulation_index.py lookup --equipment '滅火器'

# 規則庫自檢與先紅再綠測試（修改 rules/*.json 後必跑）
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}

# 門檻判斷與計算
python3 tools/fire_code_calc.py check-threshold --case output/{案件名}-{日期}/case.json
python3 tools/fire_code_calc.py check-applicability --case output/{案件名}-{日期}/case.json
python3 tools/fire_code_calc.py classify-mixed-use --case output/{案件名}-{日期}/case.json
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2

# 交付物產生
python3 tools/dxf_svg_review.py --annotations output/{案件名}-{日期}/annotations.json
python3 tools/article_checklist.py --case output/{案件名}-{日期}/case.json
python3 tools/checklist_html.py --results output/{案件名}-{日期}/check_results.json
python3 tools/mixed_use_report.py --case output/{案件名}-{日期}/case.json
python3 tools/stage_report_xlsx.py --case output/{案件名}-{日期}/case.json --stage first|stage-two

# 規則核定
python3 tools/verification_sheet.py export
python3 tools/verification_sheet.py apply --results governance/核定紀錄/results-{日期}.json

# 更新安全檢查（更新倉庫前必跑）
python3 tools/update_guard.py check

# 測試
python3 -m unittest discover tests
```

## 開發規範

- **語言**：報告與交付物使用繁體中文（台灣消防法規用語）
- **缺失分級**：`重大缺失`／`一般缺失`／`配置疑義`／`需人工判讀`；`建議事項` 僅用於無強制法源
- **工具層**：維持 stdlib-only；例外為 `ezdxf`（DXF）與 `openpyxl`（Excel）
- **變更規範**：所有變更走分支 + PR，不直接 push main
- **CI**：`self-test` 與 `run-tests --strict` 紅燈不得合併
- **commit message**：用中文，說清楚改了什麼、法源依據
- **`input/` 只讀**；法規全文固定於 `rules/core/`；案件產出寫入 `output/{案件名}-{YYYYMMDD}/`
- **修改 `rules/*.json` 後**必須重跑 `self-test` 與 `run-tests --strict`
- **查法規依據**：先用 `regulation_graph.py` 定位，再用 `regulation_index.py lookup` 按需載入；禁止一次載入全部法規
- **法規全文正典**：`rules/core/1各類場所消防安全設備設置標準.md`（單一 md，§1~§239）；`regulation_index.py build` glob `rules/core/*.md`，維持單一檔案避免重複

## 角色分工

| 角色 | 職責 | 工作介面 |
|------|------|---------|
| 架構管理者 | 架構開發、規則編碼（先紅再綠）、核定表操作、git/PR/CI | repo 全部 |
| 消防專業人員 | 法條審查（核定規則參數）、法規解釋 | 核定表 HTML／紙本 |

## 免責聲明

本專案輸出僅供審圖輔助，最終判斷歸屬專業消防人員。`verified: false` 的法規參數不得作為正式審查依據。

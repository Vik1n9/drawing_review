# Drawing Review — 消防審圖輔助 Agent 系統

本專案是消防審圖輔助系統：案件輸入以 **待審 `平面圖.dxf`** 為主，搭配輔助對照用 `平面圖.pdf` 與相關審查文件；AI 依人工確認後的 `case.json` 與固定法規資料夾中的結構化規則庫進行工具計算，最後輸出缺失清單、法條檢核表，以及可互動導覽的 SVG 圖面標註網頁。

> **定位：輔助專業消防人員審圖，不取代專業判斷。** 每一項「應設／免設／缺失」結論都必須可追溯到法規條文；凡圖面或資料不足以判定之處，一律標註「需人工判讀」。

---

## 一、目標與範圍

| 項目 | 內容 |
|------|------|
| 輸入 | `input/{案件名}/平面圖.dxf` 為審核主圖面，搭配同資料夾內的 `平面圖.pdf` 與相關審查文件；法規不放入案件輸入資料夾 |
| 正典資料 | 人工確認後的 `output/{案件名}-{YYYYMMDD}/case.json`；DXF 與 PDF/文件只作為證據來源 |
| 核心能力 1 | 依法條清單計算各類消防設備的應設需求（種類、數量、免設或需人工判讀） |
| 核心能力 2 | 比對圖面既有設備配置與應設需求，列出缺項、數量不足、配置疑義與需人工判讀項目 |
| 輸出 | `output/{案件名}-{YYYYMMDD}/` 下四項固定交付物：① 圖面審查 HTML（DXF 轉 SVG＋缺失導覽）② 問題清單 Markdown ③ 法條檢核清單 HTML（§14~§31 逐條窮舉）④ 複合用途及樓層屬性檢討 HTML |
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
/regulation-intake（首次建庫或法規換版；來源固定在 rules/法規/）
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
output/{案件名}-{日期}/case.json
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
output/{案件名}-{日期}/
├── {案件名}-圖面審查.html                  ① DXF→SVG 圖面標註＋缺失導覽
├── {案件名}-問題清單.md                    ② 缺失四級分類，詳列違反法條
├── {案件名}-法條檢核清單.html              ③ §14~§31 逐條窮舉打勾檢核表，條號連結法條原文
└── {案件名}-複合用途及樓層屬性檢討.html    ④ 主從用途／樓層屬性檢討表＋判定結論
```

大型或複雜案件可走 `/review-team`：滅火設備、警報設備、避難逃生設備、消防搶救必要設備並行審查，由 Team Lead 統整後仍產出同三項交付物。

---

## 三、目錄結構

```text
drawing_review/
├── input/
│   └── {案件名}/
│       ├── 平面圖.dxf                — 需要審核的主圖面（只讀不改）
│       ├── 平面圖.pdf                — 輔助對照用圖面 PDF（只讀不改）
│       └── 相關審查文件               — 申請書、審查表、說明書等案件文件
├── output/
│   └── {案件名}-{YYYYMMDD}/
│       ├── case.json                 — 圖說底稿（正典資料）
│       ├── annotations.json          — SVG 標註定義
│       ├── check_results.json        — 檢核結果（供 HTML 產生）
│       ├── {案件名}-圖面審查.html
│       ├── {案件名}-問題清單.md
│       └── {案件名}-法條檢核清單.html
├── rules/                            — 固定法規資料夾與結構化法規規則庫
│   ├── equipment_rules.json
│   ├── rule_tests.json
│   ├── 法規/                         — 法規 PDF/Markdown 原文（非每案輸入）
│   ├── regulation_index.json
│   └── regulation_articles/
├── governance/                       — 規則核定責任追溯鏈
├── skills/                           — 審圖 workflow 文件
├── tests/                            — Python 單元測試
└── tools/                            — 確定性工具
```

`input/` 一律視為只讀；每案輸入資料夾只放案件圖面與審查文件，不放法規檔。法規固定維護於 `rules/法規/`，所有案件共用同一套經索引與測試的規則庫。所有案件產出寫入新的 `output/{案件名}-{YYYYMMDD}/` 目錄。

---

## 四、核心設計決策

### 1. `case.json` 是正典，不是 DXF

DXF 提供座標、圖層、符號與標註位置，但消防設備應設需求與缺失結論仍以人工確認後的 `case.json` 為準。任何從圖面萃取的面積、用途、樓層、既有設備數量與低信心欄位，都必須經人工確認後才進入計算。

### 2. 計算交給工具，不交給 LLM

「是否應設」「應設多少」「缺口多少」必須透過 `tools/fire_code_calc.py` 或其他確定性工具計算。LLM 負責萃取、整理、分類與撰寫，不得心算或憑記憶引用法規數值。

### 3. SVG 是標註呈現，不是最終判定來源

`tools/dxf_svg_review.py` 使用 `ezdxf` 讀取 DXF，將常見實體轉成 SVG，並把 `annotations.json` 的缺失位置畫在圖上。圖面不足以判定配置時，輸出「配置疑義」或「需人工判讀」，不得用視覺推測取代專業審圖。

### 4. 法規參數先紅再綠

規則庫的每個門檻、係數與數量參數都必須先有測試；測試 expected 需逐字抄錄法條來源並附頁碼與 quote。`run-tests --verify-red` 確認紅得正確後，才可編碼最小規則讓 `run-tests --strict` 轉綠。

---

## 五、工具層

| 工具 | 用途 | 依賴 |
|------|------|------|
| `tools/fire_code_calc.py` | 法規門檻、數量計算、§13 適用判斷、主從用途比對、規則測試、自檢 | stdlib |
| `tools/regulation_index.py` | 法規 Markdown 轉逐條索引與按需查詢 | stdlib |
| `tools/article_checklist.py` | 依 case.json 產出 §14~§31 逐條窮舉 `check_results.json` | stdlib |
| `tools/mixed_use_report.py` | case.json 轉複合用途及樓層屬性檢討 HTML（交付物4） | stdlib |
| `tools/checklist_html.py` | `check_results.json` 轉法條檢核清單 HTML | stdlib |
| `tools/dxf_svg_review.py` | `annotations.json` + DXF 轉互動式 SVG 圖面審查 HTML | `ezdxf` |
| `tools/pdf_annotate.py` | legacy：舊版 PDF 紅圈標註輸出 | `pymupdf` |
| `tools/verification_sheet.py` | 規則核定表匯出與回填 | stdlib |

安裝 Python 相依套件：

```bash
python3 -m pip install -r requirements.txt
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
  "output_html": "output/示範案件-20260708/示範案件-圖面審查.html",
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
# 安裝相依套件
python3 -m pip install -r requirements.txt

# 法規索引
python3 tools/regulation_index.py build
python3 tools/regulation_index.py lookup --article '§19'
python3 tools/regulation_index.py lookup --equipment '滅火器'

# 規則庫自檢與先紅再綠測試
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}

# 門檻判斷與數量計算
python3 tools/fire_code_calc.py check-threshold --case output/{案件名}-{日期}/case.json
python3 tools/fire_code_calc.py check-applicability --case output/{案件名}-{日期}/case.json   # §13 新舊標準
python3 tools/fire_code_calc.py classify-mixed-use --case output/{案件名}-{日期}/case.json    # 主從用途候選
python3 tools/fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
python3 tools/fire_code_calc.py sprinkler --area 450 --radius 2.3
python3 tools/fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
python3 tools/fire_code_calc.py hydrant-coverage --area 450 --radius 25
python3 tools/fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40

# 交付物產生
python3 tools/dxf_svg_review.py --annotations output/{案件名}-{日期}/annotations.json
python3 tools/article_checklist.py --case output/{案件名}-{日期}/case.json     # §14~31 逐條窮舉
python3 tools/checklist_html.py --results output/{案件名}-{日期}/check_results.json
python3 tools/mixed_use_report.py --case output/{案件名}-{日期}/case.json      # 交付物4

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
| Phase 0 法規編碼 | 設置標準逐條結構化為 rules JSON，消防專業人員逐條核定 | 示例子集已建，仍為 `verified: false` |
| Phase 1 規則引擎 MVP | 人工確認 `case.json` → 應設需求計算 | 已具備 |
| Phase 2 DXF/SVG 工具層 | DXF 轉 SVG 圖面審查 HTML，缺失清單導覽與高亮定位 | 已導入工具骨架 |
| Phase 3 圖面萃取 | 從 DXF 圖層、符號與審查文件萃取 `case.json`，並經人工確認 | 流程定義中 |
| Phase 4 配置幾何檢核 | 將步行距離、水平距離、涵蓋半徑從疑義升級為座標幾何檢核 | 待建 |
| Phase 5 多 Agent 編排 | 四類設備審查員並行，Team Lead 彙整 | skill 已建 |
| Phase 6 品管准出 | 抽檢重算、法條引用逐項可追溯性檢查、自動化 CI | 部分已建 |
| Phase 7 實戰迭代 | 實案回饋轉成規則、測試、工具檢查點 | 持續 |

---

## 十、待補事項備忘（後續跟進清單）

> 本節為待補文件與待辦事項的備忘錄，完成一項勾銷一項（`[ ]` → `[x]` 並注記日期）。

| # | 狀態 | 事項 | 觸發條件／後續動作 |
|---|------|------|-------------------|
| 1 | [ ] 待文件 | **《複合用途建築物判斷基準》本文**（從屬認定要件：管理權、使用形態、面積比例門檻等文字規定）尚未提供，目前僅有附表 | 文件放入 `rules/法規/` 後：先紅再綠補 `mixed_use_rules.json` 的 `subordinate-criteria`／`subordinate-thresholds` 規則，`classify-mixed-use` 量化判定由「需人工判讀」升級為工具計算 |
| 2 | [ ] 待文件 | 「14~31 條判斷用」勾選表**實務範例**尚未提供 | 取得後對齊 `checklist_html.py` 檢核表版面與欄位 |
| 3 | [ ] 待文件 | 實際案件的**使用執照、室內裝修申請書**樣本（可去識別化）尚未提供 | 取得後驗證 `plan-intake` 證照萃取欄位（`use_permit`／`interior_renovation`／`change_of_use`）設計是否齊備 |
| 4 | [ ] 待入庫 | **§16、§18、§20、§21、§22、§25、§26、§27、§29、§30 規則尚未入庫**——檢核表以「⚪需人工判讀（規則未入庫）」逐條呈現 | 逐條先紅再綠入 `equipment_rules.json`（條文原文已在 `rules/regulation_articles/`，可隨時進行） |
| 5 | [ ] 待核定 | **全部規則 `verified: false`**（equipment_rules 12 條＋mixed_use_rules 1 條，含 §13 與對照表 31 項）；對照表抄錄自掃描 PDF，若干疑字已標 `transcription_note`（如「更氣室」「百貨適場」「診療至」） | 走 governance 核定：`python3 tools/verification_sheet.py export` 匯出核定表 → 消防專業人員逐條核對原文（特別是 transcription_note 項）→ `apply` 回填 |
| 6 | [ ] 待實作 | 戊類複合用途之 §12-1 面積合計方式（以各目為單元合計）尚未進 `check-threshold` 引擎 | 判定為戊類的案件目前由 `/code-requirements` 報告注記、人工調整面積合計；後續先紅再綠入引擎 |

## 十一、免責聲明

本專案為審圖輔助工具研究，內建法規參數為開發示例。未經主管機關或消防專業人員核定前，不得作為正式審查依據；實際審查以現行法規條文、主管機關解釋與專業消防人員判斷為準。

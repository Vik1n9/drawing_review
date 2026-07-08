# Drawing Review — 消防審圖輔助 Agent 系統

> 參考 [ai-berkshire](https://github.com/xbtlin/ai-berkshire)「投研 Agent 作業系統」架構，移植到消防設備審圖領域。
>
> **定位：輔助專業消防人員審圖，不取代專業判斷。** 系統的每一項結論都必須可追溯到法規條文，凡視覺判讀不確定之處一律標註「需人工判讀」。

---

## 一、目標與範圍

| 項目 | 內容 |
|------|------|
| 輸入 | 統一輸入資料夾 `input/`：建築平面圖 **PDF** ＋ 核對用**法條清單 PDF**（有具體來源的條文彙編） |
| 核心能力 1 | 依法條清單計算各類消防設備的**應設需求**（種類＋數量） |
| 核心能力 2 | 比對圖面既有設備配置，列出**缺失清單**（缺項／數量不足／配置疑義） |
| 輸出 | 統一輸出資料夾 `output/{案件名}-{YYYYMMDD}/`，三項固定交付物：**① 原圖紅圈標註 PDF（附簡短解釋）② 問題清單（詳列違反法條）③ 法條檢核清單 HTML（標準表格＋逐項打勾）** |
| 防幻覺機制 | **先紅再綠**：規則庫每個參數先有測試（expected 逐字抄錄自法條 PDF、附頁碼與原文引用），測試先紅、編碼後轉綠才可使用 |
| 使用者 | 消防設備師（士）、消防審查人員、建築師事務所 |
| 適用法規 | 以使用者提供的法條清單 PDF 為準，架構支援法規版本管理 |

**免責界線**：本系統輸出為審圖輔助草稿，最終審查判斷與法律責任歸屬專業消防人員。所有內建法規參數在正式使用前必須經消防專業人員逐條核定（見 `rules/` 的 `verified` 欄位機制）。

**協作方式**：角色分工與變更規範見 [CONTRIBUTING.md](CONTRIBUTING.md)；消防專業人員的核定循環（不需操作 GitHub／AI，紙本簽名即可）見 [governance/README.md](governance/README.md)。

---

## 二、與 ai-berkshire 的架構對照

| 層 | ai-berkshire（投研） | drawing_review（消防審圖） |
|----|---------------------|------------------------|
| 方法論層 | 四大師投資框架 → checklist／評分／紅線 | 設置標準法規 → 結構化規則庫（`rules/*.json`，含條號） |
| Skill 層 | `skills/*.md` 工作流 prompt | `/plan-intake`、`/code-requirements`、`/gap-analysis`、`/review-team` |
| 編排層 | 4 大師視角並行 Agent + Team Lead | 4 類設備審查員並行 Agent + Team Lead（依設置標準四大設備分類） |
| 工具層 | `financial_rigor.py` 精確計算 | `fire_code_calc.py` 規則引擎＋數量計算（Decimal，禁止心算） |
| 資料治理層 | `financial-data.md` 雙源交叉驗證 | `regulation-data.md` 法規雙源驗證＋圖說萃取雙重確認 |
| 品管層 | `report_audit.py` 抽檢 15% 准出 | 檢核項抽檢重算＋法條引用逐項可追溯性檢查 |
| 記憶層 | `CLAUDE.md` 行為契約 | `CLAUDE.md`（審圖最高原則） |
| 產出層 | `reports/{公司名}/` | `output/{案件名}-{YYYYMMDD}/`（case.json 底稿＋三項交付物） |

## 三、與投研系統的四個關鍵差異（設計決策）

### 1. 正典資料是 case.json，不是圖片

投研的輸入（財報數字）LLM 讀取相對可靠；**平面圖視覺判讀是整條流水線最不可靠的環節**。因此：

- 圖片只是「證據來源」，所有下游計算一律以結構化的 `case.json`（圖說底稿）為準
- `/plan-intake` 產出 case.json 後有**強制人工確認關卡**：面積、用途、樓層數、防火構造等關鍵欄位逐項向審圖人員確認後才進入計算
- 每個從圖面萃取的欄位帶 `confidence`（high/medium/low）與 `source`（圖面標注／人工輸入／推算）

### 2. 判斷是硬規則，LLM 只做萃取、分類與敘述

投研的核心是模糊判斷（護城河、管理層），LLM 是主角；消防審圖的核心是**法定門檻與數量計算**，容錯為零。因此權重反轉：

- 「某用途某面積是否應設某設備」「應設多少」→ 全部進 Python 規則引擎（`fire_code_calc.py` + `rules/equipment_rules.json`），LLM 禁止心算、禁止憑記憶引用法規數值
- LLM 負責的是：圖面資訊萃取、用途分類建議（需人工確認）、缺失敘述與意見書撰寫、疑義點的說明

### 3. 留白原則從「加分項」變成「安全底線」

投研留白是誠實；審圖留白是安全。凡下列情況一律輸出「需人工判讀」而非推測：

- 圖面圖例不清、比例尺缺失、夾層／挑空是否計入面積
- 防火區劃、排煙區劃、開口有效面積等需要現場或大樣圖才能確認的項目
- 複合用途場所的用途歸類邊界案例

### 4. 先紅再綠：規則庫的防幻覺測試（TDD for 法規）

AI 最危險的失敗模式是**憑訓練記憶編造法規數值**（門檻面積、涵蓋半徑、每只探測面積），且編得極像真的。對策是把 TDD 的 RED–GREEN 紀律（改編自 [obra/superpowers](https://github.com/obra/superpowers) 的 test-driven-development skill，完整版見 `skills/red-green.md`）搬到法規編碼上：

```
（RED）        1. 先寫測試：expected 值對著法條清單 PDF「逐字抄錄」，必附頁碼 + 原文引用（quote）
（Verify RED） 2. run-tests --verify-red {測試ID}：看著測試失敗，且必須「紅得正確」——
                  已綠 = 測試無鑑別力（重寫）；INVALID = 測試壞掉（先修測試，不算合法的紅）
（GREEN）      3. 編碼最小參數到 rules/equipment_rules.json（只讓這個測試轉綠，不順手加別的）
（Verify GREEN）4. run-tests --strict 轉綠且沒弄破其他測試；紅了修參數、不修測試
               5. 消防專業人員核定後 verified: true
```

**鐵律**：參數先於測試被寫入規則庫 → 刪除該參數重來，不保留當參考（事後補的測試只是把幻覺抄寫第二遍）。紅→綠的順序保證「測試的期望值」與「規則的參數值」來自**兩次獨立的取數動作**——等同投研系統的雙源交叉驗證。無 quote 的測試一律判 INVALID。

---

## 四、系統分層架構

```
┌─ 法規知識層   rules/equipment_rules.json — 結構化條文（門檻、係數、條號、verified 旗標）
│               rules/rule_tests.json      — 先紅再綠測試（expected 抄錄自法條 PDF）
│               rules/regulation-checklist.html — 法條清單 HTML（格式不變、逐條錨點）
├─ Skill 層     skills/*.md — 審圖工作流（prompt-as-code，編號步驟＋關卡）
│   ├─ regulation-intake.md  法條清單 PDF → 規則庫 + HTML（先紅再綠）
│   ├─ plan-intake.md        平面圖 PDF → case.json 圖說底稿（含人工確認關卡）
│   ├─ code-requirements.md  依法規計算應設設備種類與數量
│   ├─ gap-analysis.md       應設 vs 圖面既有 → 三項交付物
│   ├─ review-team.md        四類設備審查員並行 + Team Lead 彙整
│   └─ regulation-data.md    法規資料治理規範（雙源驗證、版本管理）
├─ 工具層       tools/fire_code_calc.py — 規則引擎＋run-tests（stdlib、Decimal）
│               tools/checklist_html.py — 打勾檢核表 HTML 產生（stdlib）
│               tools/pdf_annotate.py   — 原圖紅圈標註（需 pymupdf）
├─ 記憶層       CLAUDE.md — 審圖行為契約（最高原則）
└─ 產出層       input/ 統一輸入 ─▶ output/{案件名}-{YYYYMMDD}/ 統一輸出（三交付物）
```

### 標準工作流（單案件）

```
input/法規/法條清單.pdf                    input/{案件名}/平面圖.pdf
   │                                          │
   ▼                                          ▼
/regulation-intake（一次性/換版時）        /plan-intake ── 圖說可讀性評級 A/B/C ── 逐層萃取
   │ 先紅再綠：測試(抄PDF)→紅→編碼→綠        │
   ▼                                          ▼
rules/equipment_rules.json           【關卡1：人工確認】關鍵欄位逐項確認
rules/regulation-checklist.html               │
（格式不變、逐條錨點）                        ▼
   │                              output/{案件名}-{日期}/case.json（定稿）
   │                                          │
   └──────────────┬───────────────────────────┘
                  ▼
   /code-requirements ── check-threshold + 各設備數量計算（每項附條號）
                  │
                  ▼
   /gap-analysis ── 應設 vs 既有比對
                  │
                  ▼
   【關卡2：准出】run-tests --strict 全綠 + 抽檢重算 + 條號可追溯
                  │
                  ▼
   output/{案件名}-{YYYYMMDD}/  三項交付物：
   ├── {案件名}-標註圖.pdf         ① 原圖紅圈＋簡短解釋（pdf_annotate.py）
   ├── {案件名}-問題清單.md        ② 缺失四級分類，詳列違反法條
   └── {案件名}-法條檢核清單.html  ③ 標準表格逐項打勾，條號深連結法條原文
```

大型／複雜案件改走 `/review-team`：四類設備審查員（滅火／警報／避難逃生／消防搶救必要設備）並行審查，Team Lead 彙整。

---

## 五、Skill 一覽

| Skill | 觸發 | 輸入 | 輸出 |
|-------|------|------|------|
| `/regulation-intake` | 法條清單換版／首次建庫 | `input/法規/法條清單.pdf` | 規則庫＋測試＋法條 HTML（先紅再綠） |
| `/plan-intake` | 新案件進場 | `input/{案件名}/平面圖.pdf` | `output/{案件名}-{日期}/case.json` |
| `/code-requirements` | case.json 定稿後 | case.json | 應設設備清單（含條號） |
| `/gap-analysis` | 應設清單完成後 | 應設清單＋圖面既有設備 | 三項交付物（標註圖／問題清單／檢核 HTML） |
| `/review-team` | 大型案件完整審查 | case.json | 三項交付物＋彙整意見 |
| `regulation-data` | 被其他 skill 引用 | — | 法規取數與驗證規範 |

---

## 六、從零建置路線圖

| 階段 | 內容 | 本骨架的完成度 |
|------|------|--------------|
| **Phase 0 法規編碼** | 設置標準逐條結構化為 rules JSON，消防技師逐條核定（`verified: true`） | 示例子集已建，全部標 `verified: false` |
| **Phase 1 單 Skill MVP** | 先跳過圖面辨識：人工輸入 case.json → 需求計算。驗證規則引擎正確性 | skills + 工具原型已建 |
| **Phase 2 工具層** | 規則引擎補全所有設備類別；配置類檢核（步行距離、涵蓋半徑）從估算升級為座標幾何計算 | 核心子命令已實作 |
| **Phase 3 圖面萃取** | 引入視覺模型讀圖＋人工確認關卡；累積圖例庫提升萃取準確率 | 流程與關卡已定義 |
| **Phase 4 多 Agent 編排** | `/review-team` 四類設備並行審查 | skill 已建 |
| **Phase 5 品管關卡** | 先紅再綠測試（`run-tests --strict`）＋抽檢重算＋條號可追溯性驗證 | run-tests 已實作；抽檢工具（仿 `report_audit.py`）待建 |
| **Phase 6 法規版本管理** | 修法監控、rules 版本欄位、舊案件用舊版規則重跑比對 | 欄位已預留 |
| **Phase 7 實戰迭代** | 與審查員實際案件回饋：每發現一個 AI 誤判模式，補一條規則或一個工具檢查點 | — |

**建置優先序建議**：八成力氣先花在 Phase 0 與 Phase 2（法規結構化＋規則引擎），這是系統的可信度來源；圖面辨識（Phase 3）反而放後面——先讓「人工輸入資料 → 正確計算需求」跑通並被審查員信任，再逐步自動化輸入端。

---

## 七、免責聲明

本專案為審圖輔助工具研究，內建法規參數為開發示例，未經主管機關或消防專業人員核定前不得作為審查依據。實際審查以現行法規條文及主管機關解釋為準。

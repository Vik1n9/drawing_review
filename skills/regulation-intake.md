# 法條清單結構化與 HTML 轉換（先紅再綠）

對 $ARGUMENTS（法條清單 PDF 路徑）執行法規結構化。這是規則庫的**唯一合法來源**：所有 `rules/equipment_rules.json` 的參數都必須經由本 skill 從法條清單 PDF 萃取，並通過「先紅再綠」測試後才能供 `/code-requirements` 使用。

## 輸入與輸出

| 項目 | 內容 |
|------|------|
| 輸入 | 法條清單 PDF（有具體來源的條文彙編，如設置標準條文＋審查基準） |
| 輸出 1 | `rules/equipment_rules.json` — 結構化規則（每條附 PDF 頁碼＋原文引用） |
| 輸出 2 | `rules/rule_tests.json` — 規則測試案例（先紅再綠的依據） |
| 輸出 3 | `rules/regulation-checklist.html` — 法條清單 HTML 版（**格式不變**，供審查意見書引用） |

## 執行流程

### 第一步：讀取法條清單 PDF

- 用 Read 工具逐頁讀取 PDF（每次最多 20 頁，分批處理）
- 記錄文件來源資訊：文件名稱、版本／修正日期、總頁數，寫入 rules JSON 的 `regulation_version` 與 `source_document`

### 第二步：轉換 HTML（格式不變）

產出 `rules/regulation-checklist.html`，轉換紀律：

1. **格式不變**：保留原文的章節層級、條號、項款目編號、表格結構（PDF 中的表格轉為 `<table>`，欄位一一對應）、附註位置。不增刪文字、不改寫、不摘要
2. **逐條錨點**：每一條加 `id` 錨點（如 `<section id="art-19">`），項款目加子錨點（`art-19-1-4`），供審查意見書的法條引用直接深連結
3. **來源標注**：每條末尾以小字標注來源 PDF 頁碼（`<span class="src">來源：p.12</span>`）
4. **自我核對**：轉換完成後，隨機抽 10% 條文，將 HTML 內文字與 PDF 原頁逐字比對，不一致即修正並擴大抽查到 20%

### 第三步：先紅再綠——規則編碼（防幻覺核心機制）

**完整紀律見 `skills/red-green.md`（改編自 obra/superpowers 的 TDD skill），含鐵律、紅旗清單與交付前檢查清單。** 對每一條要進規則庫的參數，嚴格依照順序執行，不得跳步：

```
（RED）       1. 先寫測試：在 rules/rule_tests.json 新增測試案例——
                 expected 值必須從 PDF 原文「抄錄」（不能推算），
                 並填入 source.page 與 source.quote（逐字原文引用）
                 ★ 沒有 quote 的測試引擎直接判 INVALID
（Verify RED）2. 看著測試失敗，且必須紅得正確：
                 python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}
                 ★ 已綠 = 測試無鑑別力（你測的是既有參數）→ 重寫測試；
                   若參數先於測試存在 → 刪除該參數重來（鐵律：不留參考）
                 ★ INVALID = 測試本身壞掉，不是合法的紅 → 先修測試
（GREEN）     3. 編碼最小參數：只寫入讓這個測試轉綠所需的參數，
                 附 legal_basis 條號；不順手加其他條文的參數
（Verify GREEN）4. 確認轉綠且沒弄破其他測試：
                 python3 tools/fire_code_calc.py run-tests --strict
                 ★ 紅了是參數錯 → 修參數，不是修測試
              5. 專業核定後將該規則 verified 改為 true（僅能經 verification_sheet.py apply）
```

**為什麼先紅再綠能防幻覺**：expected 值在規則編碼**之前**、直接對著 PDF 原文抄錄並留下頁碼與原文引用——AI 沒有機會「先編一個參數、再編一個會通過的測試」。紅→綠的順序保證測試與實作來自兩次獨立的取數動作，等同投研系統的雙源交叉驗證。而 Verify RED 關卡進一步保證：這個測試確實在測「這個參數」，而不是恰好永遠通過的空測試。

測試案例格式（`rules/rule_tests.json`）：

```json
{
  "id": "T-extinguisher-count-甲",
  "rule_id": "extinguisher-count",
  "type": "param-equals",
  "path": "params.effectiveness_area_per_unit.甲",
  "expected": 100,
  "source": {"pdf": "法條清單.pdf", "page": 12, "quote": "（原文逐字抄錄，含條號）"}
}
```

計算型測試（驗證引擎行為，同樣附法源）：

```json
{
  "id": "T-extinguisher-calc-450",
  "rule_id": "extinguisher-count",
  "type": "calc-extinguisher",
  "input": {"use_category": "甲", "floor_area": 450},
  "expected": {"effectiveness_value": 5},
  "source": {"pdf": "法條清單.pdf", "page": 12, "quote": "（原文）"}
}
```

### 第四步：覆蓋率與准出

```bash
# 全部測試必須綠，且每條規則至少有一個測試（--strict）
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/fire_code_calc.py self-test
```

- 任一測試紅 → 規則庫不得交付使用
- `--strict` 檢查每條規則的測試覆蓋，未覆蓋的規則列為紅
- 通過後輸出結構化摘要：規則數、測試數、verified 比例、HTML 條文數

### 第五步：修法更新流程

法條清單 PDF 換版時：
1. 重新執行本 skill，`regulation_version` 更新
2. 受影響規則的 `verified` 重置為 `false`，對應測試的 expected 依新版 PDF 重新抄錄（先改測試→紅→改規則→綠）
3. 舊版 rules 與 HTML 封存為 `-{版本日期}` 後綴

## 重要注意事項

1. **expected 值只能抄錄、不能推算**——測試的存在意義就是「PDF 原文的複寫」，推算出的 expected 等於讓 AI 自己驗自己
2. **HTML 是引用基準**——審查意見書中每個條號都連結到 HTML 錨點，審查者一鍵可核對原文
3. **quote 必須逐字**——run-tests 會檢查 quote 非空；人工核定時逐字比對 PDF
4. 遵守 `CLAUDE.md` 審圖最高原則與 `regulation-data.md` 治理規範

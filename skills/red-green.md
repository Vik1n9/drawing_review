# 先紅再綠：法規編碼紀律

規則庫（`rules/equipment_rules.json`）任何參數變更的**強制流程**。方法論改編自 [obra/superpowers](https://github.com/obra/superpowers) 的 test-driven-development skill——把 TDD 的 RED–GREEN–REFACTOR 紀律移植到法規編碼：「production code」是規則參數，「test」是法條 PDF 原文的抄錄。

## 鐵律

**沒有先紅的測試，就沒有規則參數。**

發現參數先於測試被寫入規則庫？**刪除該參數，重新開始。** 無一例外：

- 不要保留當「參考」再補測試——你會照著參數寫測試，那就是測試後補，證明不了任何事
- 不要「一邊補測試一邊微調參數」
- 刪除就是刪除

為什麼這麼嚴：AI 最危險的失敗模式是憑訓練記憶編造法規數值，且編得極像真的。事後補的測試只是把幻覺抄寫第二遍；只有「測試先對著 PDF 抄、參數後編碼」才構成兩次獨立取數。

## RED → Verify RED → GREEN → Verify GREEN → 整理

### 1. RED：先寫測試

在 `rules/rule_tests.json` 新增測試，一次一條規則、單一參數行為：

- `expected` 值**只能抄錄、不能推算**——對著法條清單 PDF 逐字抄
- `source.page` 與 `source.quote`（原文逐字引用）必填——無 quote 的測試引擎直接判 INVALID

### 2. Verify RED（強制，不可跳過）

```bash
python3 tools/fire_code_calc.py run-tests --verify-red {測試ID}
```

沒看著測試失敗，就不知道它測的是不是對的東西。此關卡驗證三件事：

| 檢查 | 不通過的意義 |
|------|------------|
| 測試是紅的（FAIL） | 已經綠 = 測試無鑑別力：你測的是既有參數。重寫測試，或參數先於測試存在 → 刪參數重來 |
| 紅得正確（是 FAIL 不是 INVALID） | INVALID = 測試本身壞掉（缺 quote／格式錯誤），不是「參數缺失」的合法紅。先修測試 |
| 失敗訊息符合預期 | 訊息應顯示「參數尚未編碼」或「與期望值不一致」，而非路徑打錯之類的意外原因 |

### 3. GREEN：編碼最小參數

只把**讓這個測試轉綠所需的參數**寫入 `equipment_rules.json`（附 `legal_basis` 條號）。不順手加其他條文的參數、不「改進」其他規則——那些要走各自的紅綠循環。

### 4. Verify GREEN（強制）

```bash
python3 tools/fire_code_calc.py run-tests --strict
```

- 該測試轉綠，**且其他測試沒有被弄破**
- 測試紅了是參數錯，**修參數，不是修測試**——除非重查 PDF 發現當初抄錄錯誤（此時修 quote 與 expected，並重走 Verify RED）

### 5. 整理（僅在綠燈後）

補 `note`、整理欄位命名、調整 JSON 結構——**不改參數值、不加行為**，改完 `run-tests --strict` 仍須全綠。

## 紅旗清單（出現任何一條：停，刪掉重來）

- 「參數我先寫進去了，等等補測試」
- 「測試第一次跑就綠了」（而你沒有質疑為什麼）
- 「quote 我等抓到 PDF 再補」
- 「這條很簡單，不用走流程」
- 「我已經人工對過 PDF 了，直接寫參數比較快」——人工對照不可重複執行、不留紀錄，不能取代測試
- 「都花時間寫好了，刪掉很浪費」——沉沒成本謬誤；未經驗證的法規參數是審圖系統裡最貴的技術債
- 「這次情況不同，因為……」

## 交付前檢查清單

- [ ] 每條規則的每個參數都有對應測試（`--strict` 覆蓋率檢查通過）
- [ ] 每個測試都經過 Verify RED（看著它紅得正確）
- [ ] 每個 expected 附頁碼＋逐字 quote
- [ ] `run-tests --strict` 全綠、`self-test` 通過
- [ ] 綠 ≠ 核定：新編碼的規則保持 `verified: false`，進下一輪核定表送消防專業人員核定

有任何一項打不了勾？你跳過了先紅再綠。回到鐵律。

# 法定設備需求計算

對 $ARGUMENTS（案件名）依《各類場所消防安全設備設置標準》計算**應設消防安全設備的種類與數量**。輸入為已人工確認的 `case.json`，輸出為附法條依據的應設設備清單。

## 前置檢查

1. 確認 `output/{案件名}-{YYYYMMDD}/case.json` 存在且關鍵欄位 `confidence` 均為 `high`（即已通過人工確認關卡）；否則退回 `/plan-intake`
1-1. 確認 §12 場所分類已經 `/mixed-use-review` 定案（`building.mixed_use_assessment` 非 `null` 且 `source: manual`）；複合用途未定案則先執行 `/mixed-use-review`——戊類複合用途之面積合計方式（以各目為單元）直接影響門檻判斷
2. 讀取 `rules/equipment_rules.json` 的 `regulation_version`，寫入報告標頭
3. 執行 `python3 tools/fire_code_calc.py self-test` 確認規則引擎正常
4. 執行 `python3 tools/fire_code_calc.py run-tests --strict` ——**先紅再綠關卡：任一測試紅，規則庫不得用於本次計算**，先回 `/regulation-intake` 修復

## 執行流程

### 第零步：§13 適用標準判斷（增建・改建・變更用途）

案件涉及增建、改建、室內裝修或變更用途時（`case.json` 的 `interior_renovation`／`change_of_use` 區塊，由 `/plan-intake` 證照文件萃取產生），先判斷各設備適用新標準或變更前標準：

```bash
python3 tools/fire_code_calc.py check-applicability --case output/{案件名}-{YYYYMMDD}/case.json
```

工具依 §13 逐款輸出：款一（七類設備一律新標準）、款二（增建/改建面積逾 1000 ㎡ 或達原總樓地板面積 1/2 → 全棟新標準）、款三（變更為甲類 → 變更後用途設備新標準）、款四（變更前未符規定之設備）。**工具輸出原文嵌入報告**；「室內裝修是否構成增建/改建」與款四之歷史符合性為需人工判讀項。另本步結論（哪些設備適用舊標準）必須在報告標頭注明，否則後續門檻判斷一律視為適用現行標準。

### 第一步：門檻判斷（應設哪些設備）

**必須使用 Bash 呼叫工具，禁止心算、禁止憑記憶引用法規門檻**：

```bash
python3 tools/fire_code_calc.py check-threshold \
  --rules rules/equipment_rules.json \
  --case output/{案件名}-{YYYYMMDD}/case.json
```

工具會逐層、逐設備類別輸出：`應設`／`免設`／`需人工判讀`，附條號與判斷依據。將工具輸出**原文嵌入報告**作為計算記錄。

### 第二步：數量計算（應設多少）

對第一步判定「應設」的每類設備，呼叫對應子命令計算需求數量：

```bash
# 滅火器：滅火效能值需求
python3 tools/fire_code_calc.py extinguisher --use-category {甲|乙|丙|丁} --floor-area {面積}

# 室內消防栓：涵蓋估算（下限值，實際配置依圖面水平距離檢核）
python3 tools/fire_code_calc.py hydrant-coverage --area {面積} --radius {25|15}

# 自動撒水設備：撒水頭數量估算
python3 tools/fire_code_calc.py sprinkler --area {面積} --radius {2.1|2.3|2.6}

# 火警探測器：依種類/裝置高度/構造計算
python3 tools/fire_code_calc.py detector --area {面積} --height {高度} [--fireproof] --detector-type {smoke-1|smoke-2|heat-diff-1|heat-diff-2}

# 收容人數（避難器具、緊急廣播等門檻的基礎）
python3 tools/fire_code_calc.py occupancy --components '{JSON}' [--fixed-seats N]
```

**估算值與精確值要分開標示**：

| 類型 | 說明 | 標示 |
|------|------|------|
| 精確值 | 面積÷法定係數的計算（滅火效能值、探測器數） | 「工具計算」 |
| 估算下限 | 依涵蓋半徑推算的最少數量（消防栓、撒水頭）——實際數量取決於圖面配置與隔間 | 「估算下限，實際配置需依圖面逐點檢核」 |

### 第三步：彙整應設設備清單

輸出固定格式（逐層一張表 + 全案彙總表）：

```
## {樓層} 應設設備清單

| 設備類別 | 設備 | 應設判定 | 法條依據 | 需求數量 | 計算方式 | 備註 |
|---------|------|---------|---------|---------|---------|------|
| 滅火設備 | 滅火器 | 應設 | §14、§31 | 滅火效能值 5 | 工具計算 | 步行距離20m內另需圖面檢核 |
| 滅火設備 | 室內消防栓 | 應設 | §15 | ≥1（估算下限） | 估算下限 | 水平距離涵蓋需圖面檢核 |
| 警報設備 | 火警自動警報 | 應設 | §19 | 偵煙式二種 4 只 | 工具計算 | 分探測區域另計 |
| ...
```

`verified: false` 的規則參數，工具輸出會自帶警語，**警語必須保留在報告中**。

### 第四步：需人工判讀清單

集中列出所有工具判定為 `需人工判讀` 的項目（無開口樓層、排煙區劃、複合用途邊界等），說明各需要什麼補充資料（大樣圖／開口計算書／現場勘查）。

### 第五步：保存

寫入 `output/{案件名}-{YYYYMMDD}/{案件名}-requirements.md`，標頭注明：法規版本、case.json 確認日期、規則庫中未核定（`verified: false`）參數的比例。

## 重要注意事項

1. **每一項判定必附條號**——引用不到條號的一律降級為「建議事項」
2. **工具輸出原文嵌入**——這是審查者覆核計算過程的依據
3. **免設也要列**——免設判定同樣附計算過程與條文，供覆核
4. 遵守 `CLAUDE.md` 審圖最高原則

# Graph Report - rules  (2026-07-24)

## Corpus Check
- Corpus is ~42,156 words - fits in a single context window. You may not need a graph.

## Summary
- 339 nodes · 369 edges · 46 communities (20 shown, 26 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- 消防設計綱要（第2編）
- 氣體與乾粉滅火設備
- 消防栓與自動撒水設備
- 避難器具
- 火警警報與緊急電源
- 滅火器與消防栓設置
- 水霧與泡沫滅火設備
- 出口標示與避難指標
- 甲類場所用途分類
- 乙類場所用途分類
- 消防搶救設備應設場所
- 手動報警與緊急廣播
- 火警探測器
- 排煙設備構造規定
- 緊急照明設備
- 連結送水管構造
- 丙類場所用途分類
- 消防專用蓄水池
- 火警受信總機
- 防災監控綜合操作裝置
- 丁類場所用途分類
- 簡易自動滅火設備
- 緊急電源插座
- 配線耐燃耐熱保護
- 訂定依據（第1條）
- 設備國家標準認可
- 增改建適用標準（第13條）
- 水霧泡沫簡易滅火（第18條）
- 防火區劃視為另一場所
- 消防安全設備分類
- 第197條 公共危險物品
- 第198條 公共危險物品
- 第199條 公共危險物品
- 第200條 公共危險物品
- 第201條 公共危險物品
- 第202條 公共危險物品
- 第203條 公共危險物品
- 第220條 附則
- 第222條 附則
- 第225條 附則
- 第226條 附則
- 第228條 附則
- 第231條 附則
- 第232條 附則
- 第233條 附則
- 緊急供電系統電源

## God Nodes (most connected - your core abstractions)
1. `避難器具` - 20 edges
2. `自動撒水設備` - 17 edges
3. `第12條 各類場所用途分類` - 16 edges
4. `甲類` - 16 edges
5. `二氧化碳及惰性氣體滅火設備` - 14 edges
6. `出口標示燈` - 13 edges
7. `泡沫滅火設備` - 12 edges
8. `避難方向指示燈` - 12 edges
9. `乙類` - 12 edges
10. `火警探測器` - 11 edges

## Surprising Connections (you probably didn't know these)
- `rules/README.md 法規資料取用格式` --references--> `複合用途建築物`  [EXTRACTED]
  README.md → 法規/第2編-消防設計.md
- `第207條` --references--> `自動撒水設備`  [EXTRACTED]
  法規/第4編-公共危險物品等場所.md → 法規/第3編-第1章-滅火設備.md
- `第205條` --references--> `室內消防栓設備`  [EXTRACTED]
  法規/第4編-公共危險物品等場所.md → 法規/第3編-第1章-滅火設備.md
- `第229條` --references--> `自動撒水設備`  [EXTRACTED]
  法規/第4編-公共危險物品等場所.md → 法規/第3編-第1章-滅火設備.md
- `第208條` --references--> `水霧滅火設備`  [EXTRACTED]
  法規/第4編-公共危險物品等場所.md → 法規/第3編-第1章-滅火設備.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **第8條 滅火設備種類共同構成** — rules_法規_第2編_消防設計_第8條, rules_法規_第2編_消防設計_滅火器, rules_法規_第2編_消防設計_室內消防栓設備, rules_法規_第2編_消防設計_室外消防栓設備, rules_法規_第2編_消防設計_自動撒水設備 [EXTRACTED 1.00]
- **第11條 消防搶救上必要設備共同構成** — rules_法規_第2編_消防設計_第11條, rules_法規_第2編_消防設計_連結送水管, rules_法規_第2編_消防設計_消防專用蓄水池, rules_法規_第2編_消防設計_排煙設備, rules_法規_第2編_消防設計_緊急電源插座, rules_法規_第2編_消防設計_無線電通信輔助設備, rules_法規_第2編_消防設計_防災監控系統綜合操作裝置 [EXTRACTED 1.00]
- **第12條 各類場所用途分類共同構成** — rules_法規_第2編_消防設計_第12條, rules_法規_第2編_消防設計_甲類場所, rules_法規_第2編_消防設計_乙類場所, rules_法規_第2編_消防設計_丙類場所, rules_法規_第2編_消防設計_丁類場所, rules_法規_第2編_消防設計_戊類場所 [EXTRACTED 1.00]
- **自動撒水設備相關條文群 (第43-60條)** — concept_自動撒水設備, rules_法規_第3編_第1章_滅火設備_第43條, rules_法規_第3編_第1章_滅火設備_第46條, rules_法規_第3編_第1章_滅火設備_第57條, rules_法規_第3編_第1章_滅火設備_第58條 [EXTRACTED 0.90]
- **二氧化碳及惰性氣體全區放射設計條文群** — concept_二氧化碳滅火設備, rules_法規_第3編_第1章_滅火設備_第82條, rules_法規_第3編_第1章_滅火設備_第83條, rules_法規_第3編_第1章_滅火設備_第84條, rules_法規_第3編_第1章_滅火設備_第86條 [EXTRACTED 0.90]
- **加壓送水裝置準用第58條之設備群** — concept_加壓送水裝置, rules_法規_第3編_第1章_滅火設備_第58條, rules_法規_第3編_第1章_滅火設備_第65條, rules_法規_第3編_第1章_滅火設備_第77條 [EXTRACTED 0.85]
- **避難逃生設備體系** — concept_出口標示燈, concept_避難方向指示燈, concept_避難指標, concept_避難器具, concept_緊急照明設備 [EXTRACTED 1.00]
- **消防搶救上之必要設備** — concept_連結送水管, concept_消防專用蓄水池, concept_排煙設備, concept_緊急電源插座, concept_無線電通信輔助設備 [EXTRACTED 1.00]
- **第四類公共危險物品滅火設備擇一設置** — concept_水霧滅火設備, concept_泡沫滅火設備, concept_二氧化碳滅火設備, concept_惰性氣體滅火設備, concept_鹵化烴滅火設備, concept_乾粉滅火設備 [EXTRACTED 1.00]

## Communities (46 total, 26 thin omitted)

### Community 0 - "消防設計綱要（第2編）"
Cohesion: 0.08
Nodes (41): rules/README.md 法規資料取用格式, 一一九火災通報裝置, 丁類場所, 丙類場所, 乙類場所, 地下建築物, 室內消防栓設備, 室外消防栓設備 (+33 more)

### Community 1 - "氣體與乾粉滅火設備"
Cohesion: 0.07
Nodes (35): 乾粉滅火設備, 二氧化碳及惰性氣體滅火設備, 惰性氣體滅火設備, 鹵化烴滅火設備, 第100條 乾粉噴頭, 第101條 室內停車空間乾粉藥劑, 第110條 乾粉啟動, 第111條 移動式乾粉設備 (+27 more)

### Community 2 - "消防栓與自動撒水設備"
Cohesion: 0.09
Nodes (27): 加壓送水裝置, 自動撒水設備, 第32條 室內消防栓配管配件屋頂水箱, 第37條 室內消防栓加壓送水裝置, 第42條 室外消防栓加壓送水裝置, 第43條 自動撒水設備種類, 第44條 自動撒水配管配件屋頂水箱, 第46條 撒水頭配置 (+19 more)

### Community 3 - "避難器具"
Cohesion: 0.10
Nodes (27): 救助袋, 滑杆, 滑臺, 緩降機, 避難器具, 避難梯, 避難橋, 避難繩索 (+19 more)

### Community 4 - "火警警報與緊急電源"
Cohesion: 0.10
Nodes (21): 一一九火災通報裝置, 火警自動警報設備, 瓦斯漏氣火警自動警報設備, 緊急電源, 第38條 室內消防栓緊急電源, 第60條 自動撒水緊急電源, 第95條 二氧化碳惰性氣體緊急電源, 第97-8條 鹵化烴緊急電源 (+13 more)

### Community 5 - "滅火器與消防栓設置"
Cohesion: 0.10
Nodes (21): 公共危險物品, 室內消防栓設備, 室外消防栓設備, 滅火器, 第31條 滅火器設置規定, 第33條 室內消防栓立管加壓試驗, 第34條 第一種與第二種消防栓, 第35條 室內消防栓箱 (+13 more)

### Community 6 - "水霧與泡沫滅火設備"
Cohesion: 0.11
Nodes (18): 水霧滅火設備, 泡沫滅火設備, 第61條 水霧噴頭配置, 第63條 水霧放射區域, 第64條 水霧水源容量, 第66條 水霧配管與高壓電距離, 第68條 室內停車空間水霧排水, 第69條 泡沫放射方式 (+10 more)

### Community 7 - "出口標示與避難指標"
Cohesion: 0.22
Nodes (17): 出口標示燈, 標示設備, 避難指標, 避難方向指示燈, 第146-1條, 第146-2條, 第146-3條, 第146-4條 (+9 more)

### Community 8 - "甲類場所用途分類"
Cohesion: 0.12
Nodes (16): 甲類, 甲類（一）歌廳、舞廳、夜總會、俱樂部, 甲類（一）理容院、指壓按摩場所, 甲類（一）酒家、酒吧、酒店（廊）, 甲類（一）錄影節目帶播映場所（MTV）、視聽歌唱場所（KTV）, 甲類（一）電影片映演場所（戲院、電影院）, 甲類（七）三溫暖、公共浴室, 甲類（三）觀光旅館、飯店、旅館、招待所（限有寢室客房者） (+8 more)

### Community 9 - "乙類場所用途分類"
Cohesion: 0.14
Nodes (14): 乙類, 乙類（一）車站、飛機場大廈、候船室, 乙類（七）集合住宅、寄宿舍, 乙類（三）兒童及少年福利機構、學校教室、補習班、訓練班、K書中心、安親（才藝）班, 乙類（九）室內溜冰場、室內游泳池, 乙類（二）期貨經紀業、證券交易所、金融機構, 乙類（五）寺廟、宗祠、教堂、靈骨塔, 乙類（八）體育館、活動中心 (+6 more)

### Community 10 - "消防搶救設備應設場所"
Cohesion: 0.14
Nodes (14): 排煙設備, 消防專用蓄水池, 無線電通信輔助設備, 第11條 消防搶救上必要設備種類, 第26條 應設連結送水管場所, 第27條 應設消防專用蓄水池場所, 第28條 應設排煙設備場所, 第29條 應設緊急電源插座場所 (+6 more)

### Community 11 - "手動報警與緊急廣播"
Cohesion: 0.18
Nodes (12): 手動報警設備, 緊急廣播設備, 第129條 火警發信機, 第130條 標示燈, 第131條 火警警鈴, 第132條 手動報警裝置位置, 第133條 緊急廣播揚聲器, 第134條 緊急廣播分區 (+4 more)

### Community 12 - "火警探測器"
Cohesion: 0.17
Nodes (12): 火警探測器, 第114條 探測器高度選擇, 第115條 探測器裝置位置, 第116條 免設探測器處所, 第117條 偵煙火焰式禁設處所, 第118條 特定場所探測器選擇, 第119條 探測區域劃定, 第120條 局限型探測器有效範圍 (+4 more)

### Community 13 - "排煙設備構造規定"
Cohesion: 0.29
Nodes (7): 排煙設備, 無線電通信輔助設備, 第188條, 第189條, 第190條, 第192條, 第229條

### Community 14 - "緊急照明設備"
Cohesion: 0.29
Nodes (7): 緊急照明設備, 第175條, 第176條, 第177條, 第178條, 第179條, 第219條

### Community 15 - "連結送水管構造"
Cohesion: 0.33
Nodes (6): 連結送水管, 第180條, 第181條, 第182條, 第183條, 第184條

### Community 16 - "丙類場所用途分類"
Cohesion: 0.50
Nodes (4): 丙類, 丙類（一）電信機器室, 丙類（三）室內停車場、建築物依法附設之室內停車空間, 丙類（二）汽車修護場、飛機修理廠、飛機庫

### Community 17 - "消防專用蓄水池"
Cohesion: 0.50
Nodes (4): 消防專用蓄水池, 第185條, 第186條, 第187條

### Community 18 - "火警受信總機"
Cohesion: 0.67
Nodes (3): 火警受信總機, 第125條 火警受信總機規定, 第126條 受信總機位置

### Community 19 - "防災監控綜合操作裝置"
Cohesion: 1.00
Nodes (3): 防災監控系統綜合操作裝置, 第192-1條, 第223條

## Knowledge Gaps
- **195 isolated node(s):** `rules/README.md 法規資料取用格式`, `第1條 訂定依據`, `第3條 未定國家標準設備認可`, `第5條 防火區劃視為另一場所`, `第7條 消防安全設備分類` (+190 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `第39條 室外消防栓配管試壓緊急電源` connect `滅火器與消防栓設置` to `消防栓與自動撒水設備`, `火警警報與緊急電源`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `第208條` connect `氣體與乾粉滅火設備` to `滅火器與消防栓設置`, `水霧與泡沫滅火設備`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `第38條 室內消防栓緊急電源` connect `火警警報與緊急電源` to `滅火器與消防栓設置`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **What connects `rules/README.md 法規資料取用格式`, `第1條 訂定依據`, `第3條 未定國家標準設備認可` to the rest of the system?**
  _195 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `消防設計綱要（第2編）` be split into smaller, more focused modules?**
  _Cohesion score 0.07560975609756097 - nodes in this community are weakly interconnected._
- **Should `氣體與乾粉滅火設備` be split into smaller, more focused modules?**
  _Cohesion score 0.06890756302521009 - nodes in this community are weakly interconnected._
- **Should `消防栓與自動撒水設備` be split into smaller, more focused modules?**
  _Cohesion score 0.09401709401709402 - nodes in this community are weakly interconnected._
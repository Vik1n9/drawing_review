# 協作指南

本專案分成兩個角色：技術人員負責開發與維護這個倉庫的架構，消防專業人員則把倉庫導入自己電腦上的 AI 工具（Claude Code、Codex、OpenCode 都可以）獨立作業。

消防專業人員不需要寫程式，也不需要操作 git，但會直接跟 AI 互動。載入倉庫後照開場導引走就好，不必等技術人員代跑。

## 角色與職責

| 角色 | 職責 | 工作介面 |
|------|------|---------|
| 技術人員／架構管理者 | 架構開發與維護、流程管控、規則編碼（先紅再綠）、git/PR/CI、法規全文與圖譜維護 | 本 repo 全部 |
| 消防專業人員 | 跑開場導引、裁示疑義表、執行審圖案件、判讀交付物、提供法規解釋與誤判回饋 | 自己電腦上的 AI 工具 ＋ `output/` 交付物 |

## 消防專業人員的作業入口

載入倉庫後跑這一行（Windows 沒有 `python3` 就用 `python`）：

```bash
python3 tools/onboarding.py status
```

再跟你的 AI 說「照 `skills/onboarding.md` 帶我開始」，它會依序引導：
① 本機成果保護 → ② 待確認事項裁示 → ③ 法規圖譜 → ④ 環境工具 → ⑤ 規則庫健康 → ⑥ 操作簡介。

導引有兩條安全底線：唯讀檢查 AI 可以直接跑，會改動系統的動作（安裝套件、回填裁示、重建圖譜）一律先說明並取得你的同意。另外，AI 不得代替你裁示任何法規事項。

## 消防專業人員的四種貢獻方式

1. **疑義表裁示**（主要路徑）：開場導引第一步會列出規則參數和現行條文比對出的差異，逐則回覆「採納更正／維持現值／另有更正＋正確值」，AI 代跑 `pending_review.py decide` 與 `apply --all`，工具會自動走先紅再綠完成更正並回填 `verified`
2. **規則核定表**（可選路徑）：需要留紙本簽名紀錄時，還是可以用 `verification_sheet.py export` 匯出核定表 HTML 或紙本，逐條勾選簽名後回傳。流程見 `governance/README.md`
3. **法規解釋**：口述或寫 memo 都行（函釋文號、但書適用、實務認定慣例）。法典沒涵蓋到的實務見解走 `/practice-note`（Practice Note）寫進 `practice_notes/`，不要直接改規則參數
4. **誤判回饋**：審查產出（問題清單、打勾檢核 HTML）本來就是寫給人讀的，直接指出「這條判錯了」和理由即可，技術人員會把它轉成測試案例來修規則

## 支援的 AI 工具

本倉庫不綁定單一 AI 工具。下面三層觸發機制，任何一層都能把使用者接進開場導引：

| 層 | 檔案 | 涵蓋範圍 |
|----|------|---------|
| 1 | `README.md`「先跑這兩行」與 `docs/使用手冊.md` | 所有工具，以及自己動手貼的使用者 |
| 2 | `AGENTS.md`（行為契約的正本；`CLAUDE.md` 只是指向它的指標） | Codex、OpenCode、Claude Code 等會讀代理指示檔的工具 |
| 3 | `.claude/settings.json` 的 SessionStart hook | 只有 Claude Code。這是加分的自動化，不是機制本體 |

實作上有三條規範：

- **不要把導引綁在某一家工具的專屬機制上。** 新增前置檢查時，入口一律是 `python3 tools/onboarding.py status`，不要只寫進 hook，也不要只寫進某一份代理指示檔
- **面向使用者的文字不能只給斜線指令。** `/gap-analysis`、`/train` 這類指令只有 Claude Code 有，其他工具得用自然語言加上 `skills/*.md` 檔名。真要寫斜線指令，只能當附註
- **新增的安全紅線，三層都要涵蓋。** 只寫進 `.claude/settings.json` 的 `PreToolUse` hook，等於只保護到 Claude Code 使用者；只寫進 `AGENTS.md`，對不讀代理指示檔的工具就無效。所以紅線本體放 `AGENTS.md`（受 30 行／2500 bytes 預算限制，逐條細節移到對應的 skill），程序放 `skills/`，狀態由 `onboarding.py status` 給出，hook 當加分層

## 兩條發佈路線

| 線 | 產物 | 給誰 | 更新方式 |
|---|---|---|---|
| 線1 | `git clone` | 技術人員、送 PR 的人 | `update_guard.py snapshot` → `commit` → `git pull --ff-only` |
| 線2 | GitHub Release 的 `setup.exe`（7-Zip 自解壓縮檔）＋ `.zip` | 消防專業人員 | 裝到同一個資料夾，`update_guard.py install` 逐檔判定 |

線2 為什麼要存在？因為使用者不懂 git，而讓 AI 代跑 git 正是本機訓練成果被蓋掉的主要來源。安裝包裡沒有 `.git`，自然也就沒有 `git pull` 撞到本機改動的問題。

發版流程寫在 `.github/workflows/release.yml`，推 `v*` tag 觸發：

1. 跑完整把關（單元測試、`self-test`、`run-tests --strict`、圖譜新鮮度）。規則測試沒全綠的版本不出貨
2. `python3 tools/make_release.py --version {版本}` 打包，順便產生 `安裝清單.json`
3. 解壓安裝包，跑它自己的測試與開場診斷，驗的是「拿掉範例圖之後它還跑不跑得起來」
4. `python3 tools/make_sfx.py` 串成 `setup.exe`。整條建置都在 ubuntu 上跑，7-Zip SFX 只是把「模組 ＋ 設定 ＋ 封存」串起來，不需要 Windows 工具鏈
5. windows runner 只做驗證，不裝任何工具鏈：全新安裝 → 開場診斷 → 對同一個資料夾再裝一次，驗升級語意
6. 建立草稿 Release，人工確認過才發佈

保留 windows job 的理由不是為了建置，是中文檔名在 Windows 上的編碼問題。`安裝清單.json`、`待確認事項.md`、`.上游新版` 全是非 ASCII，cp950 主控台是經典地雷，而這種問題在 Linux 上永遠測不出來。

`安裝清單.json` 是線2 的上游基準。安裝目錄沒有 git，只能靠它逐檔的 sha256 才分得出哪些是「上游出貨的原樣」、哪些是「使用者改過的」。它是打包產物，不需要人工維護。

### 為什麼從 Inno Setup 換成自解壓縮檔

前一版用 Inno Setup，代價是一份 220 行的 `.iss`，其中 136 行 Pascal Script 沒有任何測試涵蓋，而且 CI 得多開一台 `windows-latest` 跑 `choco install innosetup`。換掉之後，那 136 行變成 20 行以內的 `安裝.bat`（由 `make_sfx.py` 產生，內容有測試釘住）。

結構上也更安全。`7zS2.sfx` 把酬載解到 `%TEMP%`、執行 `RunProgram`、結束後清掉，在 `tools/installer.py` 跑起來之前，使用者的資料夾一個位元組都沒被碰過。Inno Setup 則是在安裝過程中逐檔複製到 `{app}`，靠 Pascal 判斷該落在暫存還是本體，判斷錯就是部分覆蓋；換成 SFX 之後，這種錯誤根本不可能發生。

代價也要誠實記著：自解壓縮檔被防毒誤判、隔離的機率比 Inno Setup 高（惡意程式常用這種殼），企業電腦尤其明顯。所以 `.zip` 不是可有可無的附屬品，它是唯一的退路，Release notes 必須寫得夠明顯。

### 建置輸入的釘選規則

兩個資料檔，兩種相反的處理方式，理由各自不同：

| 檔案 | 釘 sha256？ | 為什麼 |
|---|:---:|---|
| `packaging/sfx-module.json` | ✅ | 這是建置輸入，會原封不動接進我們發出去的 exe，完整性得釘死；而且它極少更新，釘住也不會腐爛。（注意：現代的 `7z*-extra.7z` 已經不含 `.sfx`，模組的家在 LZMA SDK 的 `bin/`） |
| `packaging/python-runtime.json` | ❌ | Python 要跟著安全更新走，釘死雜湊反而會腐爛：一出安全更新，釘住的就是舊版，要跟上就得每次人工重算，這種維護稅遲早沒人繳。改成在 `安裝.bat` 裡驗 Authenticode 發行者簽章，檢查的是「這真的是 Python Software Foundation 出的」，換版本不必動到任何雜湊 |

安裝殼層只做偵測與呼叫，逐檔判定一律放 Python（`tools/installer.py` ＋ `update_guard.py install`）。同一份邏輯寫兩次遲早會漂移成兩種行為，而殼層腳本又沒有單元測試。`安裝.bat` 的內容由 `tests/test_make_sfx.py` 釘住，包括切碼頁、驗簽章和行數上限。

## 更新倉庫的規範

- **把使用者產物收進 `.gitignore` 是防護的一環，不只是「不進版控」而已。** `git clean -fd`（不加 `-x`）不刪 gitignored 檔案，`git checkout`／`reset` 也永遠不會碰它們，所以光是一段 `.gitignore`，就讓整類威脅對 `input/{案件}/`、`output/`、`training/{批次}/`、`practice_notes/*.json` 失效
- **代價是使用者要送 PR 回饋 practice note 時得加 `git add -f`。** 這是刻意的取捨：拿一個偶爾才用到的旗標，換數月成果的保護，划算
- **已經被追蹤的檔案，ignore 是無效的**（`output/` 現有交付物、`training/registry.json`），那些只能靠 `update_guard.py` 的備份
- 新增會寫入 `update_guard.py` `DATA_ZONES` 的工具時，保護清單與 `OWNER_RULES` 要同步更新。分區沒歸類到的檔案，`check` 會報「保護清單需複核」，不變式測試 `test_known_zones_cover_the_whole_repository` 也會紅燈
- **`owner` 的 `user` 和 `shared` 要分對。** `shared` 指的是使用者裁示與上游修法交錯的檔案（`rules/`、`graphify-out/`），`restore` 對它預設拒絕整檔還原。標錯的話，救援會把上游的法規更新一起吃掉

## 架構管理者的變更規範

### 改 `rules/`（規則庫）

- **一定要走先紅再綠**（完整紀律見 `skills/red-green.md`，改編自 obra/superpowers 的 TDD skill）：先在 `rule_tests.json` 寫測試（expected 逐字抄錄法規原文，附 `source.article`，附表類另附 `source.page` 與 quote）→ `run-tests --verify-red {測試ID}` 確認紅得正確 → 編碼最小參數 → `run-tests --strict` 轉綠
- **鐵律**：如果發現參數比測試先寫進去，把那個參數刪掉重來，不要留著當參考
- `verified: true` 只能經 `tools/verification_sheet.py apply` 產生，results JSON 一定要附 `verified_by` 與 `verified_date`（走紙本簽名流程時另附 `evidence` 指向簽名掃描檔）
- **和現行條文比對出差異的規則，不得回填 `verified: true`。** 差異要寫進 `governance/待確認清單/rule-discrepancies-{日期}.json`，`apply` 會擋下該規則；只有使用者裁示「維持現值」時，才在那筆 results 加上 `"override_discrepancy": true` 並註明理由
- PR 說明要附法條依據，條號和頁碼都要有

### 改 `skills/`（工作流）

- 說明你改了哪個步驟、為什麼要改。動到關卡（人工確認、抽檢准出、先紅再綠）的部分，PR 裡要特別標注出來

### 改 `tools/`

- **維持 stdlib-only。** 使用者多半只裝了一個 AI 桌面版就開始用，沙盒環境讓 `pip install` 常常失敗，多一個第三方相依，等於把那些人擋在門外
- **要加第三方相依之前，先證明標準庫真的做不到。** 舉個反例：DXF 一度被認為非 `ezdxf` 不可，但它其實是純文字的 group code 格式，`tools/dxf_parse.py` 用標準庫就解決了
- **任何第三方相依都必須是選用的，缺席時要有替代路徑。** 替代路徑登記在 `tools/check_env.py` 的 `CAPABILITY_SPECS`，`tests/test_check_env.py` 會強制檢查「不可用的能力一定有替代路徑」
- 目前的選用相依有三個：`openpyxl`（兩階段 Excel 交付物，替代方案是 HTML 版檢核清單）、`pymupdf`（legacy PDF 標註，替代方案是交付物1 的 HTML／SVG 標註）、`ezdxf`（二進位 DXF 後備，替代方案是請使用者改存 ASCII DXF）
- 動到計算邏輯，就要有對應的測試案例

## 流程規範

1. 所有變更都走分支加 PR，不直接 push main
2. CI（`.github/workflows/rule-tests.yml`）會自動跑 `self-test` 與 `run-tests --strict`，紅燈不得合併
3. commit message 用中文，講清楚改了什麼、法源依據是什麼
4. `input/` 裡的圖面與法規 PDF 如果涉及實際案件，先確認能不能入庫（個資、機密），不確定就別 commit

## 品質底線（不可協商）

- 每項判定都要附法條條號；引不到條號的，降級成建議事項
- 禁止心算，也禁止憑記憶引法規數值
- 不確定就標「需人工判讀」，不要用推測填充
- 本專案的輸出僅供審圖輔助，最終判斷歸屬專業消防人員

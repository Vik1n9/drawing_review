# 協作指南

本專案採兩角色分工：**技術人員負責開發與維護本倉庫的架構；消防專業人員自行把倉庫導入自己電腦上的 AI 工具（Claude Code／Codex／OpenCode 等皆可）獨立作業。**

消防專業人員不需要寫程式、不需要操作 git，但**會直接與 AI 互動**——載入倉庫後照開場導引走即可，不必等技術人員代跑。

## 角色與職責

| 角色 | 職責 | 工作介面 |
|------|------|---------|
| **技術人員／架構管理者** | 架構開發與維護、流程管控、規則編碼（先紅再綠）、git/PR/CI、法規全文與圖譜維護 | 本 repo 全部 |
| **消防專業人員** | 跑開場導引、裁示疑義表、執行審圖案件、判讀交付物、提供法規解釋與誤判回饋 | 自己電腦上的 AI 工具 ＋ `output/` 交付物 |

## 消防專業人員的作業入口

載入倉庫後跑這一行（Windows 沒有 `python3` 就用 `python`）：

```bash
python3 tools/onboarding.py status
```

再跟你的 AI 說「照 `skills/onboarding.md` 帶我開始」，它會依序引導：
① 本機成果保護 → ② 待確認事項裁示 → ③ 法規圖譜 → ④ 環境工具 → ⑤ 規則庫健康 → ⑥ 操作簡介。

導引的兩條安全底線：**唯讀檢查 AI 可直接跑；會改動系統的動作（安裝套件、回填裁示、重建圖譜）一律先說明並取得你的同意**，且 **AI 不得代替你裁示任何法規事項**。

## 消防專業人員的四種貢獻方式

1. **疑義表裁示**（主要路徑）：開場導引第一步會列出規則參數與現行條文比對出的差異，逐則回覆「採納更正／維持現值／另有更正＋正確值」，AI 代跑 `pending_review.py decide` 與 `apply --all`——工具自動走先紅再綠完成更正並回填 `verified`
2. **規則核定表**（可選路徑）：需要留紙本簽名紀錄時，仍可用 `verification_sheet.py export` 匯出核定表 HTML／紙本，逐條勾選簽名回傳。流程詳見 `governance/README.md`
3. **法規解釋**：口述或寫 memo（函釋文號、但書適用、實務認定慣例）。法典未涵蓋的實務見解走 `/practice-note`（Practice Note）寫入 `practice_notes/`，**不得直接改規則參數**
4. **誤判回饋**：審查產出（問題清單、打勾檢核 HTML）本來就是給人讀的——直接指出「這條判錯了」＋理由，由技術人員轉成測試案例修正規則

## 支援的 AI 工具

本倉庫**不綁定單一 AI 工具**。三層觸發機制任一層都能把使用者接進開場導引：

| 層 | 檔案 | 涵蓋範圍 |
|----|------|---------|
| 1 | `README.md` 最上方的可貼區塊 | 所有工具，以及自己動手貼的使用者 |
| 2 | `AGENTS.md`（行為契約**正本**；`CLAUDE.md` 只是指向它的指標） | Codex、OpenCode、Claude Code 等會讀代理指示檔的工具 |
| 3 | `.claude/settings.json` 的 SessionStart hook | 僅 Claude Code——**加分自動化，不是機制本體** |

三條實作規範：

- **不得把導引綁在某家工具的專屬機制上。** 新增前置檢查時，入口一律是 `python3 tools/onboarding.py status`，不要只寫進 hook 或只寫進某一份代理指示檔
- **面向使用者的文字不得只給斜線指令。** `/gap-analysis`、`/train` 這類指令只有 Claude Code 有；其他工具用自然語言＋`skills/*.md` 檔名。要寫斜線指令的話，只能作為附註
- **新增的安全紅線三層都要涵蓋。** 只寫進 `.claude/settings.json` 的 `PreToolUse` hook 等於只保護 Claude Code 使用者；只寫進 `AGENTS.md` 則對不讀代理指示檔的工具無效。紅線本體放 `AGENTS.md`（受 30 行／2500 bytes 預算限制，逐條細節移到對應 skill）、程序放 `skills/`、`onboarding.py status` 給出狀態、hook 當加分層

## 兩條發佈路線

| 線 | 產物 | 給誰 | 更新方式 |
|---|---|---|---|
| 線1 | `git clone` | 技術人員、送 PR 的人 | `update_guard.py snapshot` → `commit` → `git pull --ff-only` |
| 線2 | GitHub Release 的 `setup.exe` ＋ `.zip` | 消防專業人員 | 裝到同一個資料夾，`update_guard.py install` 逐檔判定 |

線2 存在的理由：使用者不懂 git，而**讓 AI 代跑 git 正是本機訓練成果被蓋掉的來源**。安裝包沒有 `.git`，也就沒有 `git pull` 撞到本機改動的問題。

發版流程（`.github/workflows/release.yml`，推 `v*` tag 觸發）：

1. 跑完整把關（單元測試、`self-test`、`run-tests --strict`、圖譜新鮮度）——規則測試沒全綠的版本不得出貨
2. `python3 tools/make_release.py --version {版本}` 打包，並產生 `安裝清單.json`
3. 解壓安裝包、跑它自己的測試與開場診斷（驗「拿掉範例圖之後它還跑不跑得起來」）
4. Windows runner 用 Inno Setup 編出 `setup.exe`，跑全新安裝煙霧測試
5. 建立**草稿** Release，人工確認後才發佈

`安裝清單.json` 是線2 的上游基準：安裝目錄沒有 git，靠它逐檔的 sha256 才分得出「上游出貨的原樣」與「使用者改過的」。它是打包產物，不需要人工維護。

**`packaging/fire-review.iss` 的 Pascal Script 只做偵測與呼叫，逐檔判定邏輯一律放 Python**（`update_guard.py install`）——同一份邏輯寫兩次遲早漂移成兩種行為，而 Pascal Script 沒有任何測試。

## 更新倉庫的規範

- **`.gitignore` 收編使用者產物是防護的一部分，不只是「不進版控」。** `git clean -fd`（不加 `-x`）不刪 gitignored 檔案，`git checkout`／`reset` 也永遠不會碰它們——一段 `.gitignore` 就讓整類威脅對 `input/{案件}/`、`output/`、`training/{批次}/`、`practice_notes/*.json` 失效
- **代價：使用者要送 PR 回饋 practice note 時需要 `git add -f`。** 這是刻意的取捨——保護數月的成果，值得換一個偶爾才用到的旗標
- **已經被追蹤的檔案 ignore 無效**（`output/` 現有交付物、`training/registry.json`），那些只能靠 `update_guard.py` 的備份
- 新增會寫入 `update_guard.py` `DATA_ZONES` 的工具時，**必須同步保護清單與 `OWNER_RULES`**。分區沒歸類的檔案會被 `check` 報成「保護清單需複核」（不變式測試 `test_known_zones_cover_the_whole_repository` 也會紅燈）
- **`owner` 的 `user` 與 `shared` 要分對。** `shared` 是使用者裁示與上游修法交錯的檔案（`rules/`、`graphify-out/`），`restore` 對它預設拒絕整檔還原——標錯會讓救援把上游的法規更新一起吃掉

## 架構管理者的變更規範

### 改 `rules/`（規則庫）

- **必須走先紅再綠**（完整紀律見 `skills/red-green.md`，改編自 obra/superpowers 的 TDD skill）：先在 `rule_tests.json` 寫測試（expected 逐字抄錄法規原文、附 `source.article`／附表類附 `source.page` 與 quote）→ `run-tests --verify-red {測試ID}` 確認紅得正確 → 編碼最小參數 → `run-tests --strict` 轉綠
- **鐵律**：發現參數先於測試被寫入，刪除該參數重來，不保留當參考
- `verified: true` 只能經 `tools/verification_sheet.py apply` 產生，且 results JSON 必附 `verified_by` 與 `verified_date`（走紙本簽名流程時另附 `evidence` 指向簽名掃描檔）
- **與現行條文比對出差異的規則不得回填 `verified: true`**：差異寫入 `governance/待確認清單/rule-discrepancies-{日期}.json`，`apply` 會擋下該規則；使用者裁示「維持現值」時才於該筆 results 加 `"override_discrepancy": true` 並註明理由
- PR 說明必附法條依據（條號＋頁碼）

### 改 `skills/`（工作流）

- 說明改動了哪個步驟、為什麼；涉及關卡（人工確認、抽檢准出、先紅再綠）的刪改需在 PR 中特別標注

### 改 `tools/`

- **維持 stdlib-only。** 使用者多半只裝了一個 AI 桌面版就開始用，沙盒讓 `pip install` 往往失敗——第三方相依等於把那些人擋在門外
- **新增第三方相依前，必須先證明標準庫做不到。** 反例：DXF 曾被認為需要 `ezdxf`，實際上它是純文字的 group code 格式，`tools/dxf_parse.py` 用標準庫就解決了
- **任何第三方相依都必須是選用的，而且缺席時要有替代路徑。** 替代路徑登記在 `tools/check_env.py` 的 `CAPABILITY_SPECS`，`tests/test_check_env.py` 會強制檢查「不可用的能力一定有替代路徑」
- 目前的選用相依：`openpyxl`（兩階段 Excel 交付物，替代：HTML 版檢核清單）、`pymupdf`（legacy PDF 標註，替代：交付物1 的 HTML／SVG 標註）、`ezdxf`（二進位 DXF 後備，替代：請使用者改存 ASCII DXF）
- 改動計算邏輯必須有對應測試案例

## 流程規範

1. 所有變更走分支 ＋ PR，不直接 push main
2. CI（`.github/workflows/rule-tests.yml`）自動跑 `self-test` 與 `run-tests --strict`，紅燈不得合併
3. commit message 用中文，說清楚改了什麼、法源依據是什麼
4. `input/` 內的圖面與法規 PDF 若涉及實際案件，先確認可否入庫（個資／機密），不確定就不要 commit

## 品質底線（不可協商）

- 每項判定附法條條號；引不到條號的降級為建議事項
- 禁止心算、禁止憑記憶引法規數值
- 不確定就標「需人工判讀」，不用推測填充
- 本專案輸出僅供審圖輔助，最終判斷歸屬專業消防人員

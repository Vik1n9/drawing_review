# 安全更新（更新倉庫、重裝、救回被蓋掉的成果）

使用者的訓練成果——規則裁示、實務見解、案件圖面、交付物——**只存在他這台電腦，
從未推上遠端**。更新方式錯了就是永久消失，不是「再抓一次就好」。

本檔是 `AGENTS.md` 底線 6 的完整程序。

## 觸發時機

使用者說「更新到最新版」「拉最新的」「同步一下倉庫」「重新下載」「裝新版」，
或貼上倉庫網址要你更新；以及 `python3 tools/update_guard.py check` 回結束碼 2／3／4 時。

**只要牽涉到「把上游的新內容弄進來」，就走本檔。**

## 前置認知

1. 使用者是消防專業人員，不懂 git。他說「更新」的意思是「我要新版的法規和功能」，
   **不是**「請你操作 git」
2. 本流程**不做任何法規判斷**——只處理檔案與版本
3. 有兩條取得路徑，程序不同：**線1 是 `git clone`**（技術人員），
   **線2 是安裝包**（多數使用者）。先看倉庫根目錄有沒有 `安裝清單.json` 判斷是哪一條

## 絕對禁止清單

**在 `update_guard.py snapshot` 成功之前，下列命令一律不得執行**——
即使使用者說「沒關係你弄」，即使 `git pull` 因為本機改動而失敗，
即使你判斷那些改動「看起來不重要」：

| 命令 | 它會毀掉什麼 |
|------|------|
| `git reset --hard` | 工作目錄裡所有未提交的改動，**永久消失**（從未進 object database，reflog 也救不回） |
| `git checkout -- .`／`git checkout .`／`git checkout -f` | 同上 |
| `git restore <路徑>` | 同上 |
| `git clean -fd`／`-fdx` | 未追蹤的檔案——**包含 `input/{案件}/` 這種使用者唯一一份的原始圖面** |
| `git stash`（沒有立刻 pop 並驗證） | 改動被藏起來，而 AI 常忘了拿回來 |
| `git pull --force`／`git pull -X theirs` | 靜默用上游版本蓋掉本機版本 |
| 刪掉資料夾重新 clone／重新下載 | 全部 |

Claude Code 有 `PreToolUse` hook（`tools/guard_hook.py`）會擋下這些命令。
**擋下來不是要你換個寫法繞過去**，是要你回到本檔的程序。
其他 AI 工具沒有這道關卡，紀律就是唯一的防線。

真的必須執行時（使用者已備份且明確要求），**請他自己在終端機打**，不要由你代跑。

## 線1（git clone）的安全更新程序

```bash
# 1. 先看有什麼會被影響（唯讀，可直接跑）
python3 tools/update_guard.py check

# 2. 備份（寫入，先說明並取得同意）——寫到倉庫外，更新與重裝都動不到
python3 tools/update_guard.py snapshot --note "更新前"

# 3. 把本機成果送進 git object database（寫入，先取得同意）
#    這一步把「不可逆」變成「reflog 可逆」，成本極低
python3 tools/update_guard.py commit --by "{使用者名字}"

# 4. 只做快轉合併。有衝突就停下來報告，不得自行解決
git pull --ff-only

# 5. 確認狀態，並驗證規則庫沒被換壞
python3 tools/update_guard.py check
python3 tools/fire_code_calc.py self-test
python3 tools/fire_code_calc.py run-tests --strict
python3 tools/onboarding.py status
```

第 4 步失敗時**就到此為止**。把 git 的訊息原文給使用者看，說明「上游和你的本機
改動動到了同一個地方，需要逐項確認」，然後走下面的衝突處理。**不要**為了讓
`git pull` 成功而動用禁止清單裡的任何一條。

## 線2（安裝包）的更新程序

倉庫根目錄有 `安裝清單.json` 就是這一條。**這條路徑沒有 git，也就沒有 git 的風險。**

1. `python3 tools/update_guard.py check` 看現況
2. 請使用者到 GitHub Releases 下載新版 `FireReview-{版本}-setup.exe`
3. **裝到同一個資料夾**（安裝程式會自己認出是升級）
4. 安裝程式會：先備份到資料夾外面 → 沒改過的檔案直接更新 →
   **改過的檔案保住原檔、上游新版另存 `.上游新版`** → 使用者新增的完全不動
5. 讀安裝目錄下的 `更新報告-{日期}.txt`，逐項陪使用者處理 `.上游新版` 檔案

安裝程式是**自解壓縮檔**：酬載先解到 `%TEMP%`，再由 `tools/installer.py` 逐檔判定。
**在判定跑起來之前，使用者的資料夾一個位元組都沒被碰過**——所以中途取消、
Python 缺席、下載失敗，都不會留下半套狀態。這點可以直接講給不安的使用者聽。

Windows 會對未簽章的 exe 跳「已保護您的電腦」——那不是病毒，
點「其他資訊」→「仍要執行」。**若防毒軟體直接把它擋掉或刪掉**（自解壓縮檔常被
視為可疑格式，企業電腦尤其明顯），改用 zip 版，內容完全相同。

沒有安裝程式可用時（例如使用者在 macOS／Linux 上解 zip），手動走同一套邏輯：

```bash
python3 tools/update_guard.py install --from {新版解壓目錄} --dry-run   # 先看處置計畫
python3 tools/update_guard.py install --from {新版解壓目錄}
```

## 衝突處理

**`rules/*.json`、`graphify-out/graph.json` 是共編檔**——使用者的裁示與上游的修法
交錯在同一個檔案裡。這類衝突不能一鍵解決：

（`training/graph.json` **不是**共編檔：它是使用者所有的衍生產物，也不進版控。
真的出問題就 `python3 tools/training_graph_build.py build` 從素材重建，不必還原。）

- **不得**用 `--ours`／`--theirs`／`-X` 任何一種自動解法
- 正確做法：`python3 tools/update_guard.py diff` 列出差異 → 把「上游改了什麼、
  你的版本是什麼」逐項講給使用者聽 → 依 `skills/red-green.md` 重跑先紅再綠，
  或依 `skills/onboarding.md` 第二步逐則裁示
- 使用者的裁示紀錄（`governance/`）、實務見解（`practice_notes/`）、
  案件圖面（`input/`）是他獨佔的，不會與上游衝突，直接保留他的版本

## 救援程序（`check` 回 `suspected_loss` 或 `foreign_backup`）

`suspected_loss` 代表：備份裡記得是使用者版本的檔案，現在不見了、
或內容變回上游原樣。**此時 `git status` 通常是乾淨的**——不要因為它乾淨就以為沒事。

```bash
# 0. 先不要再跑任何 git 命令
# 1. 先把現況也備份起來（現況可能有比舊備份更新的東西）
python3 tools/update_guard.py snapshot --note "救援前現況"

# 2. 逐檔看差異，把結果講給使用者聽
python3 tools/update_guard.py diff

# 3. 逐項確認後還原（預設只預演，加 --apply 才寫入）
python3 tools/update_guard.py restore --path {路徑}
python3 tools/update_guard.py restore --path {路徑} --apply
```

三條紀律：

- **共編檔預設拒絕整檔還原**。`restore` 對 `rules/`、`graphify-out/` 會擋下來，
  因為拿舊備份整檔蓋回去會把上游的法規更新一起吃掉。要的是列差異、
  請使用者重新裁示，不是 `--force-shared`
- **`graphify-out/node_ledger.json` 必須與 `graph.json` 同版本**。台帳記錄
  `(source_file, label) → node id`；只還原其中一個會讓訓練圖譜的跨圖譜參照掛不回法規，
  查圖譜就查不到訓練成果。要還原就兩個一起，或直接重跑
  `python3 tools/regulation_graph_build.py rebuild --commit`
- **一次一項，逐項確認**。不要 `--all --apply` 一把梭
- **不得代替使用者決定要不要救回某個檔案**——那是他的成果，不是你的

`foreign_backup` 代表這個資料夾是全新的，但這台電腦有先前的成果備份
（通常是使用者重新下載或裝到了別的位置）。用 `list` 與 `diff` 給他看，
問他要不要把成果搬過來。

## 無解的邊界（必須誠實告訴使用者）

- **雲端沙盒救不了本機。** 你在 Claude Code web 這類一次性容器裡操作時，
  那是每次全新 clone 的環境，使用者本機的成果與備份都不在那裡。
  **不要在雲端沙盒對使用者的本機成果做更新操作**——你動不到，也救不回。
- **重新下載到另一個資料夾又改了名字，索引認不出來。** 家目錄索引以資料夾名認親。
  使用者說「我重灌過／換過電腦」時，主動問他舊資料夾在哪，用
  `update_guard.py diff --backup {路徑}` 手動指過去。
- **這道關卡只擋直球。** `bash -c "..."` 這種包一層的寫法 hook 攔不到，
  不讀 `AGENTS.md` 的工具也不會知道有這些規則。所以備份才是最後一道防線，
  而不是第一道。

## 完成契約

- 更新之前一定跑過 `snapshot`，而且使用者知道備份在哪（絕對路徑講給他聽）
- 禁止清單裡的命令，一條都沒有由你執行過
- 更新之後 `self-test` 與 `run-tests --strict` 全綠，`check` 不是 `suspected_loss`
- 使用者知道有哪些檔案保留了他的版本、上游新版在哪、下一步要做什麼
- 任何「要不要採用上游新版」的決定都出自使用者本人

## 常見錯誤

- **「先 `git checkout` 清乾淨再 pull」**——這是本檔存在的唯一理由。清掉的是他數月的成果。
- **以為 `git status` 乾淨就代表沒事**——成果被還原成上游版本之後，工作目錄正是乾淨的。
- **被 hook 擋下來就換個寫法再試一次**——擋下來是要你回到程序，不是要你繞過去。
- **用 `--ours`／`--theirs` 解 `rules/*.json` 的衝突**——不是把使用者的裁示丟掉，
  就是把上游的修法丟掉，而且兩種都不會有人發現。
- **`restore --all --apply` 一把梭**——救援本身就是覆蓋，現況可能比備份新。
- **在雲端沙盒假裝自己在幫他更新本機**——你動不到他的電腦，講清楚比裝作有用更重要。
- **代替使用者決定要不要採用上游的新法規值**——那是法規判斷，歸他。

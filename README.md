# Fire Review — 消防審圖輔助系統

把 **DXF 平面圖 ＋ 審查文件**交給 AI，依《各類場所消防安全設備設置標準》算出應設設備、
列出缺失，並把問題直接圈在圖上。

> **輔助，不取代。** 每一項「應設／免設／缺失」都附法條條號供覆核；資料不足以判定的一律
> 標「需人工判讀」。最終審查判斷與法律責任歸屬專業消防人員。

```text
input/{案件名}/  平面圖.dxf ＋ 審查文件（申請書、審查表、使用執照…）
        │
        ▼   AI 萃取 →【人工確認】→ 工具依法規計算（禁止心算）
output/
  ① {案件名}-圖面審查.html                  缺失圈在圖上，可點選導覽
  ② {案件名}-問題清單.md                    缺失分級＋違反法條
  ③ {案件名}-法條檢核清單.html              §14~§31 逐條打勾
  ④ {案件名}-複合用途及樓層屬性檢討.html    主從用途與樓層屬性
```

---

## 三個入口，挑你自己的那一個

| 你是 | 讀這份 | 大概是什麼 |
|------|--------|-----------|
| **消防專業人員**（不必懂程式、不必碰 git） | **[docs/使用手冊.md](docs/使用手冊.md)** | 下載安裝 → 把圖丟進 `input/` → 跟你的 AI 說要審哪個案件 → 到 `output/` 收交付物 |
| **技術人員／要改架構、送 PR** | **[docs/架構.md](docs/架構.md)** ＋ [CONTRIBUTING.md](CONTRIBUTING.md) | 零安裝 stdlib 工具層、`case.json` 正典、規則庫先紅再綠、四項交付物的產生鏈 |
| **AI 代理**（Claude Code／Codex／OpenCode…） | **[AGENTS.md](AGENTS.md)**（行為契約正本）→ [docs/AI-作業流程.md](docs/AI-作業流程.md) | 開場先跑 `onboarding.py status`，再依路由載入 `skills/*.md`；半自動化關卡與命令速查 |

進度與待補清單見 [docs/路線圖.md](docs/路線圖.md)。

---

## 30 秒上手

```bash
python3 tools/onboarding.py status   # 載入倉庫後的第一件事：診斷 ＋ 列出待處理步驟
python3 tools/onboarding.py intro    # 只想看操作簡介的話
```

接著跟你的 AI 說 **「照 `skills/onboarding.md` 帶我開始」**，它會依序帶你走完
本機成果保護 → 待確認事項裁示 → 法規圖譜 → 環境工具 → 規則庫健康 → 操作簡介。

不想碰終端機？到 [Releases](https://github.com/Vik1n9/drawing_review/releases) 下載
`FireReview-{版本}-setup.exe`，裝完照資料夾裡的
「安裝完成-請把這段貼給你的AI.txt」把那段話貼給 AI 就好——細節見
[docs/使用手冊.md](docs/使用手冊.md)。

> **預設什麼都不用安裝。** 法規計算、DXF 圖面標註、PDF／DOCX／XLSX 判讀全部只用
> Python 標準庫。唯一無法迴避的前置是 Python 本身。
>
> **你的審圖成果只存在你這台電腦**——規則裁示、實務見解、案件圖面、交付物都沒有上傳到
> 任何地方，所以**更新方式錯了就救不回來**。更新前先跑
> `python3 tools/update_guard.py check`。

---

<!-- PENDING-REVIEW:BEGIN -->
### ⚠️ 有 14 則待確認事項——請先處理再開始審圖

規則參數與現行條文（各類場所消防安全設備設置標準 民國 113 年 04 月 24 日修正）比對出 14 則差異，其中 14 則尚未裁示。受影響的規則：`18-8`、`18-9`、`detector-coverage`、`emergency-light-threshold`、`exit-light-threshold`、`extinguisher-count`、`extinguisher-threshold`、`fire-alarm-threshold`、`indoor-hydrant-coverage`、`indoor-hydrant-threshold`、`smoke-exhaust-threshold`、`sprinkler-head-spacing`、`sprinkler-threshold`、`subordinate-table`。

完整內容見 **[`待確認事項.md`](待確認事項.md)**。

```bash
python3 tools/pending_review.py status   # 開場檢查（有待確認事項會回結束碼 2）
python3 tools/pending_review.py list     # 逐則列出，交給具消防專業的使用者裁示
python3 tools/pending_review.py apply --all --by "○○○（消防設備師）"
```

裁示完成後 `apply` 會自動走先紅再綠更正參數、回填 `verified`、更新本區塊並移除疑義檔。在此之前，這些規則的輸出一律附「本參數尚未逐條確認」警語。
<!-- PENDING-REVIEW:END -->

---

## 文件地圖

| 檔案 | 給誰 | 內容 |
|------|------|------|
| `docs/使用手冊.md` | 使用者 | 取得、上手、審一個案件、更新備份、疑難排解 |
| `docs/架構.md` | 技術人員 | 資料流、目錄結構、核心設計決策、工具層、資料介面 |
| `docs/AI-作業流程.md` | AI 代理 | 開場程序、skill 路由、人工關卡、命令速查 |
| `docs/路線圖.md` | 兩者 | 建置階段狀態、待補文件與待辦 |
| `AGENTS.md` | AI 代理 | 行為契約**正本**（六條底線＋路由），跨 AI 工具共用 |
| `CLAUDE.md` | Claude Code | 只是指向 `AGENTS.md` 的指標 |
| `CONTRIBUTING.md` | 貢獻者 | 角色分工、發佈路線、變更規範、品質底線 |
| `skills/README.md` | 技術人員 | 兩階段審查工作流程的設計說明 |

---

## 免責聲明

本專案為審圖輔助工具研究，內建法規參數為開發示例。未經主管機關或消防專業人員核定前，
不得作為正式審查依據；實際審查以現行法規條文、主管機關解釋與專業消防人員判斷為準。

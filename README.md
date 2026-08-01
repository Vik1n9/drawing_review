# Fire Review — 消防審圖輔助系統

把 DXF 平面圖和審查文件交給 AI，依《各類場所消防安全設備設置標準》算出應設設備、列出缺失，
再把問題直接圈在圖上。

> 這只是輔助工具，不能替代審圖工作。每一項「應設／免設／缺失」都附法條條號讓你覆核，資料不夠判定的
> 就標「需人工判讀」，不會硬給答案。最終的審查判斷和法律責任還是在消防專業人員身上。

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
| 消防專業人員 | [docs/使用手冊.md](docs/使用手冊.md) | 下載安裝 → 把圖丟進 `input/` → 跟你的 AI 說要審哪個案件 → 到 `output/` 收交付物 |
| 技術人員，或想改架構、送 PR 的人 | [docs/架構.md](docs/架構.md) ＋ [CONTRIBUTING.md](CONTRIBUTING.md) | 零安裝的 stdlib 工具層、`case.json` 正典、規則庫先紅再綠、四項交付物怎麼生出來 |
| AI 代理（Claude Code／Codex／OpenCode…） | [AGENTS.md](AGENTS.md)（行為契約正本）→ [docs/AI-作業流程.md](docs/AI-作業流程.md) | 開場先跑 `onboarding.py status`，再依路由載入 `skills/*.md`，另附半自動化關卡與命令速查 |

進度與待補清單放在 [docs/路線圖.md](docs/路線圖.md)。

---

## 先跑這兩行

```bash
python3 tools/onboarding.py status   # 載入倉庫後的第一件事：診斷 ＋ 列出待處理步驟
python3 tools/onboarding.py intro    # 只想看操作簡介的話
```

接著跟你的 AI 說「照 `skills/onboarding.md` 帶我開始」，它會依序帶你走完本機成果保護、
待確認事項裁示、法規圖譜、環境工具、規則庫健康，最後是操作簡介。

不想碰終端機？到 [Releases](https://github.com/Vik1n9/drawing_review/releases) 下載
`FireReview-{版本}-setup.exe`，裝完打開資料夾裡的「安裝完成-請把這段貼給你的AI.txt」，
把那段話貼給 AI 就好。細節在 [docs/使用手冊.md](docs/使用手冊.md)。

> 預設什麼都不用裝。法規計算、DXF 圖面標註、PDF／DOCX／XLSX 判讀全部只用 Python 標準庫，
> 唯一躲不掉的前置是 Python 本身。
>
> 另外提醒一件事：你的審圖成果只存在你這台電腦。規則裁示、實務見解、案件圖面、交付物都沒有
> 上傳到任何地方，所以更新方式一旦弄錯就救不回來。更新前先跑
> `python3 tools/update_guard.py check`。

---

<!-- PENDING-REVIEW:BEGIN -->
### ✅ 目前沒有待確認事項

規則參數與現行條文的比對差異都已裁示完畢。本區塊由 `python3 tools/pending_review.py render` 自動維護。
<!-- PENDING-REVIEW:END -->

---

## 文件地圖

| 檔案 | 給誰 | 內容 |
|------|------|------|
| `docs/使用手冊.md` | 使用者 | 取得、上手、審一個案件、更新備份、疑難排解 |
| `docs/架構.md` | 技術人員 | 資料流、目錄結構、核心設計決策、工具層、資料介面 |
| `docs/AI-作業流程.md` | AI 代理 | 開場程序、skill 路由、人工關卡、命令速查 |
| `docs/路線圖.md` | 兩者 | 建置階段狀態、待補文件與待辦 |
| `AGENTS.md` | AI 代理 | 行為契約的正本（六條底線＋路由），跨 AI 工具共用 |
| `CLAUDE.md` | Claude Code | 只是指向 `AGENTS.md` 的指標 |
| `QWEN.md` | Qwen Code | 只是指向 `AGENTS.md` 的指標 |
| `CONTRIBUTING.md` | 貢獻者 | 角色分工、發佈路線、變更規範、品質底線 |
| `skills/README.md` | 技術人員 | 兩階段審查工作流程的設計說明 |

---

## 免責聲明

本專案是審圖輔助工具的研究，內建的法規參數只是開發示例。未經主管機關或消防專業人員核定前，
不得作為正式審查依據；實際審查仍以現行法規條文、主管機關解釋與專業消防人員的判斷為準。

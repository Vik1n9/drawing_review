#!/usr/bin/env python3
"""Fire Review 開場導引：載入倉庫後的半自動狀態診斷與引導。

本倉庫的使用者是消防專業人員，自行把倉庫導入自己電腦上的 AI 工具
（Claude Code／Codex／OpenCode …皆可）獨立作業，不一定熟悉 AI 與終端機。
本工具把散在各處的前置檢查聚合成一份有序清單，讓 AI 能照著逐步引導：

    python3 tools/onboarding.py status          # 開場診斷（結束碼 2 ＝ 有待處理步驟）
    python3 tools/onboarding.py status --format json
    python3 tools/onboarding.py intro           # 操作簡介（印在終端機）

三個設計約束：

1. **只用標準庫**——任何能執行 shell 的 AI 工具都跑得起來，不必先安裝什麼。
2. **工具中立**——斜線指令（`/gap-analysis` 之類）只有 Claude Code 有，所以每個
   步驟一律同時給「可複製的 python 命令」與「一句自然語言請求」（`say` 欄位），
   命令裡的解譯器照 `interpreter` 改寫（Windows 常只有 `python` 而無 `python3`）。
3. **唯讀自動、寫入先問**——本工具自己只讀不寫；輸出中每條命令都標明 `讀`／`寫`，
   標 `寫` 者 AI 必須先向使用者說明並取得同意才能執行。

本工具**不做任何法規判斷**（審圖最高原則 2／4／5），只做狀態診斷與流程引導。
行為契約見 `skills/onboarding.md`。
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import check_env  # noqa: E402
from tools import graph_status  # noqa: E402
from tools import pending_review as pr  # noqa: E402
from tools import training_intake  # noqa: E402

EXIT_OK, EXIT_PENDING = 0, 2

READ, WRITE = "讀", "寫"

# 步驟狀態：ready 就緒／action 待處理／blocked 卡住須先解決／info 純資訊不計入關卡
MARKS = {"ready": "✅", "action": "⚪", "blocked": "⛔", "info": "📘"}
BLOCKING = ("action", "blocked")

STEP_TOTAL = 5

CALC = "tools/fire_code_calc.py"


def command(cmd, kind=READ, optional=False):
    return {"cmd": cmd, "kind": kind, "optional": optional}


def step(title, state, why, lines, commands, say):
    """一個導引步驟。`no` 由 evaluate() 依實際順序填入，builder 不自己編號。"""
    return {"no": None, "title": title, "state": state, "why": why,
            "lines": lines, "commands": commands, "say": say}


# ---------------------------------------------------------------------------
# 第一步：環境工具
# ---------------------------------------------------------------------------

def step_environment(env):
    py = env["interpreter"]
    lines = [f"Python {env['python_version']}（你的命令請用 {py}）",
             "核心計算與法規查詢只用標準庫，什麼都不裝也能跑"]
    commands = []

    if env["missing"]:
        for dep in env["deps"]:
            if not dep["ok"]:
                lines.append(f"缺 {dep['package']} —— {dep['use']}")
        if env["has_bash"]:
            commands.append(command("bash tools/setup.sh", WRITE))
        else:
            lines.append("這台電腦沒有 bash（Windows 常見），改用 pip 直接安裝")
            commands.append(
                command(f"{py} -m pip install -r requirements.txt", WRITE))
        state = "action"
    else:
        lines.append("三個交付物套件（ezdxf／openpyxl／pymupdf）都已就緒")
        state = "ready"

    return step(
        "環境工具", state,
        "缺套件時只影響對應的交付物（DXF 標註、xlsx、PDF），法規計算不受影響",
        lines, commands,
        "跟你的 AI 說：幫我把缺的套件裝起來",
    )


# ---------------------------------------------------------------------------
# 第二步：待確認事項裁示
# ---------------------------------------------------------------------------

def step_pending(env):
    py = env["interpreter"]
    path, doc = pr.load_sheet(None)

    if path is None:
        return step(
            "待確認事項裁示", "ready",
            "規則參數與現行條文比對出的差異，必須由你（消防專業人員）逐則裁示",
            ["沒有待確認事項——governance/待確認清單/ 沒有疑義檔"],
            [], "",
        )

    open_findings = pr.open_findings(doc)

    if not open_findings:
        return step(
            "待確認事項裁示", "action",
            "疑義檔內所有事項都已裁示，只剩收尾動作",
            [f"疑義檔 {path} 已全部裁示，跑 render 即可移除疑義檔"],
            [command(f"{py} tools/pending_review.py render", WRITE)],
            "跟你的 AI 說：待確認事項我都裁示完了，幫我收尾",
        )

    undecided = [f for f in open_findings if not f.get("decision")]
    decided = len(open_findings) - len(undecided)
    rules = sorted({f.get("rule_id", "?") for f in open_findings})
    # 十幾個規則 ID 擠成一行沒人看得完，列前三個就夠定位
    shown = "、".join(rules[:3])
    if len(rules) > 3:
        shown += f" 等 {len(rules)} 條規則"

    lines = [f"有 {len(open_findings)} 則待確認（{path}）",
             f"其中 {len(undecided)} 則尚未裁示、{decided} 則已裁示待執行",
             f"影響：{shown}",
             "未裁示前照常審圖是允許的，但這些規則的輸出必須附「本參數尚未逐條確認」警語"]

    commands = [command(f"{py} tools/pending_review.py list", READ)]
    if undecided:
        commands.append(command(
            f'{py} tools/pending_review.py decide --id {{ID}} '
            f'--decision {{採納更正|維持現值|另有更正}} --by "{{你的名字}}"', WRITE))
    commands.append(command(
        f'{py} tools/pending_review.py apply --all --by "{{你的名字}}"', WRITE))

    return step(
        "待確認事項裁示", "action",
        "AI 不得代替你裁示；apply 內建先紅再綠關卡，測試沒紅即整批回滾",
        lines, commands,
        "跟你的 AI 說：把待確認事項一則一則列給我看，我逐則裁示",
    )


# ---------------------------------------------------------------------------
# 第三步：法規圖譜
# ---------------------------------------------------------------------------

def step_graph(env):
    py = env["interpreter"]
    graph = graph_status.evaluate(".")
    state_name = graph["state"]

    lines = ["查詢現在就能用——graph.json 已在倉庫內，"
             "regulation_graph.py 只用標準庫，不必安裝任何東西"]
    commands = [command(
        f"{py} tools/regulation_graph.py neighbors --article §24", READ)]

    if env["graphify"]:
        lines.append("graphify 已安裝，可重建圖譜")
    else:
        lines.append("graphify 未安裝——只查詢法規的話不用裝；"
                     "要重建圖譜（改了法規全文）才需要")
        install = ("bash tools/setup.sh --with-graph" if env["has_bash"]
                   else f"{py} -m pip install graphifyy")
        commands.append(command(install, WRITE, optional=True))

    if state_name == "fresh":
        lines.append(f"新鮮度：圖譜與 {graph['source_count']} 個來源檔一致"
                     f"（蓋章時間：{graph.get('stamped_at') or '—'}）")
        step_state = "ready"
    elif state_name == "no_baseline":
        lines.append("新鮮度：尚未建立基準——圖譜沒蓋章過，先重建再蓋章")
        step_state = "blocked"
    else:
        diff = graph.get("diff") or {}
        changed = sum(len(diff.get(k, [])) for k in ("added", "removed", "changed"))
        lines.append(f"新鮮度：{state_name}——來源檔有 {changed} 處異動未反映到圖譜，"
                     "此時查到的關聯可能不是最新的")
        lines.append(graph_status.REBUILD_HINT)
        step_state = "blocked"

    return step(
        "法規圖譜", step_state,
        "圖譜只是索引與導覽，用來定位條號與關聯；門檻數值與計算一律回法條原文與 "
        "fire_code_calc.py，不得引用圖譜節點標題當法規數值",
        lines, commands,
        "跟你的 AI 說：幫我查第 24 條牽涉哪些條文和設備",
    )


# ---------------------------------------------------------------------------
# 第四步：規則庫健康
# ---------------------------------------------------------------------------

def run_calc(args, timeout=90):
    """跑 fire_code_calc 子命令，回傳 (ok, 尾部輸出)。只讀不寫。"""
    try:
        proc = subprocess.run(
            [sys.executable, CALC, *args],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"逾時（{timeout} 秒）未跑完"
    except OSError as exc:
        return False, f"無法執行：{exc}"
    if proc.returncode == 0:
        return True, ""
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    return False, "；".join(tail[-3:]) if tail else f"結束碼 {proc.returncode}"


def training_snapshot():
    """training_intake.status() 的容錯包裝（最小倉庫可能缺 training/）。"""
    try:
        return training_intake.status(".")
    except Exception:  # noqa: BLE001 — 診斷工具不該因為附屬資訊掛掉
        return {}


def step_rules(env):
    py = env["interpreter"]
    lines, commands = [], []
    ok = True

    for args, label in (
        (["self-test"], "引擎與規則庫自檢"),
        (["run-tests", "--strict"], "規則測試（先紅再綠）"),
    ):
        passed, detail = run_calc(args)
        if passed:
            lines.append(f"{label}：通過")
        else:
            ok = False
            lines.append(f"{label}：**失敗** —— {detail}")
            commands.append(command(f"{py} {CALC} {' '.join(args)}", READ))

    snap = training_snapshot()
    unverified = snap.get("unverified_rules")
    if unverified:
        lines.append(f"規則庫還有 {unverified} 條尚未逐條確認——"
                     "這些規則的輸出必須附「本參數尚未逐條確認」警語")
        commands.append(command(f"{py} tools/verification_sheet.py list", READ))
    notes = snap.get("practice_notes_active")
    if notes:
        lines.append(f"實務註解：{notes} 則生效中（實務見解，非法規條文）")
    if snap.get("practice_notes_staging"):
        lines.append(f"實務註解另有 {snap['practice_notes_staging']} 則草擬中，"
                     "未經你「確認納入」不會生效")

    return step(
        "規則庫健康", "ready" if ok else "blocked",
        "規則測試沒全綠的規則庫不得用來交付審圖結果",
        lines, commands,
        "跟你的 AI 說：幫我跑一次規則測試看有沒有問題",
    )


# ---------------------------------------------------------------------------
# 第五步：操作簡介
# ---------------------------------------------------------------------------

def step_intro(env):
    py = env["interpreter"]
    return step(
        "操作簡介", "info",
        "第一次使用先看這份——講清楚你要做什麼、產出會是什麼",
        ["把圖面放進 input/ → 跟你的 AI 說要審哪個案件 → 到 output/ 收交付物"],
        [command(f"{py} tools/onboarding.py intro", READ)],
        "跟你的 AI 說：把操作簡介印出來給我看",
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def evaluate():
    """五個步驟的診斷結果。

    順序刻意是「先裁示疑義表 → 再確認圖譜 → 再補環境套件 → 規則庫健檢 → 操作簡介」：
    疑義表裁示與圖譜查詢都只用標準庫，不必等套件裝完；而疑義表未裁示會影響
    所有受影響規則的結論可信度，所以排在最前面。
    """
    env = check_env.probe()
    builders = (step_pending, step_graph, step_environment, step_rules, step_intro)
    steps = []
    for no, build in enumerate(builders, start=1):
        s = build(env)
        s["no"] = no
        steps.append(s)
    outstanding = [s for s in steps if s["state"] in BLOCKING]
    return {
        "ready": not outstanding,
        "interpreter": env["interpreter"],
        "has_bash": env["has_bash"],
        "outstanding": [s["no"] for s in outstanding],
        "steps": steps,
    }


def format_status(result):
    py = result["interpreter"]
    out = ["== Fire Review 開場導引 =="]

    if result["ready"]:
        out.append("✅ 全部就緒（環境套件、待確認事項、法規圖譜、規則庫皆通過）"
                   "——可以開始審圖了。")
        out.append(f"→ 第一次使用請先看操作簡介：{py} tools/onboarding.py intro")
        return "\n".join(out)

    out.append("消防審圖輔助系統｜照下面的順序處理即可（詳細流程見 skills/onboarding.md）")
    out.append("")

    for s in result["steps"]:
        out.append(f"［{s['no']}/{STEP_TOTAL}］{MARKS[s['state']]} {s['title']}")
        for line in s["lines"]:
            out.append(f"     · {line}")
        for c in s["commands"]:
            tag = "唯讀，可直接跑" if c["kind"] == READ else "寫入，需你同意"
            if c["optional"]:
                tag = f"選用，{tag}"
            out.append(f"     → {c['cmd']}（{tag}）")
        if s["say"] and s["state"] in BLOCKING:
            out.append(f"     💬 {s['say']}")

    out.append("")
    out.append(f"⚪ 還有 {len(result['outstanding'])} 個步驟待處理"
               f"（第 {'、'.join(str(n) for n in result['outstanding'])} 步）"
               "——處理完重跑本命令即可確認。")
    out.append("→ AI 請依 skills/onboarding.md 逐步引導：唯讀命令可直接跑，"
               "標「寫入」的先說明並取得同意；不得代替使用者裁示法規事項。")
    return "\n".join(out)


def cmd_status(args):
    result = evaluate()
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_status(result))
    return EXIT_OK if result["ready"] else EXIT_PENDING


# ---------------------------------------------------------------------------
# intro
# ---------------------------------------------------------------------------

def format_intro(py):
    return f"""== Fire Review 操作簡介 ==

【這是什麼】
  消防審圖的輔助系統：讀你的 DXF 圖面與審查依據文件，依法規算出應設設備、
  列出缺失與數量，並把問題標在圖上。
  **輔助，不取代**——每一項結論都附法條條號給你覆核，最終判斷歸你。

【你要做的三件事】
  1. 把 DXF 圖面與審查依據文件放進 input/{{案件名}}/drawings/
  2. 用中文直接跟你的 AI 說：「幫我審 {{案件名}} 這個案件」
  3. 到 output/ 收交付物

【會拿到什麼】四項固定交付物
  · {{案件名}}-圖面審查.html —— 圖面轉成網頁，缺失位置直接圈在圖上，可點選導覽
  · {{案件名}}-問題清單.md —— 缺失逐項詳列違反法條、應設要求、圖面現況、缺口
  · {{案件名}}-法條檢核清單.html —— §14~§31 逐條打勾表，條號可點進法條原文
  · {{案件名}}-複合用途及樓層屬性檢討.html —— 主從用途與各層樓層屬性檢討表

  另有一條兩階段 Excel 路線（複合用途及樓層屬性檢討 → 設置標準檢討），
  流程見 skills/first-stage-review.md 與 skills/stage-two-review.md。
  跟 AI 說「走兩階段 Excel 流程」即可。

【三條你必須知道的底線】
  · input/ 只讀不改——原始圖面與法規文件不會被動到，產出一律寫進 output/
  · 缺失固定分四級：重大缺失／一般缺失／配置疑義／需人工判讀
    （另有「建議事項」，代表沒有強制法源，會標明）
  · 標「需人工判讀」的項目系統不會替你猜——需要大樣圖或現場才能確認的
    （防火區劃、排煙開口、夾層面積…），一律留給你判斷

【想查法規時】
  直接說「查第 24 條」或「排煙設備規定在哪幾條」，
  AI 會先用法規圖譜定位條號與關聯，再調出條文原文核對。

【卡住怎麼辦】
  直接問你的 AI；或重跑下面這行看還缺什麼：
    {py} tools/onboarding.py status

  完整導引流程見 skills/onboarding.md，審圖行為契約見 AGENTS.md。
  （用 Claude Code 的話，各流程另可用 /gap-analysis 這類斜線指令直接叫；
    其他 AI 工具用自然語言說明即可，效果相同。）"""


def cmd_intro(args):
    print(format_intro(check_env.interpreter_command()))
    return EXIT_OK


# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Fire Review 開場導引：載入倉庫後的半自動狀態診斷與引導")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_status = sub.add_parser("status", help="開場診斷（結束碼 2 ＝ 有待處理步驟）")
    p_status.add_argument("--format", choices=("text", "json"), default="text")
    p_status.set_defaults(func=cmd_status)

    p_intro = sub.add_parser("intro", help="印出操作簡介")
    p_intro.set_defaults(func=cmd_intro)

    for p in (p_status, p_intro):
        p.add_argument("--root", default=".", help="倉庫根目錄（預設為現在的目錄）")

    args = parser.parse_args(argv)
    os.chdir(args.root)
    return args.func(args) or EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

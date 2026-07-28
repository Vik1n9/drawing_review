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
from tools import update_guard  # noqa: E402

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

EXIT_OK, EXIT_PENDING = 0, 2

READ, WRITE = "讀", "寫"

# 步驟狀態：ready 就緒／action 待處理／blocked 卡住須先解決／info 純資訊不計入關卡
MARKS = {"ready": "✅", "action": "⚪", "blocked": "⛔", "info": "📘"}
BLOCKING = ("action", "blocked")

STEP_TOTAL = 6

CALC = "tools/fire_code_calc.py"


def command(cmd, kind=READ, optional=False):
    return {"cmd": cmd, "kind": kind, "optional": optional}


def step(title, state, why, lines, commands, say):
    """一個導引步驟。`no` 由 evaluate() 依實際順序填入，builder 不自己編號。"""
    return {"no": None, "title": title, "state": state, "why": why,
            "lines": lines, "commands": commands, "say": say}


# ---------------------------------------------------------------------------
# 第一步：本機成果保護
# ---------------------------------------------------------------------------

def guard_snapshot():
    """update_guard.evaluate() 的容錯包裝。

    家目錄不可寫、git 壞掉、倉庫結構沒見過——任何一種都不該讓整份開場診斷掛掉。
    診斷工具自己壞掉而讓使用者連狀態都看不到，比漏報一個步驟更糟。
    """
    try:
        return update_guard.evaluate(".")
    except Exception:  # noqa: BLE001 — 診斷工具不該因為附屬資訊掛掉
        return None


def step_local_data(env):
    """排在最前面：資料被蓋掉不可逆，優先於任何其他待處理事項。

    疑義表沒裁示、圖譜過期、套件沒裝，事後都補得回來；
    使用者的訓練成果被 `git checkout -- .` 蓋掉則救不回來（除非有備份）。
    不可逆的事項排在可逆的前面。
    """
    py = env["interpreter"]
    result = guard_snapshot()

    if result is None:
        return step(
            "本機成果保護", "ready",
            "更新倉庫前先確認你的訓練成果不會被蓋掉",
            ["守門工具跑不起來——不影響審圖，但更新倉庫前請先手動備份整個資料夾"],
            [command(f"{py} tools/update_guard.py check", READ)],
            "",
        )

    state = update_guard.STEP_STATES[result["state"]]
    lines = update_guard.format_check(result).splitlines()

    commands = [command(f"{py} tools/update_guard.py check", READ)]
    if state != "ready":
        commands.append(command(
            f'{py} tools/update_guard.py snapshot --note "更新前"', WRITE))
    if result["state"] == "suspected_loss":
        commands.append(command(f"{py} tools/update_guard.py diff", READ))
        commands.append(command(
            f"{py} tools/update_guard.py restore --path {{路徑}} --apply", WRITE))

    say = ""
    if result["state"] == "suspected_loss":
        say = "跟你的 AI 說：我的成果好像被蓋掉了，幫我看 diff 再逐項救回來"
    elif state != "ready":
        say = "跟你的 AI 說：更新倉庫之前先幫我把本機成果備份起來"

    return step(
        "本機成果保護", state,
        "你的訓練成果只存在這台電腦，被覆蓋掉不可逆——"
        "更新倉庫前一律先備份，且不得執行任何會還原或清除工作目錄的 git 操作",
        lines, commands, say,
    )


# ---------------------------------------------------------------------------
# 第二步：環境工具
# ---------------------------------------------------------------------------

def step_environment(env):
    """回報「現在能做什麼」，不是「缺哪些套件」。

    使用者多半只裝了一個 AI 桌面版就開始用，沙盒讓 pip 裝不起來。
    對這種人列一串裝不上的套件只會製造焦慮——所以本步驟永遠是 ready，
    每個做不到的能力都直接給替代路徑（替代路徑的存在由 check_env
    的能力矩陣保證，見 tests/test_check_env.py）。
    """
    py = env["interpreter"]
    capabilities = env.get("capabilities", [])
    blocked = [c for c in capabilities if not c["ok"]]

    lines = [f"Python {env['python_version']}（你的命令請用 {py}）",
             "本倉庫預設什麼都不必安裝——法規計算、DXF 圖面標註、文件判讀都是零安裝"]

    for capability in capabilities:
        if capability["ok"]:
            note = f"（{capability['note']}）" if capability.get("note") else ""
            lines.append(f"可用：{capability['name']}{note}")
    for capability in blocked:
        lines.append(f"暫時做不到：{capability['name']}"
                     f"（需 {capability['requires']}）→ {capability['alternative']}")

    commands = []
    if env["missing"]:
        # 裝得起來的環境可以補齊，但這是加分項，不是門檻——
        # 標 optional 讓 AI 知道不必追著使用者裝。
        if env["has_bash"]:
            commands.append(command("bash tools/setup.sh", WRITE, optional=True))
        else:
            lines.append("這台電腦沒有 bash（Windows 常見），要裝的話改用 pip")
            commands.append(
                command(f"{py} -m pip install -r requirements.txt", WRITE, optional=True))

    return step(
        "環境工具", "ready",
        "零安裝就能跑審圖主線；少數交付物格式需要套件，但每項都有替代路徑",
        lines, commands,
        "",
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
    regulation = graph["regulation"]
    training = graph["training"]

    lines = ["兩個圖譜：法規圖譜（條文關聯）與訓練圖譜（你確認過的實務見解），"
             "審圖時會同時查；查詢只用標準庫，不必安裝任何東西"]
    commands = [command(
        f"{py} tools/regulation_graph.py neighbors --article §24", READ)]

    if regulation["state"] == "fresh":
        lines.append(f"法規圖譜：✅ 與 {regulation['source_count']} 個來源檔一致"
                     f"（蓋章時間：{regulation.get('stamped_at') or '—'}）")
        step_state = "ready"
    elif regulation["state"] == "no_baseline":
        lines.append("法規圖譜：⚠️ 尚未建立基準——沒蓋章過，先重建再蓋章")
        step_state = "blocked"
    else:
        diff = regulation.get("diff") or {}
        changed = sum(len(diff.get(k, [])) for k in ("added", "removed", "changed"))
        lines.append(f"法規圖譜：⛔ 來源檔有 {changed} 處異動未反映到圖譜，"
                     "此時查到的關聯可能不是最新的")
        lines.append(graph_status.REBUILD_HINT)
        step_state = "blocked"

    coverage = training["coverage"]
    if coverage["state"] == "covered":
        lines.append(f"訓練圖譜：✅ 實務註解 {coverage['active']} 則、"
                     f"markdown 筆記 {coverage['entries']} 則都查得到")
    elif coverage["state"] == "not_built":
        lines.append(f"訓練圖譜：尚未建置——倉庫已有 {coverage['entries']} 則審圖筆記與"
                     "判斷慣例，建起來審圖時就查得到")
        commands.append(command(f"{py} tools/training_graph_build.py build", WRITE,
                                optional=True))
    else:
        lines.append("訓練圖譜：⛔ 沒跟上素材——審圖查圖譜會查不到你的訓練成果")
        commands.append(command(f"{py} tools/training_graph_build.py build", WRITE))
        step_state = "blocked"

    # graphify 排在最後，而且是純加值：重建圖譜已不需要它。
    if not env["graphify"]:
        lines.append("graphify 未安裝——不影響查詢，也不影響重建（重建已內建於本倉庫、"
                     "只用標準庫）；它只用來重繪 graph.html 與提供 query/explain/path CLI")
        install = ("bash tools/setup.sh --with-graph" if env["has_bash"]
                   else f"{py} -m pip install graphifyy")
        commands.append(command(install, WRITE, optional=True))

    return step(
        "法規圖譜與訓練圖譜", step_state,
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
    """六個步驟的診斷結果。

    順序刻意是「先保住本機成果 → 再裁示疑義表 → 再確認圖譜 → 再補環境套件
    → 規則庫健檢 → 操作簡介」。

    本機成果保護排第一的理由是**可逆性**，不是重要性：疑義表沒裁示、圖譜過期、
    套件沒裝，事後都補得回來；訓練成果被覆蓋掉則救不回來。其餘順序沿用原設計——
    疑義表裁示與圖譜查詢都只用標準庫，不必等套件裝完，而疑義表未裁示會影響
    所有受影響規則的結論可信度。
    """
    env = check_env.probe()
    builders = (step_local_data, step_pending, step_graph, step_environment,
                step_rules, step_intro)
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
        out.append("✅ 全部就緒（本機成果、環境套件、待確認事項、法規圖譜、規則庫皆通過）"
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
  1. 把 DXF 圖面與審查依據文件放進 input/{{案件名}}/（多張圖可放 drawings/ 子資料夾）
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

【你的成果存在哪，以及怎麼保住它】
  你的裁示、實務見解、案件圖面與交付物都在這個資料夾裡，**只存在這台電腦**。
  更新到新版之前先備份一次（會寫到這個資料夾的外面，更新動不到）：
    {py} tools/update_guard.py check      # 看有什麼會被影響
    {py} tools/update_guard.py snapshot   # 備份
  **不要讓 AI 用 git 指令幫你「清乾淨再更新」**——那會把成果一次抹掉，
  而且救不回來。安全的更新程序見 skills/safe-update.md。

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

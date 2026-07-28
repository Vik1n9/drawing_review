#!/usr/bin/env python3
"""安裝與升級的唯一入口——由自解壓縮檔的「安裝.bat」呼叫，也可以自己跑。

只用 Python 標準庫。

    python tools/installer.py                        # 互動：問安裝位置
    python tools/installer.py --target D:\\FireReview --yes   # 非互動

## 為什麼安裝邏輯全部在 Python

前一版用 Inno Setup，逐檔判定寫在 220 行的 `.iss` 裡（其中 136 行 Pascal Script
完全沒有測試涵蓋，也是整個專案唯一沒實機驗證過的部分）。同一份邏輯只要有第二種
寫法就會漂移成兩種行為，而漂移的後果是使用者的裁示被靜默蓋掉。

現在只剩一份：**判定在 `update_guard.install()`，收尾在本檔，兩者都有測試**。
自解壓縮檔那一層只負責把酬載解到暫存區再呼叫本檔——20 行以內的批次檔。

## 為什麼「解壓覆蓋」不是可行的升級方式

使用者可能會想：安裝包裡本來就沒有訓練內容，覆蓋過去應該沒差。
**覆蓋的目標不是安裝包，是使用者那個已經累積了成果的資料夾**，而上游出貨的檔案
正好落在同一批路徑上——`rules/equipment_rules.json`、`rules/rule_tests.json`、
`governance/核定紀錄/`、`待確認事項.md` 都是上游出貨檔，也都是開場導引第二步
（逐則裁示）會寫的檔。直接覆蓋等於裁示歸零。

所以本檔在**碰目標資料夾之前**先判斷全新或升級，升級一律走逐檔判定。

## 為什麼用主控台提問而不是圖形對話框

`tkinter` 在部分 Python 發行版缺席（embeddable 版就沒有），多一個相依就多一個
在使用者電腦上才會發現的失敗點。主控台提問哪裡都跑得起來，而且測得到。
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

try:
    from tools import make_release, update_guard
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    import make_release
    import update_guard

PRODUCT_DIR = "FireReview"

FRESH, UPGRADE, REFUSE_GIT_CLONE = "fresh", "upgrade", "git_clone"

# 自解壓縮檔的殼層必須把這個批次檔放在酬載根目錄（SFX 只會執行一個程式，
# 而要跑的是 Python 腳本，中間得有一層「找到 Python」）。但它是**安裝程式的
# 產物**，不是使用者資料夾該有的東西——留著只會讓人日後誤點而重跑一次安裝。
# tests/test_make_sfx.py 有一條測試釘住這裡與 make_sfx.BATCH_NAME 一致。
INSTALLER_ARTIFACTS = ("安裝.bat",)

BANNER = """
============================================================
  Fire Review 消防審圖輔助系統
============================================================
"""

GIT_CLONE_REFUSAL = """⛔ 這個資料夾是用 git 取得的倉庫（線1），不是安裝包裝出來的。

安裝程式不會碰它——用安裝包蓋過去會把 git 的紀錄與你的本機成果攪在一起。
要更新這種資料夾請改用：

    python tools/update_guard.py check
    python tools/update_guard.py snapshot --note "更新前"
    python tools/update_guard.py commit
    git pull --ff-only

完整程序見該資料夾裡的 skills/safe-update.md。
"""


def default_target():
    """預設安裝位置：使用者文件夾底下，不是 Program Files。

    這個系統會往自己的資料夾寫東西（output/ 交付物、governance/ 裁示紀錄、
    input/ 案件圖面）。Program Files 需要管理員權限，而且 Windows 的 VirtualStore
    重導向會讓使用者在檔案總管裡找不到自己的產出。
    """
    if os.name == "nt":
        documents = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    else:
        documents = Path.home() / "Documents"
    base = documents if documents.is_dir() else Path.home()
    return base / PRODUCT_DIR


def classify_target(target):
    """要對這個資料夾做什麼——在複製任何檔案**之前**決定。"""
    target = Path(target)
    if (target / update_guard.MANIFEST_NAME).is_file():
        return UPGRADE
    if (target / ".git").exists():
        return REFUSE_GIT_CLONE
    return FRESH


def fill_welcome(target, welcome_name=None):
    """把歡迎檔裡的 {{INSTALL_DIR}} 換成真正的安裝路徑。

    這段原本在 `.iss` 的 FillWelcomeFile，沒有任何測試。搬到這裡就測得到了——
    而它是使用者裝完之後看到的第一份文字，換錯就等於沒有入口。
    """
    name = welcome_name or make_release.WELCOME_NAME
    path = Path(target) / name
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace(make_release.INSTALL_DIR_TOKEN, str(Path(target).resolve()))
    path.write_text(text, encoding="utf-8-sig")
    return str(path)


def copy_tree(source, target):
    """全新安裝：整棵複製過去。

    不走 `update_guard.install()`，因為那會先對空資料夾做一次備份——
    產生一個零筆內容的 zip，只會讓使用者困惑「我還沒開始用就有備份？」。
    """
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*INSTALLER_ARTIFACTS))
    return sorted(p.relative_to(source).as_posix()
                  for p in Path(source).rglob("*")
                  if p.is_file() and p.name not in INSTALLER_ARTIFACTS)


def prune_installer_artifacts(target):
    """把安裝程式自己的零件從使用者的資料夾清掉。

    升級路徑走的是 `update_guard.install()`，它照抄來源整棵樹（那是對的，
    它不該知道誰是安裝殼層），所以清理放在這裡收尾。
    """
    removed = []
    for name in INSTALLER_ARTIFACTS:
        path = Path(target) / name
        if path.is_file():
            path.unlink()
            removed.append(name)
    return removed


def install_optional_packages(target, timeout=300):
    """盡力而為裝選用套件——**失敗不算失敗**。

    倉庫的哲學是零安裝主線（見 requirements.txt）：法規計算、DXF 圖面標註、
    文件判讀全部只用標準庫，選用套件只影響少數交付物格式，而每項都有替代路徑。
    沙盒、離線環境、企業內網擋 PyPI 都會讓 pip 失敗，那不該讓安裝變成紅字。
    """
    requirements = Path(target) / "requirements.txt"
    if not requirements.is_file():
        return {"attempted": False, "ok": False, "reason": "沒有 requirements.txt"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"attempted": True, "ok": False, "reason": str(exc)}
    return {"attempted": True, "ok": proc.returncode == 0,
            "reason": (proc.stderr or proc.stdout or "").strip()[-500:]}


def install(source, target, by=None, with_optional=True):
    """把 source 安裝到 target。回傳處置結果，不印任何東西。"""
    source_path = Path(source).resolve()
    target_path = Path(target).expanduser()
    if not (source_path / update_guard.MANIFEST_NAME).is_file():
        raise ValueError(
            f"來源不是安裝包（找不到 {update_guard.MANIFEST_NAME}）：{source_path}")

    mode = classify_target(target_path)
    result = {"mode": mode, "source": str(source_path), "target": str(target_path),
              "plan": None, "snapshot": None, "report": None,
              "welcome": None, "optional": None, "pruned": []}
    if mode == REFUSE_GIT_CLONE:
        return result

    if mode == FRESH:
        target_path.mkdir(parents=True, exist_ok=True)
        copied = copy_tree(source_path, target_path)
        result["plan"] = {"new": copied, "updated": [], "preserved": [],
                          "untouched": []}
    else:
        outcome = update_guard.install(target_path, source=source_path, by=by)
        result["plan"] = outcome["plan"]
        result["snapshot"] = outcome["snapshot"]
        result["report"] = outcome["report"]

    result["target"] = str(target_path.resolve())
    result["pruned"] = prune_installer_artifacts(target_path)
    result["welcome"] = fill_welcome(target_path)
    if with_optional:
        result["optional"] = install_optional_packages(target_path)
    return result


# ---------------------------------------------------------------------------
# 互動
# ---------------------------------------------------------------------------

def ask_target(default, stream=None, prompt_stream=None):
    """問安裝位置，直接按 Enter 就用預設值。"""
    stream = stream or sys.stdin
    out = prompt_stream or sys.stdout
    print(f"\n要把 Fire Review 裝到哪個資料夾？", file=out)
    print(f"  直接按 Enter 就用：{default}", file=out)
    print(f"  或輸入你要的完整路徑（已經裝過的話，請填**同一個資料夾**）", file=out)
    print("> ", end="", file=out, flush=True)
    answer = (stream.readline() or "").strip().strip('"')
    return Path(answer).expanduser() if answer else Path(default)


def describe(result, out=None):
    """把處置結果講成使用者讀得懂的話。"""
    out = out or sys.stdout
    plan = result["plan"] or {}
    lines = []

    if result["mode"] == REFUSE_GIT_CLONE:
        print(GIT_CLONE_REFUSAL, file=out)
        return

    if result["mode"] == FRESH:
        lines.append(f"✅ 安裝完成——{len(plan.get('new', []))} 個檔案")
        lines.append(f"  位置：{result['target']}")
    else:
        preserved = plan.get("preserved", [])
        updated = len(plan.get("updated", [])) + len(plan.get("new", []))
        lines.append(f"✅ 更新完成——{updated} 個檔案已換成新版")
        lines.append(f"  位置：{result['target']}")
        if result["snapshot"]:
            lines.append(f"  更新前的備份：{result['snapshot']['path']}")
            lines.append("    （在安裝資料夾外面，重裝與更新都動不到它）")
        if preserved:
            lines.append(f"\n■ 保留了你改過的 {len(preserved)} 個檔案")
            lines.append("  上游新版另存在旁邊，你可以自己比對後決定要不要採用：")
            for rel in preserved[:15]:
                lines.append(f"    · {rel}  →  {rel}{update_guard.UPSTREAM_SUFFIX}")
            if len(preserved) > 15:
                lines.append(f"    …… 另有 {len(preserved) - 15} 個")
        else:
            lines.append("\n■ 你改過的檔案：無（這次沒有任何檔案需要保留原版）")
        lines.append("\n■ 你自己新增的案件圖面與實務見解：完全沒有被動到")
        if result["report"]:
            lines.append(f"\n更新報告：{result['report']}")

    optional = result.get("optional") or {}
    if optional.get("attempted") and not optional.get("ok"):
        lines.append("\n⚪ 選用套件沒裝起來——**不影響審圖**。")
        lines.append("  法規計算、DXF 圖面標註、文件判讀本來就零安裝；")
        lines.append("  只有兩階段 Excel 匯出等少數格式受影響，而它們都有替代路徑。")
        lines.append("  跑 check_env.py 會列出這台電腦現在能做什麼。")

    if result["welcome"]:
        lines.append(f"\n下一步：打開這個檔案，照著把那段話貼給你的 AI")
        lines.append(f"  {result['welcome']}")
    lines.append("  不想用終端機的話，雙擊安裝資料夾裡的「開場診斷.bat」也可以。")
    print("\n".join(lines), file=out)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="把 Fire Review 安裝或更新到指定資料夾")
    p.add_argument("--source", help="安裝來源（預設為本工具所在的資料夾）")
    p.add_argument("--target", help="安裝位置（省略則互動詢問）")
    p.add_argument("--yes", action="store_true", help="不互動，直接用 --target 或預設值")
    p.add_argument("--by", help="操作人（寫進更新報告）")
    p.add_argument("--no-optional", action="store_true",
                   help="不要嘗試安裝選用套件")
    p.add_argument("--no-pause", action="store_true",
                   help="結束時不等待按鍵（給 CI 用）")
    args = p.parse_args(argv)

    source = Path(args.source) if args.source else Path(__file__).resolve().parent.parent
    print(BANNER)

    if args.target:
        target = Path(args.target).expanduser()
    elif args.yes:
        target = default_target()
    else:
        target = ask_target(default_target())

    mode = classify_target(target)
    if mode == UPGRADE:
        print(f"\n偵測到這個資料夾已經裝過 Fire Review：{target}")
        print("  · 會先把你的成果備份到這個資料夾的**外面**")
        print("  · 你沒改過的檔案直接更新")
        print("  · **你改過的檔案保留原版**，上游新版另存成"
              f"「{update_guard.UPSTREAM_SUFFIX}」")
        print("  · 你自己新增的案件圖面與實務見解完全不動")
    elif mode == FRESH:
        print(f"\n將全新安裝到：{target}")

    if not args.yes and mode != REFUSE_GIT_CLONE:
        print("\n要繼續嗎？（直接按 Enter 繼續，輸入 n 取消）")
        print("> ", end="", flush=True)
        if (sys.stdin.readline() or "").strip().lower() in ("n", "no", "否"):
            print("已取消，什麼都沒有更動。")
            return 1

    try:
        result = install(source, target, by=args.by,
                         with_optional=not args.no_optional)
    except (ValueError, OSError) as exc:
        print(f"\n⛔ 安裝失敗：{exc}", file=sys.stderr)
        print("  你原本的檔案沒有被更動。", file=sys.stderr)
        code = 2
    else:
        describe(result)
        code = 2 if result["mode"] == REFUSE_GIT_CLONE else 0

    if not args.no_pause and sys.stdin.isatty():
        print("\n按 Enter 關閉這個視窗。")
        sys.stdin.readline()
    return code


if __name__ == "__main__":
    sys.exit(main())

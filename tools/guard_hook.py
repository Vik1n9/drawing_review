#!/usr/bin/env python3
"""破壞性命令攔截：在 AI 執行會抹掉本機訓練成果的 git 操作之前擋下來。

只用 Python 標準庫。設計成 Claude Code 的 PreToolUse hook，但核心是純函式，
任何工具都能拿去用：

    python3 tools/guard_hook.py check "git reset --hard"   # 0=放行 2=攔截
    echo '{"tool_name":"Bash","tool_input":{"command":"git clean -fd"}}' \\
        | python3 tools/guard_hook.py hook                 # 0=放行 2=攔截

為什麼需要這道關卡（呼應 AGENTS.md 底線 6）：使用者的訓練成果只存在他本機，
從未推上遠端。`git reset --hard`／`git checkout -- .` 會讓**未提交**的改動永久消失
（那些內容從來沒進過 object database，reflog 也救不回）；`git clean -fd` 會刪掉
`input/{案件}/` 這種未追蹤目錄——那是使用者唯一一份原始圖面，刪了連重跑都不可能。

三層防護裡本檔是**唯一真正攔得下命令**的一層，但只有 Claude Code 有 hook 機制，
所以依 CONTRIBUTING.md 的工具中立條款，它是加分自動化而非機制本體；機制本體是
`tools/onboarding.py status` 與 `AGENTS.md` 的紅線。

**一律 fail-open**：解析不了、格式沒見過、任何例外——全部放行。這道關卡寧可漏擋，
也不能因為自己壞掉就讓使用者連正常工作都做不了。

本工具不做任何法規判斷（審圖最高原則 2／4／5）。
"""

import argparse
import json
import re
import shlex
import sys

EXIT_ALLOW, EXIT_BLOCK = 0, 2

SKILL = "skills/safe-update.md"

# 會讓「未提交的改動」或「未追蹤的檔案」永久消失的 git 操作。
# 逐條都附「它到底毀掉什麼」——AI 看到攔截訊息才知道要改走哪條路，
# 而不是換個寫法再試一次。
GIT_RULES = [
    (r"^git\s+reset\b.*\s--hard\b",
     "git reset --hard 會丟棄工作目錄裡所有未提交的改動"),
    (r"^git\s+checkout\b.*\s--(\s|$)",
     "git checkout -- <路徑> 會把檔案還原成上游版本，未提交的改動永久消失"),
    (r"^git\s+checkout\s+\.(\s|$)",
     "git checkout . 會把整個工作目錄還原成上游版本"),
    (r"^git\s+checkout\b.*\s-f\b",
     "git checkout -f 會強制覆蓋工作目錄"),
    (r"^git\s+restore\b(?!.*--staged\s*$)",
     "git restore 會把檔案還原成上游版本，未提交的改動永久消失"),
    (r"^git\s+clean\b",
     "git clean 會刪掉未追蹤的檔案，包含 input/{案件}/ 這種唯一一份的原始圖面"),
    (r"^git\s+stash\s+(drop|clear)\b",
     "git stash drop／clear 會丟棄暫存起來的改動"),
    (r"^git\s+pull\b.*\s(--force|-f)\b",
     "git pull --force 會強制覆蓋本機分支"),
]

# rm -rf 只在打到倉庫本身或資料區時才擋——全面攔截 rm -rf 會讓正常工作寸步難行。
DATA_ZONES = ("rules", "governance", "practice_notes", "training",
              "graphify-out", "input", "output")
RM_RECURSIVE_FORCE = re.compile(r"^rm\s+(-\S*[rR]\S*\s+-\S*f|-\S*f\S*\s+-\S*[rR]|-\S*[rRf]{2,})")


SEPARATORS = ("&&", "||", ";", "|", "&", ";;")


def split_pipeline(command):
    """把一行命令拆成子命令；&&、||、;、| 都算分界。

    用 shlex 而不是正規表示式切割，因為**引號內的分隔符不是分隔符**。
    字面切割會把 `echo "cd /tmp && git clean -fd"` 拆出一個看起來像
    `git clean -fd` 的片段而誤攔——本檔開發時就真的被自己的測試腳本擋下來過。
    誤攔比漏擋更傷：使用者會學會繞過這道關卡，那它就等於不存在。

    shlex 會脫掉引號，所以 `bash -c "git clean -fd"` 這種包一層的寫法擋不到
    （拆出來的片段開頭是 `bash`，而規則一律錨在行首）。這是刻意的 fail-open：
    真正的機制本體是 AGENTS.md 的紅線與 onboarding 診斷，本檔只擋直球。
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:  # 引號沒收尾——退回字面切割，寧可誤攔也別讓它整個溜過去
        return [p.strip() for p in re.split(r"&&|\|\||[;|\n]", command) if p.strip()]

    parts, current = [], []
    for token in tokens:
        if token in SEPARATORS:
            if current:
                parts.append(" ".join(current))
                current = []
        else:
            current.append(token)
    if current:
        parts.append(" ".join(current))
    return parts


def rm_targets_repo(part):
    """`rm -rf` 的目標是否打在倉庫本身或資料區。"""
    if not RM_RECURSIVE_FORCE.match(part):
        return None
    try:
        args = [a for a in shlex.split(part)[1:] if not a.startswith("-")]
    except ValueError:  # 引號沒收尾之類——fail-open
        return None
    for target in args:
        cleaned = target.rstrip("/").lstrip("./")
        head = cleaned.split("/", 1)[0]
        if cleaned in ("", ".", "..") or head in DATA_ZONES:
            return f"rm -rf {target} 會刪掉倉庫或資料區，本機訓練成果一併消失"
    return None


DRY_RUN = re.compile(r"(^|\s)(--dry-run|-[a-zA-Z]*n[a-zA-Z]*)(\s|$)")


def is_inspection(part):
    """`git clean -n` 什麼都不刪——那是「先看看會刪什麼」，不是破壞。

    連預演都擋掉，只會把代理推向「不檢查就動手」或「想辦法繞過這道關卡」，
    兩種都比讓它看一眼更危險。本檔開發時就真的被自己的預演命令擋下來過。
    """
    return part.startswith("git clean") and bool(DRY_RUN.search(part))


def check_command(command):
    """回傳攔截理由；放行則回 None。"""
    if not command or not isinstance(command, str):
        return None
    for part in split_pipeline(command):
        normalized = " ".join(part.split())
        if is_inspection(normalized):
            continue
        for pattern, reason in GIT_RULES:
            if re.search(pattern, normalized):
                return reason
        rm_reason = rm_targets_repo(normalized)
        if rm_reason:
            return rm_reason
    return None


def block_message(reason):
    return (f"⛔ 這個命令被 Fire Review 擋下：{reason}。\n"
            f"使用者的訓練成果（規則裁示、實務見解、案件圖面）只存在他本機，"
            f"覆蓋掉不可逆。\n"
            f"→ 先跑 python3 tools/update_guard.py check 看有什麼會被影響，"
            f"再依 {SKILL} 的安全更新程序走：備份 → 本機提交 → git pull --ff-only。\n"
            f"→ 使用者明確要求且已備份時，請他自己在終端機執行，不要由你代跑。")


def cmd_check(args):
    reason = check_command(args.command)
    if reason is None:
        return EXIT_ALLOW
    print(block_message(reason), file=sys.stderr)
    return EXIT_BLOCK


def cmd_hook(args):
    """讀 stdin 的 PreToolUse payload。任何意外一律放行。"""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        return EXIT_ALLOW
    if not isinstance(payload, dict):
        return EXIT_ALLOW
    if payload.get("tool_name") not in (None, "Bash"):
        return EXIT_ALLOW
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return EXIT_ALLOW
    reason = check_command(tool_input.get("command"))
    if reason is None:
        return EXIT_ALLOW
    print(block_message(reason), file=sys.stderr)
    return EXIT_BLOCK


def build_parser():
    p = argparse.ArgumentParser(
        description="破壞性命令攔截（結束碼 0=放行 2=攔截；解析不了一律放行）")
    sub = p.add_subparsers(dest="command_name", required=True)

    s = sub.add_parser("check", help="檢查一行命令")
    s.add_argument("command", help="要檢查的完整命令")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("hook", help="從 stdin 讀 PreToolUse payload")
    s.set_defaults(func=cmd_hook)
    return p


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — fail-open 是本檔的核心紀律
        return EXIT_ALLOW


if __name__ == "__main__":
    sys.exit(main())

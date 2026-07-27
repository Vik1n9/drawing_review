#!/usr/bin/env python3
"""發佈打包：把倉庫做成使用者裝得起來的安裝包（線2）。

只用 Python 標準庫。

    python3 tools/make_release.py --version v1.2.0 --out dist/
    python3 tools/make_release.py --version v1.2.0 --out dist/ --stage-only

## 為什麼要有第二條取得路徑

線1 是 `git clone`——給技術人員與要送 PR 的人。但本倉庫的使用者是消防專業人員，
不懂 git，也不一定裝得起套件。要他「先學會 git 才能開始審圖」等於把他擋在門外，
而讓 AI 代跑 git 又正是本機訓練成果被蓋掉的來源（見 AGENTS.md 底線 6）。

線2 因此存在：下載安裝程式 → 自選安裝位置 → 把那個資料夾丟給 AI 當專案資料夾。
全程沒有 git，也就沒有 `git pull` 撞到本機改動的問題。

## 安裝清單.json 是這條路線的關鍵

安裝目錄沒有 `.git`，本來無從分辨「上游出貨的原樣」與「使用者改過的」。
發版時把每個檔案的 sha256 記進 `安裝清單.json`，`tools/update_guard.py` 就有了
權威基準——而且它是打包產物，不是要人工維護的狀態檔，零維護稅。

升級時 `update_guard.py install` 靠它逐檔判定：使用者改過的保住原檔、上游新版
另存 `.上游新版`；沒改過的直接更新。
"""

import argparse
import datetime
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools import update_guard as guard
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    import update_guard as guard

SCHEMA_VERSION = 1
PRODUCT = "FireReview"
UPSTREAM_OWNER = "upstream"

# 包進安裝包的東西。使用者要能開箱審圖，也要能自己驗證安裝完整
# （tests/ 全部用 tempfile，不依賴 input/範例 或 output/，拿掉範例圖也跑得起來）。
INCLUDE_DIRS = ("tools", "skills", "rules", "graphify-out", "governance",
                "practice_notes", "training", "tests", ".claude")
INCLUDE_FILES = ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md",
                 "requirements.txt", "待確認事項.md", "input/README.md")

# 不進安裝包。範例圖佔掉 3 MB 卻不是使用者要審的案件；
# 示範交付物會讓全新安裝的 output/ 一開始就有別人的東西，反而混淆。
EXCLUDE_PATTERNS = (
    ".git/*", "*/__pycache__/*", "*.pyc", "*/.DS_Store",
    "input/範例/*", "output/*",
    "graphify-out/.graphify_*", "graphify-out/cache/*",
    "dist/*", "packaging/*",
    guard.MANIFEST_NAME, guard.REPORT_PREFIX + "*", "*" + guard.UPSTREAM_SUFFIX,
)

# 安裝後留在資料夾裡、給不熟終端機的人用的東西。
DIAGNOSTIC_BAT = """@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Fire Review 開場診斷 ===
echo.
where py >nul 2>nul && (py -3 tools\\onboarding.py status & goto done)
where python >nul 2>nul && (python tools\\onboarding.py status & goto done)
echo 找不到 Python。請先安裝：https://www.python.org/downloads/
echo 安裝時記得勾選「Add python.exe to PATH」，然後再雙擊本檔案。
goto end
:done
echo.
echo ------------------------------------------------------------
echo 要把這個系統交給 AI 的話，把下面這行貼給它：
echo   請把 %CD% 當作專案資料夾，先讀 AGENTS.md，再跑 python tools/onboarding.py status
echo ------------------------------------------------------------
:end
echo.
pause
"""

# 安裝程式會把 {{INSTALL_DIR}} 換成實際安裝路徑。
# 直接解壓 zip 的人換不到，所以「開場診斷.bat」也會印一份帶實際路徑的版本。
INSTALL_DIR_TOKEN = "{{INSTALL_DIR}}"
WELCOME_NAME = "安裝完成-請把這段貼給你的AI.txt"

WELCOME_TEMPLATE = f"""Fire Review 消防審圖輔助系統——安裝完成

把下面框起來的這段整段貼給你的 AI（Claude Code／Codex／OpenCode 都可以）：

------------------------------------------------------------
請把這個資料夾當作專案資料夾（工作目錄）：

  {INSTALL_DIR_TOKEN}

先讀裡面的 AGENTS.md（行為契約正本），然後執行開場診斷：

  python tools/onboarding.py status

接著照 skills/onboarding.md 帶我開始。
------------------------------------------------------------

不想用終端機的話，直接雙擊這個資料夾裡的「開場診斷.bat」也可以，
它會把上面那段話連同實際路徑一起印出來。

【你的成果存在哪】
  你的審圖成果——規則裁示、實務見解、案件圖面、交付物——都在這個資料夾裡。
  它們**只存在你這台電腦**，沒有上傳到任何地方。

【要更新到新版時】
  到 GitHub Releases 下載新版安裝程式，裝到**同一個資料夾**即可。
  安裝程式會先把你的成果備份到這個資料夾的外面，再逐檔判斷：
  你改過的檔案一律保住，上游的新版另存成「.上游新版」讓你自己比對決定。
  裝完會產生一份「更新報告-日期.txt」，逐檔告訴你發生了什麼事。

  **不要用 AI 幫你「更新倉庫」**——它可能會用 git 指令把你的成果清掉。
  詳見 skills/safe-update.md。
"""

EMPTY_DIRS = ("input", "output", "training/inbox",
              "practice_notes/active", "practice_notes/staging",
              "practice_notes/graph_extractions")


def is_excluded(rel):
    return guard.matches_any(rel, EXCLUDE_PATTERNS)


def iter_sources(root):
    """要打包的 repo 相對路徑。"""
    root = Path(root)
    for name in INCLUDE_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if not is_excluded(rel):
                yield rel
    for name in INCLUDE_FILES:
        if (root / name).is_file() and not is_excluded(name):
            yield name


def owner_for(rel):
    """資料區內沿用 update_guard 的 owner 表——兩個工具必須是同一份真相。"""
    head = rel.split("/", 1)[0]
    if head in guard.DATA_ZONES or rel in guard.ROOT_FILES:
        return guard.owner_for(rel)
    return UPSTREAM_OWNER


def regulation_version(root):
    path = Path(root) / "rules" / "equipment_rules.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("regulation_version")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def source_commit(root):
    head = guard.run_git(root, ["rev-parse", "HEAD"])
    return head.strip() if head else None


def stage(root, out_dir, version, now=None):
    """把安裝包內容攤到一個目錄，並寫出 安裝清單.json 與輔助檔。

    先攤成目錄再壓縮，是因為 Inno Setup 要的就是一棵目錄樹，
    而 `update_guard.py install --from` 吃的也是目錄——一份產物餵兩條路。
    """
    root = Path(root)
    stage_dir = Path(out_dir) / f"{PRODUCT}-{version}"
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)

    packaged = []
    for rel in iter_sources(root):
        target = stage_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, target)
        packaged.append(rel)

    # 工具會往這些目錄寫東西，空目錄進不了 zip，用 .gitkeep 佔位
    for rel in EMPTY_DIRS:
        keep = stage_dir / rel / ".gitkeep"
        keep.parent.mkdir(parents=True, exist_ok=True)
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
            packaged.append(f"{rel}/.gitkeep")

    (stage_dir / "開場診斷.bat").write_text(DIAGNOSTIC_BAT, encoding="utf-8-sig")
    packaged.append("開場診斷.bat")

    (stage_dir / WELCOME_NAME).write_text(WELCOME_TEMPLATE, encoding="utf-8-sig")
    packaged.append(WELCOME_NAME)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "version": version,
        "released_at": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
        "source_commit": source_commit(root),
        "regulation_version": regulation_version(root),
        "note": "上游出貨基準：update_guard.py 以此分辨「上游原樣」與「使用者改過」。"
                "升級時改過的檔案會被保住，上游新版另存 " + guard.UPSTREAM_SUFFIX + "。",
        "files": {rel: dict(guard.file_entry(stage_dir, rel), owner=owner_for(rel))
                  for rel in sorted(packaged)},
    }
    (stage_dir / guard.MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return stage_dir, manifest


def make_zip(stage_dir, out_dir, version):
    """zip 內不加頂層目錄——安裝程式直接解到安裝位置，路徑才對得上。"""
    zip_path = Path(out_dir) / f"{PRODUCT}-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(Path(stage_dir).rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(stage_dir).as_posix())
    return zip_path


def build(root=".", out="dist", version="v0.0.0", stage_only=False, now=None):
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage_dir, manifest = stage(root, out_dir, version, now=now)
    zip_path = None if stage_only else make_zip(stage_dir, out_dir, version)
    return {"stage_dir": str(stage_dir),
            "zip": str(zip_path) if zip_path else None,
            "version": version,
            "file_count": len(manifest["files"]),
            "manifest": str(Path(stage_dir) / guard.MANIFEST_NAME)}


def main(argv=None):
    p = argparse.ArgumentParser(description="把倉庫做成使用者裝得起來的安裝包")
    p.add_argument("--root", default=".", help="倉庫根目錄（預設為當前目錄）")
    p.add_argument("--version", required=True, help="版本號，例如 v1.2.0")
    p.add_argument("--out", default="dist", help="輸出目錄（預設 dist/）")
    p.add_argument("--stage-only", action="store_true",
                   help="只攤出目錄，不壓縮（給 Inno Setup 用）")
    args = p.parse_args(argv)

    result = build(args.root, args.out, args.version, stage_only=args.stage_only)
    print(f"✅ 已打包 {result['file_count']} 個檔案（{result['version']}）")
    print(f"  目錄：{result['stage_dir']}")
    print(f"  清單：{result['manifest']}")
    if result["zip"]:
        size = Path(result["zip"]).stat().st_size / 1024 / 1024
        print(f"  壓縮檔：{result['zip']}（{size:.1f} MB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

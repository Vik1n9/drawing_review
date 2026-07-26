#!/usr/bin/env python3
"""Fire Review 環境自檢：回報各交付物所需套件是否就緒，並給出安裝指引。

只用 Python 標準庫，任何環境都能直接執行：

    python3 tools/check_env.py           # 列出狀態
    python3 tools/check_env.py --strict  # 有缺套件時以非零離開（供 CI 使用）
"""

import importlib.util
import shutil
import sys

# (import 名稱, 套件名稱, 用途/對應工具)
PY_DEPS = [
    ("ezdxf", "ezdxf", "tools/dxf_svg_review.py — DXF 轉 SVG 圖面標註（交付物1）"),
    ("openpyxl", "openpyxl", "tools/standard_checklist_html.py — xlsx 標準表檢核"),
    ("fitz", "pymupdf", "tools/pdf_annotate.py — 平面圖 PDF 紅圈標註"),
]

# 只用標準庫、不需安裝即可運作的核心工具
STDLIB_ONLY = [
    "tools/fire_code_calc.py — 法規門檻與數量計算、規則測試、自檢",
    "tools/regulation_index.py — 法規逐條索引與查詢",
    "tools/checklist_html.py / article_checklist.py / mixed_use_report.py / verification_sheet.py",
]


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def interpreter_command():
    """使用者複製貼上時該打的解譯器命令。"""
    for name in ("python3", "python"):
        if shutil.which(name):
            return name
    return sys.executable or "python3"


def probe():
    """回傳結構化的環境狀態，供本檔渲染與 tools/onboarding.py 重用。

    刻意不印任何東西——呈現格式歸 main()，聚合判斷歸呼叫者。
    """
    deps = [
        {"module": mod, "package": pkg, "use": use, "ok": has_module(mod)}
        for mod, pkg, use in PY_DEPS
    ]
    return {
        "python_version": sys.version.split()[0],
        # 給使用者複製的命令用哪個字：Windows 上常只有 python 而無 python3。
        # 兩者都找不到才退回 sys.executable 的完整路徑（至少貼上去能跑）。
        "interpreter": interpreter_command(),
        "has_bash": shutil.which("bash") is not None,
        "deps": deps,
        "missing": [d["package"] for d in deps if not d["ok"]],
        "graphify": shutil.which("graphify") is not None,
        "stdlib_only": list(STDLIB_ONLY),
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv
    env = probe()

    print("== Fire Review 環境自檢 ==")
    print(f"Python：{env['python_version']}")

    print("\n[核心工具] 只用標準庫，無需安裝即可執行：")
    for line in env["stdlib_only"]:
        print(f"  ✓ {line}")

    print("\n[交付物套件] 未安裝者，對應工具會給出明確錯誤：")
    for dep in env["deps"]:
        mark = "✓" if dep["ok"] else "✗"
        print(f"  {mark} {dep['package']:10} — {dep['use']}")
    missing = env["missing"]

    graph_ok = env["graphify"]
    print("\n[法規知識圖譜] 選用（graph.html 直接開瀏覽器即可看，重建／CLI 查詢才需要）：")
    print(f"  {'✓' if graph_ok else '✗'} graphify — 圖譜重建與 query/explain/path 查詢")

    if missing:
        print("\n→ 補齊套件：bash tools/setup.sh")
        print("  （或 python3 -m pip install -r requirements.txt）")
    if not graph_ok:
        print("→ 需重建或查詢法規圖譜時：bash tools/setup.sh --with-graph")
    if not missing and graph_ok:
        print("\n全部就緒。")

    if strict and missing:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    strict = "--strict" in argv

    print("== Fire Review 環境自檢 ==")
    print(f"Python：{sys.version.split()[0]}")

    print("\n[核心工具] 只用標準庫，無需安裝即可執行：")
    for line in STDLIB_ONLY:
        print(f"  ✓ {line}")

    print("\n[交付物套件] 未安裝者，對應工具會給出明確錯誤：")
    missing = []
    for mod, pkg, use in PY_DEPS:
        ok = has_module(mod)
        print(f"  {'✓' if ok else '✗'} {pkg:10} — {use}")
        if not ok:
            missing.append(pkg)

    graph_ok = shutil.which("graphify") is not None
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

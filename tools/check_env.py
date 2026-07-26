#!/usr/bin/env python3
"""Fire Review 環境自檢：回報「現在能做什麼」，而不只是「缺哪些套件」。

本倉庫的使用者多半只裝了一個 AI 桌面版就開始用，受沙盒與安全限制影響，
`pip install` 往往裝不起來。對這樣的使用者，列一串裝不上的套件沒有意義——
真正有用的是能力矩陣：哪些現在就能做、哪些做不到、做不到的有沒有別條路。

只用 Python 標準庫，任何環境都能直接執行：

    python3 tools/check_env.py           # 列出能力矩陣
    python3 tools/check_env.py --strict  # 供 CI 使用（選用套件缺席不算失敗）
"""

import importlib.util
import shutil
import sys

# (import 名稱, 套件名稱, 用途/對應工具)
# 三者皆為**選用**——缺席時各有替代路徑，見 CAPABILITY_SPECS。
PY_DEPS = [
    ("ezdxf", "ezdxf", "tools/dxf_svg_review.py — 二進位 DXF 後備（文字 DXF 已零相依）"),
    ("openpyxl", "openpyxl", "tools/stage_report_xlsx.py — 兩階段 Excel 交付物"),
    ("fitz", "pymupdf", "tools/pdf_annotate.py — 平面圖 PDF 紅圈標註（legacy）"),
]

# 只用標準庫、不需安裝即可運作的核心工具
STDLIB_ONLY = [
    "tools/fire_code_calc.py — 法規門檻與數量計算、規則測試、自檢",
    "tools/regulation_index.py — 法規逐條索引與查詢",
    "tools/dxf_parse.py — 零相依 DXF 解析（交付物1 的預設路徑）",
    "tools/dwg_guide.py — DWG 收件檢查與另存 DXF 引導",
    "tools/checklist_html.py / article_checklist.py / mixed_use_report.py / verification_sheet.py",
]

# 能力矩陣。(能力, 需要的模組, 需要的外部程式, 替代路徑)
#   模組與外部程式皆為 None ＝ 零安裝可用。
#   不可用的能力**必須**有替代路徑，否則等於把使用者丟在原地
#   （由 tests/test_check_env.py 強制）。
CAPABILITY_SPECS = [
    ("法規門檻計算與法條查詢", None, None, None),
    ("DXF 圖面標註（交付物1）", None, None, None),
    ("PDF／DOCX／XLSX 判讀", None, None, None),
    ("DWG 圖面轉 DXF", None, ("dwg2dxf", "ODAFileConverter"),
     "用你的 CAD 另存 DXF——零安裝、品質更好："
     "python3 tools/dwg_guide.py check --path input/"),
    ("兩階段 Excel 交付物匯出", "openpyxl", None,
     "改用 HTML 版法條檢核清單（tools/checklist_html.py），內容相同、格式不同"),
    ("平面圖 PDF 紅圈標註（legacy）", "fitz", None,
     "改用交付物1 的 HTML／SVG 圖面標註（tools/dxf_svg_review.py），功能更完整"),
]

# 零安裝能力的補充說明——講清楚「為什麼不用裝」，使用者才敢相信
CAPABILITY_NOTES = {
    "DXF 圖面標註（交付物1）": "文字 DXF 由 tools/dxf_parse.py 以標準庫解析；"
                                "只有二進位 DXF 才需要 ezdxf",
    "PDF／DOCX／XLSX 判讀": "由 AI 直接讀取檔案，不需要安裝任何套件",
}


def has_module(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def has_program(names):
    return any(shutil.which(name) for name in names)


def interpreter_command():
    """使用者複製貼上時該打的解譯器命令。"""
    for name in ("python3", "python"):
        if shutil.which(name):
            return name
    return sys.executable or "python3"


def build_capabilities():
    matrix = []
    for name, module, programs, alternative in CAPABILITY_SPECS:
        zero_install = module is None and programs is None
        ok = True
        if module:
            ok = has_module(module)
        if programs:
            ok = has_program(programs)
        matrix.append({
            "name": name,
            "ok": ok,
            "zero_install": zero_install,
            "requires": module or (" 或 ".join(programs) if programs else None),
            "alternative": alternative,
            "note": CAPABILITY_NOTES.get(name),
        })
    return matrix


def probe():
    """回傳結構化的環境狀態，供本檔渲染與 tools/onboarding.py 重用。

    刻意不印任何東西——呈現格式歸 main()，聚合判斷歸呼叫者。
    """
    deps = [
        {"module": mod, "package": pkg, "use": use, "ok": has_module(mod)}
        for mod, pkg, use in PY_DEPS
    ]
    capabilities = build_capabilities()
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
        "capabilities": capabilities,
        "unavailable": [c["name"] for c in capabilities if not c["ok"]],
    }


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    env = probe()

    print("== Fire Review 環境自檢 ==")
    print(f"Python：{env['python_version']}")
    print("\n本倉庫預設什麼都不必安裝。以下是這台電腦現在的實際能力：")

    print("\n[現在就能做]")
    for capability in env["capabilities"]:
        if not capability["ok"]:
            continue
        line = f"  ✓ {capability['name']}"
        if capability["note"]:
            line += f"\n      {capability['note']}"
        print(line)

    unavailable = [c for c in env["capabilities"] if not c["ok"]]
    if unavailable:
        print("\n[目前做不到，但都有別條路]")
        for capability in unavailable:
            print(f"  ✗ {capability['name']}（需要 {capability['requires']}）")
            print(f"      → {capability['alternative']}")

    print("\n[核心工具] 只用標準庫，無需安裝即可執行：")
    for line in env["stdlib_only"]:
        print(f"  ✓ {line}")

    print("\n[選用套件] 只影響上面列出的少數能力，缺席不影響審圖主線：")
    for dep in env["deps"]:
        print(f"  {'✓' if dep['ok'] else '✗'} {dep['package']:10} — {dep['use']}")

    print("\n[法規知識圖譜] 選用（graph.html 直接開瀏覽器即可看）：")
    print(f"  {'✓' if env['graphify'] else '✗'} graphify — 圖譜重建與 query/explain/path 查詢")

    if env["missing"]:
        print("\n→ 這台電腦裝得起套件的話，可補齊：" +
              (f"bash tools/setup.sh" if env["has_bash"]
               else f"{env['interpreter']} -m pip install -r requirements.txt"))
        print("  裝不起來也沒關係——上面每一項都有替代路徑。")
    else:
        print("\n全部就緒。")

    # --strict 只保證「審圖主線可用」。選用套件缺席各有替代路徑，
    # 不得讓 CI 或自架環境因此紅燈。
    if "--strict" in argv:
        blocking = [c for c in env["capabilities"] if not c["ok"] and not c["alternative"]]
        return 1 if blocking else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

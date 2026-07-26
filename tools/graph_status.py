#!/usr/bin/env python3
"""法規知識圖譜新鮮度把關：偵測圖譜來源檔異動，確保後續工作流程查到的是最新圖譜。

只用 Python 標準庫。

    python3 tools/graph_status.py check   # 0=新鮮 2=過期／註解未納入 3=尚未建立基準
    python3 tools/graph_status.py stamp   # 重建圖譜並併入註解層後蓋章（記錄當前來源指紋）

兩道關卡：**指紋新鮮度**（來源檔改了有沒有重建）＋**註解納入度**
（`practice_notes/active/` 每一則是否真的在 `graph.json` 有節點、sha 對得上）。
只驗指紋會有假綠燈——`/graphify rules` 只掃 `rules/`，重建後蓋章燈是綠的，
但實務註解其實沒進圖譜，審圖時查圖譜就查不到訓練成果。納入度由
`tools/practice_note_graph.py` 提供（LLM 語意抽取 → 確定性合併）。

為什麼不沿用 graphify 自己的 `graphify-out/manifest.json`：它記錄的是 `mtime`，
全新 clone 之後所有檔案的 mtime 都會重置，會整批誤報「過期」。本工具改以
sha256 逐檔指紋存於 `graphify-out/source_fingerprint.json`（非 dot 前綴，納版控），
任何機器上重算都得到相同結果。

邊界（呼應 CLAUDE.md 審圖最高原則 2、4）：圖譜只是索引與導覽，不是門檻數值來源。
本工具只回答「圖譜有沒有跟上規則庫」，不回答任何法規判斷。
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tools import practice_note_graph
except ImportError:
    import practice_note_graph

FINGERPRINT_PATH = "graphify-out/source_fingerprint.json"
GRAPH_PATH = "graphify-out/graph.json"

# 圖譜來源檔＝**圖譜真的從中抽出節點的檔案**（法典層）＋ practice_notes/active/（註解層）。
#
# 不含 rules/equipment_rules.json 與 rules/mixed_use_rules.json：這兩個檔在 graphify 的
# manifest 裡（掃描範圍涵蓋），但 graph.json 的 482 個節點沒有任何一個出自它們
# （node.source_file 只有 core/ 底下的全文 md、附表 PDF、附表圖檔與 rules/README.md）。
# 把它們列入追蹤，會讓每一次先紅再綠改參數都誤報「圖譜過期」，而重建出來的圖譜完全相同。
# 這個「未產生節點就不追蹤」的前提由 untracked_graph_sources() 持續驗證：
# 日後若重建出的圖譜真的含有這些檔的節點，check 會直接紅燈要求把它們加回本清單。
SOURCE_GLOBS = [
    "rules/core/**/*",
    "rules/README.md",
    "rules/regulation_articles/article-*.json",
    "practice_notes/active/*.json",
]

# graph.json 的 node.source_file 是相對於 graphify 執行根目錄（本專案為 rules/）的路徑，
# 註解層節點則由 practice_note_graph 以 repo 相對路徑寫入。兩種都要能對回 repo 路徑，
# 且 rules/ 要先試——否則 rules/README.md 會被誤判成 repo 根目錄的 README.md。
GRAPH_SOURCE_PREFIXES = ["rules/", ""]

REBUILD_HINT = (
    "重建圖譜：/graphify rules --update（增量）或 /graphify rules（大改）；"
    "graphify 未安裝先跑 bash tools/setup.sh --with-graph。"
    "重建會覆寫 graph.json，之後必須重跑 python3 tools/practice_note_graph.py merge "
    "把實務註解層併回去，最後才執行 python3 tools/graph_status.py stamp 蓋章。"
)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_sources(root="."):
    """回傳 {repo 相對路徑: sha256}，路徑一律以 posix 形式排序輸出。"""
    root = Path(root)
    found = {}
    for pattern in SOURCE_GLOBS:
        if "*" in pattern:
            matches = sorted(p for p in root.glob(pattern) if p.is_file())
        else:
            candidate = root / pattern
            matches = [candidate] if candidate.is_file() else []
        for path in matches:
            found[path.relative_to(root).as_posix()] = sha256_file(path)
    return dict(sorted(found.items()))


def untracked_graph_sources(root=".", tracked=None):
    """圖譜裡有節點、卻不在追蹤清單內的來源檔。

    SOURCE_GLOBS 刻意不追蹤「掃描得到但不產生節點」的檔案（見上方說明）。
    這個前提一旦破功——重建後的圖譜開始從那些檔抽出節點——追蹤清單就會漏看真正的
    來源異動。本函式把該前提變成每次 check 都驗的不變式：回傳非空即代表清單該補。
    """
    root = Path(root)
    graph = root / GRAPH_PATH
    if not graph.is_file():
        return []
    try:
        with open(graph, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    tracked = set(collect_sources(root) if tracked is None else tracked)
    untracked = set()
    for node in doc.get("nodes", []):
        cited = node.get("source_file")
        if not cited:
            continue
        for prefix in GRAPH_SOURCE_PREFIXES:
            candidate = f"{prefix}{cited}"
            if candidate in tracked:
                break
            if (root / candidate).is_file():
                untracked.add(candidate)
                break
    return sorted(untracked)


def graph_scale(root="."):
    """讀圖譜規模作為蓋章時的佐證；圖譜不存在或格式不符時回 None。"""
    path = Path(root) / GRAPH_PATH
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return {"nodes": len(doc.get("nodes", [])), "edges": len(doc.get("links", doc.get("edges", [])))}


def load_fingerprint(root="."):
    path = Path(root) / FINGERPRINT_PATH
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def diff_sources(recorded, current):
    """比對兩份指紋，回傳 added / removed / changed 三類 repo 相對路徑。"""
    return {
        "added": sorted(set(current) - set(recorded)),
        "removed": sorted(set(recorded) - set(current)),
        "changed": sorted(p for p in set(recorded) & set(current) if recorded[p] != current[p]),
    }


def evaluate(root="."):
    """圖譜新鮮度評估結果（供 training_intake.py status 直接取用）。

    兩道關卡，缺一不可：

    1. **指紋新鮮度**——來源檔改了、圖譜沒重建即 `stale`。
    2. **註解納入度**——`practice_notes/active/` 的每一則註解都必須真的在
       `graph.json` 裡有對應節點，且 `note_sha256` 對得上。只驗指紋會出現假綠燈：
       重建圖譜（`/graphify rules` 只掃 `rules/`）之後蓋章，燈是綠的，
       但註解根本沒進圖譜，審圖時查圖譜就查不到訓練成果。
    """
    current = collect_sources(root)
    notes = practice_note_graph.check(root)
    untracked = untracked_graph_sources(root, current)
    doc = load_fingerprint(root)
    if doc is None:
        return {
            "state": "no_baseline",
            "source_count": len(current),
            "diff": {"added": sorted(current), "removed": [], "changed": []},
            "stamped_at": None,
            "notes": notes,
            "untracked_sources": untracked,
        }
    changes = diff_sources(doc.get("sources", {}), current)
    if untracked:
        state = "untracked_sources"
    elif any(changes.values()):
        state = "stale"
    elif notes["state"] != "covered":
        state = "notes_missing"
    else:
        state = "fresh"
    return {
        "state": state,
        "source_count": len(current),
        "diff": changes,
        "stamped_at": doc.get("stamped_at"),
        "notes": notes,
        "untracked_sources": untracked,
    }


EXIT_CODES = {"fresh": 0, "stale": 2, "notes_missing": 2, "untracked_sources": 2,
              "no_baseline": 3}


def format_notes(notes):
    """實務註解納入度的單行摘要（供 check／status 共用）。"""
    if notes["active"] == 0:
        return "實務註解：（無 active 註解）"
    if notes["state"] == "covered":
        return f"實務註解：✅ {notes['active']} 則全部已納入圖譜（查圖譜查得到訓練成果）"
    parts = []
    for label, key in (("缺漏", "missing"), ("過期", "stale"), ("殘留", "orphan")):
        if notes[key]:
            parts.append(f"{label} {'、'.join(notes[key])}")
    return (f"實務註解：⛔ {notes['active']} 則中僅 {notes['merged']} 則在圖譜內"
            f"（{'；'.join(parts)}）")


def format_check(result):
    lines = ["== 法規圖譜新鮮度 =="]
    notes = result.get("notes") or {"active": 0, "state": "covered", "merged": 0,
                                    "missing": [], "stale": [], "orphan": []}
    if result["state"] == "fresh":
        lines.append(f"✅ 新鮮 —— {result['source_count']} 個來源檔與圖譜指紋一致"
                     f"（蓋章時間：{result['stamped_at'] or '未記錄'}）")
        lines.append(format_notes(notes))
        return "\n".join(lines)

    if result["state"] == "no_baseline":
        lines.append(f"⚠️ 尚未建立基準 —— 找不到 {FINGERPRINT_PATH}，無法判斷圖譜是否跟上"
                     f"（目前 {result['source_count']} 個來源檔）")
        lines.append(format_notes(notes))
        lines.append("→ 確認 graphify-out/ 圖譜為當前規則庫所建之後，執行："
                     " python3 tools/graph_status.py stamp")
        return "\n".join(lines)

    if result["state"] == "untracked_sources":
        lines.append("⛔ 追蹤清單漏檔 —— 圖譜有節點出自下列檔案，但它們不在 "
                     "graph_status.py 的 SOURCE_GLOBS 內；這些檔改了不會被偵測到")
        for path in result["untracked_sources"]:
            lines.append(f"  [未追蹤] {path}")
        lines.append(format_notes(notes))
        lines.append("→ 把上列路徑加進 tools/graph_status.py 的 SOURCE_GLOBS，再重新蓋章")
        return "\n".join(lines)

    if result["state"] == "notes_missing":
        lines.append("⛔ 註解未納入 —— 來源指紋一致，但實務註解沒有進到圖譜；"
                     "審圖時查圖譜會查不到這些訓練成果")
        lines.append(format_notes(notes))
        lines.append(f"→ {practice_note_graph.MERGE_HINT}")
        lines.append("  合併後重新執行 python3 tools/graph_status.py stamp 蓋章。")
        return "\n".join(lines)

    diff = result["diff"]
    total = sum(len(v) for v in diff.values())
    lines.append(f"⛔ 已過期 —— {total} 個圖譜來源檔在上次重建後有異動，"
                 "後續工作流程查到的會是舊圖譜")
    for label, key in (("新增", "added"), ("刪除", "removed"), ("變更", "changed")):
        for path in diff[key]:
            lines.append(f"  [{label}] {path}")
    lines.append(format_notes(notes))
    lines.append(f"→ {REBUILD_HINT}")
    return "\n".join(lines)


def cmd_check(args):
    result = evaluate(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_check(result))
    return EXIT_CODES[result["state"]]


def cmd_stamp(args):
    root = Path(args.root)
    sources = collect_sources(root)
    if not sources:
        print("⛔ 找不到任何圖譜來源檔，請確認執行目錄為專案根目錄", file=sys.stderr)
        return 1

    # 蓋章＝宣告「圖譜已跟上來源檔」。實務註解沒併進圖譜就蓋章，等於蓋出假綠燈。
    notes = practice_note_graph.check(root)
    if notes["state"] != "covered" and not args.allow_missing_notes:
        print(practice_note_graph.format_check(notes), file=sys.stderr)
        print(f"\n⛔ 拒絕蓋章：實務註解尚未併入圖譜。{practice_note_graph.MERGE_HINT}\n"
              "   （確知本次不需納入註解時，才用 --allow-missing-notes 強制蓋章）", file=sys.stderr)
        return 2

    previous = load_fingerprint(root) or {}
    doc = {
        "schema_version": 1,
        "note": "圖譜來源檔 sha256 指紋；graph_status.py check 以此判斷圖譜是否跟上規則庫。"
                "重建圖譜後必須重新蓋章。",
        "stamped_at": args.date,
        "graph": graph_scale(root),
        "practice_notes_merged": notes["merged"],
        "source_count": len(sources),
        "sources": sources,
    }
    if args.reason:
        doc["stamp_reason"] = args.reason
        doc["previous_stamped_at"] = previous.get("stamped_at")
    out = root / FINGERPRINT_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    scale = doc["graph"]
    scale_text = f"（圖譜 {scale['nodes']} 節點／{scale['edges']} 邊）" if scale else "（圖譜檔未讀取）"
    print(f"✅ 已蓋章 {out.as_posix()}：{len(sources)} 個來源檔 {scale_text}")
    return 0


def today():
    from datetime import date
    return date.today().isoformat()


def build_parser():
    p = argparse.ArgumentParser(description="法規知識圖譜新鮮度把關")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check",
                       help="檢查圖譜是否跟上規則庫與註解庫（0=新鮮 2=過期／註解未納入 3=尚未建立基準）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("stamp", help="重建圖譜並併入註解層後蓋章，記錄當前來源指紋")
    s.add_argument("--date", default=None, help="蓋章日期（預設今天）")
    s.add_argument("--allow-missing-notes", action="store_true",
                   help="實務註解尚未併入圖譜時仍強制蓋章（會蓋出查不到註解的圖譜，非必要不要用）")
    s.add_argument("--reason",
                   help="蓋章事由；非「重建圖譜後蓋章」的情形（例如追蹤清單修正後重新建立基準）必填，"
                        "會連同前一次蓋章日期寫進指紋檔供追溯")
    s.set_defaults(func=cmd_stamp)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "date", "skip") is None:
        args.date = today()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

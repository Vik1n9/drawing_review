#!/usr/bin/env python3
"""法規知識圖譜新鮮度把關：偵測圖譜來源檔異動，確保後續工作流程查到的是最新圖譜。

只用 Python 標準庫。

    python3 tools/graph_status.py check   # 0=新鮮 2=過期 3=尚未建立基準
    python3 tools/graph_status.py stamp   # 重建圖譜後蓋章（記錄當前來源指紋）

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
import sys
from pathlib import Path

FINGERPRINT_PATH = "graphify-out/source_fingerprint.json"
GRAPH_PATH = "graphify-out/graph.json"

# 圖譜來源檔。前三項與 graphify-out/manifest.json 的 key 集合一致（法典層）；
# practice_notes/active/ 是註解層——實務註解也是後續案件要查到的知識節點，
# 新增註解同樣代表圖譜該重建了。
SOURCE_GLOBS = [
    "rules/equipment_rules.json",
    "rules/mixed_use_rules.json",
    "rules/regulation_articles/article-*.json",
    "practice_notes/active/*.json",
]

REBUILD_HINT = (
    "重建圖譜：/graphify rules --update（增量）或 /graphify rules（大改）；"
    "graphify 未安裝先跑 bash tools/setup.sh --with-graph。"
    "重建完成後務必執行 python3 tools/graph_status.py stamp 蓋章。"
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
            matches = sorted(root.glob(pattern))
        else:
            candidate = root / pattern
            matches = [candidate] if candidate.is_file() else []
        for path in matches:
            found[path.relative_to(root).as_posix()] = sha256_file(path)
    return dict(sorted(found.items()))


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
    """圖譜新鮮度評估結果（供 training_intake.py status 直接取用）。"""
    current = collect_sources(root)
    doc = load_fingerprint(root)
    if doc is None:
        return {
            "state": "no_baseline",
            "source_count": len(current),
            "diff": {"added": sorted(current), "removed": [], "changed": []},
            "stamped_at": None,
        }
    changes = diff_sources(doc.get("sources", {}), current)
    stale = any(changes.values())
    return {
        "state": "stale" if stale else "fresh",
        "source_count": len(current),
        "diff": changes,
        "stamped_at": doc.get("stamped_at"),
    }


EXIT_CODES = {"fresh": 0, "stale": 2, "no_baseline": 3}


def format_check(result):
    lines = ["== 法規圖譜新鮮度 =="]
    if result["state"] == "fresh":
        lines.append(f"✅ 新鮮 —— {result['source_count']} 個來源檔與圖譜指紋一致"
                     f"（蓋章時間：{result['stamped_at'] or '未記錄'}）")
        return "\n".join(lines)

    if result["state"] == "no_baseline":
        lines.append(f"⚠️ 尚未建立基準 —— 找不到 {FINGERPRINT_PATH}，無法判斷圖譜是否跟上"
                     f"（目前 {result['source_count']} 個來源檔）")
        lines.append("→ 確認 graphify-out/ 圖譜為當前規則庫所建之後，執行："
                     " python3 tools/graph_status.py stamp")
        return "\n".join(lines)

    diff = result["diff"]
    total = sum(len(v) for v in diff.values())
    lines.append(f"⛔ 已過期 —— {total} 個圖譜來源檔在上次重建後有異動，"
                 "後續工作流程查到的會是舊圖譜")
    for label, key in (("新增", "added"), ("刪除", "removed"), ("變更", "changed")):
        for path in diff[key]:
            lines.append(f"  [{label}] {path}")
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
    doc = {
        "schema_version": 1,
        "note": "圖譜來源檔 sha256 指紋；graph_status.py check 以此判斷圖譜是否跟上規則庫。"
                "重建圖譜後必須重新蓋章。",
        "stamped_at": args.date,
        "graph": graph_scale(root),
        "source_count": len(sources),
        "sources": sources,
    }
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

    s = sub.add_parser("check", help="檢查圖譜是否跟上規則庫（0=新鮮 2=過期 3=尚未建立基準）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("stamp", help="重建圖譜後蓋章，記錄當前來源指紋")
    s.add_argument("--date", default=None, help="蓋章日期（預設今天）")
    s.set_defaults(func=cmd_stamp)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "date", "skip") is None:
        args.date = today()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

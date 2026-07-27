#!/usr/bin/env python3
"""兩個圖譜的新鮮度把關：法規圖譜與訓練圖譜**各自獨立**檢查、各自蓋章。

只用 Python 標準庫。

    python3 tools/graph_status.py check                    # 兩個圖譜分段回報（0=都跟上）
    python3 tools/graph_status.py stamp --graph regulation # 法規圖譜重建後蓋章
    python3 tools/graph_status.py stamp --graph training   # 訓練圖譜建置後（通常不需要，見下）

**為什麼是兩個圖譜。** 早期法規與訓練成果混在同一個 `graph.json`：法典層一重建就會把
訓練層沖掉，於是每次重建都被迫「先把註解併回去才准蓋章」，把兩件本來各自獨立的事綁成
一條必須全過的鏈——鏈上任一環卡住，訓練成果就進不了圖譜。分家之後兩者互不阻擋，
使用者說「更新圖譜」時可以只更新真正過期的那一個。

**兩者的把關方式刻意不同：**

- **法規圖譜**（`graphify-out/graph.json`，與上游共編）用 **sha256 逐檔指紋**
  （`graphify-out/source_fingerprint.json`）。不沿用 graphify 自己的 `manifest.json`：
  它記的是 `mtime`，全新 clone 之後所有檔案的 mtime 都會重置，會整批誤報「過期」。
- **訓練圖譜**（`training/graph.json`，純使用者所有）**不需要指紋檔**。它是衍生產物，
  圖譜裡每個節點都帶著來源素材的語意摘要，直接比對就知道跟不跟得上——
  少一個要維護的狀態檔，就少一種對不上的可能。

邊界（呼應 AGENTS.md 底線 1、2）：圖譜只是索引與導覽，不是門檻數值來源。
本工具只回答「圖譜有沒有跟上素材」，不回答任何法規判斷。
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tools import practice_note_graph, training_graph_build
except ImportError:
    import practice_note_graph  # noqa: F401  （其他模組沿用 graph_status.practice_note_graph）
    import training_graph_build

FINGERPRINT_PATH = "graphify-out/source_fingerprint.json"
GRAPH_PATH = training_graph_build.REGULATION_GRAPH_PATH
TRAINING_GRAPH_PATH = training_graph_build.TRAINING_GRAPH_PATH
GRAPH_PENDING_PATH = "training/graph_pending.json"

# 法規圖譜的來源檔＝**圖譜真的從中抽出節點的檔案**。
#
# 不含 rules/equipment_rules.json 與 rules/mixed_use_rules.json：這兩個檔在 graphify 的
# manifest 裡（掃描範圍涵蓋），但 graph.json 的節點沒有任何一個出自它們
# （node.source_file 只有 core/ 底下的全文 md、附表 PDF、附表圖檔與 rules/README.md）。
# 把它們列入追蹤，會讓每一次先紅再綠改參數都誤報「圖譜過期」，而重建出來的圖譜完全相同。
# 這個「未產生節點就不追蹤」的前提由 untracked_graph_sources() 持續驗證。
#
# 也**不含** practice_notes/：實務註解現在屬於訓練圖譜，改一則註解不該害法規圖譜判過期。
REGULATION_SOURCE_GLOBS = [
    "rules/core/**/*",
    "rules/README.md",
    "rules/regulation_articles/article-*.json",
]

# 相容別名：外部仍以 SOURCE_GLOBS 稱呼法規圖譜的來源清單。
SOURCE_GLOBS = REGULATION_SOURCE_GLOBS

# graph.json 的 node.source_file 是相對於 graphify 執行根目錄（本專案為 rules/）的路徑。
# rules/ 要先試——否則 rules/README.md 會被誤判成 repo 根目錄的 README.md。
GRAPH_SOURCE_PREFIXES = ["rules/", ""]

REBUILD_HINT = (
    "重建法規圖譜（零安裝、不需 API key）："
    "python3 tools/regulation_graph_build.py plan → 依契約做語意抽取 → "
    "python3 tools/regulation_graph_build.py rebuild --commit → "
    "python3 tools/graph_status.py stamp --graph regulation。"
    "外部 graphify 為選用（視覺化與 CLI 查詢），不裝也能完整重建。"
)

TRAINING_HINT = training_graph_build.BUILD_HINT


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_sources(root=".", globs=None):
    """回傳 {repo 相對路徑: sha256}，路徑一律以 posix 形式排序輸出。"""
    root = Path(root)
    found = {}
    for pattern in (globs or REGULATION_SOURCE_GLOBS):
        if "*" in pattern:
            matches = sorted(p for p in root.glob(pattern) if p.is_file())
        else:
            candidate = root / pattern
            matches = [candidate] if candidate.is_file() else []
        for path in matches:
            found[path.relative_to(root).as_posix()] = sha256_file(path)
    return dict(sorted(found.items()))


def untracked_graph_sources(root=".", tracked=None):
    """法規圖譜裡有節點、卻不在追蹤清單內的來源檔。

    REGULATION_SOURCE_GLOBS 刻意不追蹤「掃描得到但不產生節點」的檔案（見上方說明）。
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


def graph_scale(root=".", path=None):
    """讀圖譜規模作為蓋章時的佐證；圖譜不存在或格式不符時回 None。"""
    path = Path(root) / (path or GRAPH_PATH)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return {"nodes": len(doc.get("nodes", [])),
            "edges": len(doc.get("links", doc.get("edges", [])))}


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


def load_graph_pending(root="."):
    """training/graph_pending.json：上次重建失敗／中斷留下的待辦。

    文件一直宣稱「CI 的 graph_status.py check 也會紅燈」，但以前本工具根本不讀這個檔。
    現在讀了，那句話才是真的。
    """
    return practice_note_graph.load_json(Path(root) / GRAPH_PENDING_PATH)


# ---------------------------------------------------------------------------
# 法規圖譜

def evaluate_regulation(root="."):
    current = collect_sources(root, REGULATION_SOURCE_GLOBS)
    untracked = untracked_graph_sources(root, current)
    doc = load_fingerprint(root)
    if doc is None:
        return {"state": "no_baseline", "source_count": len(current),
                "diff": {"added": sorted(current), "removed": [], "changed": []},
                "stamped_at": None, "untracked_sources": untracked,
                "excluded_notes": []}
    changes = diff_sources(doc.get("sources", {}), current)
    if untracked:
        state = "untracked_sources"
    elif any(changes.values()):
        state = "stale"
    else:
        state = "fresh"
    return {"state": state, "source_count": len(current), "diff": changes,
            "stamped_at": doc.get("stamped_at"), "untracked_sources": untracked,
            "excluded_notes": doc.get("practice_notes_excluded") or []}


# ---------------------------------------------------------------------------
# 訓練圖譜

def evaluate_training(root="."):
    coverage = training_graph_build.check(root)
    pending = load_graph_pending(root)
    state = coverage["state"]
    if pending and state in training_graph_build.OK_STATES:
        state = "rebuild_pending"
    return {"state": state, "coverage": coverage, "graph_pending": pending,
            "scale": graph_scale(root, TRAINING_GRAPH_PATH)}


# ---------------------------------------------------------------------------
# 合併評估

REGULATION_EXIT = {"fresh": 0, "stale": 2, "untracked_sources": 2, "no_baseline": 3}
TRAINING_EXIT = {"covered": 0, "not_built": 0, "uncovered": 2, "absent": 2,
                 "rebuild_pending": 2}


def evaluate(root="."):
    """兩個圖譜各自的評估結果。

    頂層仍保留 `state`／`source_count`／`diff`／`stamped_at`／`notes` 等舊欄位，
    指向**法規圖譜**——onboarding.py 與 training_intake.py 沿用這些鍵，
    分家不該逼著每個顯示端同步大改。
    """
    regulation = evaluate_regulation(root)
    training = evaluate_training(root)
    reg_exit = REGULATION_EXIT.get(regulation["state"], 2)
    train_exit = TRAINING_EXIT.get(training["state"], 2)
    return {
        "regulation": regulation,
        "training": training,
        "exit_code": max(reg_exit, train_exit),
        # 相容欄位（皆為法規圖譜的視角）
        "state": regulation["state"],
        "source_count": regulation["source_count"],
        "diff": regulation["diff"],
        "stamped_at": regulation["stamped_at"],
        "untracked_sources": regulation["untracked_sources"],
        "notes": training["coverage"],
    }


def format_regulation(result):
    lines = ["== 法規圖譜 =="]
    if result["state"] == "fresh":
        lines.append(f"✅ 新鮮 —— {result['source_count']} 個來源檔與圖譜指紋一致"
                     f"（蓋章時間：{result['stamped_at'] or '未記錄'}）")
        if result["excluded_notes"]:
            lines.append(f"⚠️ 上次蓋章時排除了 {len(result['excluded_notes'])} 則實務註解："
                         f"{'、'.join(result['excluded_notes'])}")
        return "\n".join(lines)

    if result["state"] == "no_baseline":
        lines.append(f"⚠️ 尚未建立基準 —— 找不到 {FINGERPRINT_PATH}，無法判斷圖譜是否跟上"
                     f"（目前 {result['source_count']} 個來源檔）")
        lines.append("→ 確認圖譜為當前規則庫所建之後，執行："
                     " python3 tools/graph_status.py stamp --graph regulation")
        return "\n".join(lines)

    if result["state"] == "untracked_sources":
        lines.append("⛔ 追蹤清單漏檔 —— 圖譜有節點出自下列檔案，但它們不在 "
                     "graph_status.py 的 REGULATION_SOURCE_GLOBS 內；這些檔改了不會被偵測到")
        for path in result["untracked_sources"]:
            lines.append(f"  [未追蹤] {path}")
        lines.append("→ 把上列路徑加進 REGULATION_SOURCE_GLOBS，再重新蓋章")
        return "\n".join(lines)

    diff = result["diff"]
    total = sum(len(v) for v in diff.values())
    lines.append(f"⛔ 已過期 —— {total} 個來源檔在上次重建後有異動，查到的會是舊圖譜")
    for label, key in (("新增", "added"), ("刪除", "removed"), ("變更", "changed")):
        for path in diff[key]:
            lines.append(f"  [{label}] {path}")
    lines.append(f"→ {REBUILD_HINT}")
    return "\n".join(lines)


def format_training(result):
    lines = [training_graph_build.format_check(result["coverage"])]
    if result["graph_pending"]:
        pending = result["graph_pending"]
        lines.append(f"⛔ 上次圖譜重建未完成（{GRAPH_PENDING_PATH}）："
                     f"{pending.get('reason') or pending.get('批次') or '未記原因'}")
        lines.append("→ 補建完成後刪除該檔")
    return "\n".join(lines)


def format_check(result):
    """兩段式輸出：法規圖譜與訓練圖譜分開講，使用者才知道該更新哪一個。"""
    if "regulation" not in result:      # 舊格式（僅法規圖譜）
        return format_regulation(result)
    return f"{format_regulation(result['regulation'])}\n\n{format_training(result['training'])}"


# ---------------------------------------------------------------------------
# CLI

def cmd_check(args):
    result = evaluate(args.root)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_check(result))
    return result["exit_code"]


def _stamp_regulation(root, args):
    sources = collect_sources(root, REGULATION_SOURCE_GLOBS)
    if not sources:
        print("⛔ 找不到任何圖譜來源檔，請確認執行目錄為專案根目錄", file=sys.stderr)
        return 1

    # 蓋章＝宣告「圖譜已跟上來源檔」。註解沒進訓練圖譜就蓋章不會讓法規圖譜出錯，
    # 但使用者會以為「圖譜更新完了」——所以照樣要擋，並且把被排除者記在指紋裡持續提醒。
    coverage = training_graph_build.check(root)
    excluded = []
    if coverage["state"] not in training_graph_build.OK_STATES:
        if not args.allow_missing_notes:
            print(training_graph_build.format_check(coverage), file=sys.stderr)
            print("\n⛔ 拒絕蓋章：訓練圖譜尚未跟上素材。"
                  f"{training_graph_build.BUILD_HINT}\n"
                  "   （確知本次不需納入訓練成果時，才用 --allow-missing-notes "
                  "並以 --reason 說明原因）", file=sys.stderr)
            return 2
        if not args.reason:
            print("⛔ --allow-missing-notes 會蓋出「只有法規、查不到訓練成果」的綠燈，"
                  "必須以 --reason 說明原因供追溯", file=sys.stderr)
            return 1
        excluded = sorted(set(coverage["missing"]) | set(coverage["stale"]))

    previous = load_fingerprint(root) or {}
    doc = {
        "schema_version": 2,
        "note": "法規圖譜來源檔 sha256 指紋；graph_status.py check 以此判斷圖譜是否跟上規則庫。"
                "重建圖譜後必須重新蓋章。訓練圖譜不用指紋檔——它以節點內的語意摘要自證。",
        "stamped_at": args.date,
        "graph": graph_scale(root),
        "source_count": len(sources),
        "sources": sources,
    }
    if excluded:
        doc["practice_notes_excluded"] = excluded
        doc["excluded_reason"] = args.reason
        doc["excluded_at"] = args.date
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
    if excluded:
        print(f"⚠️ 本次排除了 {len(excluded)} 則訓練成果（{'、'.join(excluded)}）"
              "——check 會持續紅字提醒，直到補建訓練圖譜")
    return 0


def _stamp_training(root):
    """訓練圖譜沒有指紋檔可蓋——直接回報它跟不跟得上。"""
    coverage = training_graph_build.check(root)
    print(training_graph_build.format_check(coverage))
    if coverage["state"] in training_graph_build.OK_STATES:
        print("ℹ️ 訓練圖譜不需要蓋章：它以節點內的語意摘要自證，check 隨時比對得出來。")
        return 0
    return 2


def cmd_stamp(args):
    root = Path(args.root)
    if args.graph == "training":
        return _stamp_training(root)
    code = _stamp_regulation(root, args)
    if args.graph == "all" and code == 0:
        return _stamp_training(root)
    return code


def today():
    from datetime import date
    return date.today().isoformat()


def build_parser():
    p = argparse.ArgumentParser(description="法規圖譜與訓練圖譜的新鮮度把關（各自獨立）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check",
                       help="兩個圖譜是否各自跟上素材（0=都跟上 2=有過期 3=法規圖譜尚無基準）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("stamp", help="重建圖譜後蓋章，記錄當前來源指紋")
    s.add_argument("--graph", choices=("regulation", "training", "all"), default="regulation",
                   help="要蓋哪一個圖譜（預設 regulation；訓練圖譜不需要蓋章）")
    s.add_argument("--date", default=None, help="蓋章日期（預設今天）")
    s.add_argument("--allow-missing-notes", action="store_true",
                   help="訓練圖譜尚未跟上時仍強制蓋法規圖譜（須附 --reason；"
                        "被排除的訓練成果會記進指紋並持續紅字）")
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

#!/usr/bin/env python3
"""法規知識圖譜查詢工具 for fire-review（免安裝 graphify，直接讀 graph.json）。

用途是**定位**：先問圖譜「這件事牽涉哪幾條」，再只載入那幾條原文核對，
避免把 §14~§31 全部塞進 context。

    圖譜（定位條號與關聯）→ regulation_index.py lookup（載入條文原文）→ 判斷

**邊界（審圖最高原則 2、4）**：圖譜只是索引與導覽，**不是門檻數值或計算結果的來源**。
節點標題不得當作法規數值使用；任何應設／免設判斷與數量計算一律仍以
`tools/fire_code_calc.py` ＋人工確認後的 `case.json` 為準，數值須回法條原文核對。

Zero external dependencies — Python stdlib only。graphify 未安裝時本工具仍可用。

Usage:
    python3 tools/regulation_graph.py neighbors --article §24
    python3 tools/regulation_graph.py articles --equipment 排煙設備
    python3 tools/regulation_graph.py path --from 無開口樓層 --to 排煙設備
    python3 tools/regulation_graph.py notes --article §19        # 該條的實務註解
    python3 tools/regulation_graph.py neighbors --article §18 --format json

**實務註解（訓練成果）**：`/practice-note` 納入的註解經語意抽取後也是圖譜節點，
`neighbors`／`articles` 的輸出會一併帶出，另有 `notes` 子指令專查。註解是實務見解、
**不是法規條文**——援引時必須同時列出所補充的法條與註解 ID（輸出會附此警語）。
"""

import argparse
import json
import os
import re
import sys
from collections import deque

DEFAULT_GRAPH = os.path.join("graphify-out", "graph.json")

PRACTICE_NOTE_LAYER = "practice_note"

BOUNDARY = ("圖譜只是索引與導覽，不是門檻數值來源；判斷前務必以 "
            "`python3 tools/regulation_index.py lookup --article '{articles}'` 載入原文核對。")

NOTE_NOTICE = ("實務註解為消防專業人員確認之實務見解，非法規條文；"
               "援引時須同時列出所補充的法條與註解 ID")


def load_graph(path):
    if not os.path.exists(path):
        sys.exit(f"找不到圖譜 {path}。法規更新後請重跑 /graphify rules 重建。")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    nodes = {n["id"]: n for n in doc["nodes"]}
    out, into = {}, {}
    for edge in doc["links"]:
        out.setdefault(edge["source"], []).append(edge)
        into.setdefault(edge["target"], []).append(edge)
    return nodes, out, into


def label(nodes, node_id):
    return (nodes.get(node_id) or {}).get("label", node_id)


def article_label(text):
    """'§24' / '24' / '第24條' / '§22-1' → '第24條' / '第22-1條'。"""
    match = re.search(r"(\d+(?:-\d+)?)", str(text))
    return f"第{match.group(1)}條" if match else None


def resolve(nodes, term, exact_label=None):
    """查詢字串 → 節點 id 清單（先精確 label，再子字串）。"""
    wanted = exact_label or term
    hits = [i for i, n in nodes.items() if n.get("label") == wanted]
    if hits:
        return hits
    return [i for i, n in nodes.items() if wanted in str(n.get("label", ""))]


def article_numbers(node_ids, nodes):
    """節點清單 → 排序後的條號字串（供 lookup 一次載入）。"""
    numbers = []
    for node_id in node_ids:
        match = re.fullmatch(r"第(\d+(?:-\d+)?)條", str(label(nodes, node_id)))
        if match:
            numbers.append(match.group(1))
    def key(n):
        head, _, tail = n.partition("-")
        return (int(head), int(tail) if tail else 0)
    return [f"§{n}" for n in sorted(set(numbers), key=key)]


def is_note(node):
    return (node or {}).get("layer") == PRACTICE_NOTE_LAYER and bool((node or {}).get("note_id"))


def note_entry(node, relation=None):
    """實務註解節點 → 查詢輸出用的摘要（一律帶警語欄位）。"""
    return {
        "note_id": node.get("note_id"),
        "relation": relation,
        "ref_article": node.get("ref_article"),
        "equipment": node.get("equipment"),
        "decision": node.get("decision"),
        "summary": node.get("graph_summary") or node.get("scenario_summary"),
        "source_case": node.get("source_case"),
        "path": node.get("source_file"),
        "notice": NOTE_NOTICE,
    }


def notes_touching(node_ids, nodes, out, into):
    """哪些實務註解連到這些節點（註解節點恆為邊的起點，故看 incoming）。"""
    found = {}
    for node_id in node_ids:
        for edge in into.get(node_id, []) + out.get(node_id, []):
            for other_id in (edge["source"], edge["target"]):
                node = nodes.get(other_id)
                if is_note(node) and node["note_id"] not in found:
                    found[node["note_id"]] = note_entry(node, edge.get("relation"))
    return [found[k] for k in sorted(found)]


def cmd_neighbors(args, nodes, out, into):
    target = article_label(args.article)
    if not target:
        sys.exit(f"無法解析條號 {args.article!r}，請用 §24 或 24 的形式。")
    hits = resolve(nodes, target, exact_label=target)
    if not hits:
        sys.exit(f"圖譜中找不到 {target}。可能該條未入圖譜，請直接查 rules/regulation_articles/。")
    node_id = hits[0]

    groups = {"引用（本條 → 他條/概念）": [], "被引用（他條 → 本條）": [], "附表圖檔": []}
    for edge in out.get(node_id, []):
        other = nodes.get(edge["target"], {})
        if is_note(other):
            continue
        entry = {"relation": edge["relation"], "label": other.get("label", edge["target"]),
                 "type": other.get("file_type")}
        groups["附表圖檔" if other.get("file_type") == "image" else "引用（本條 → 他條/概念）"].append(entry)
    for edge in into.get(node_id, []):
        other = nodes.get(edge["source"], {})
        if is_note(other):
            continue  # 實務註解另立區塊，不混在條文引用網裡
        if other.get("file_type") == "image":
            groups["附表圖檔"].append({"relation": edge["relation"],
                                       "label": other.get("label", edge["source"]),
                                       "type": "image"})
        else:
            groups["被引用（他條 → 本條）"].append({"relation": edge["relation"],
                                                    "label": other.get("label", edge["source"]),
                                                    "type": other.get("file_type")})

    related = article_numbers(
        [e["target"] for e in out.get(node_id, [])] + [e["source"] for e in into.get(node_id, [])], nodes)
    payload = {"article": target, "groups": groups,
               "related_articles": related,
               "practice_notes": notes_touching([node_id], nodes, out, into),
               "lookup_hint": BOUNDARY.format(articles=",".join([f"§{target[1:-1]}"] + related))}
    return payload


def cmd_articles(args, nodes, out, into):
    hits = resolve(nodes, args.equipment)
    if not hits:
        sys.exit(f"圖譜中找不到「{args.equipment}」。可換個詞，或直接用 "
                 f"`regulation_index.py lookup --equipment '{args.equipment}'`。")
    found = {}
    for node_id in hits:
        for edge in into.get(node_id, []):
            source = nodes.get(edge["source"], {})
            if re.fullmatch(r"第\d+(?:-\d+)?條", str(source.get("label", ""))):
                found[edge["source"]] = edge["relation"]
    articles = article_numbers(list(found), nodes)
    return {"equipment": args.equipment,
            "matched_nodes": [label(nodes, h) for h in hits if not is_note(nodes.get(h))],
            "articles": articles,
            "practice_notes": notes_touching(hits, nodes, out, into),
            "lookup_hint": BOUNDARY.format(articles=",".join(articles) or "§14-§31")}


def cmd_notes(args, nodes, out, into):
    """專查實務註解：某條文的、某設備的，或全部。"""
    all_notes = [n for n in nodes.values() if is_note(n)]
    scope = "全部"
    if args.article:
        target = article_label(args.article)
        if not target:
            sys.exit(f"無法解析條號 {args.article!r}，請用 §19 或 19 的形式。")
        hits = [i for i, n in nodes.items() if n.get("label") == target]
        entries = notes_touching(hits, nodes, out, into) if hits else []
        scope = target
    elif args.equipment:
        hits = [i for i, n in nodes.items() if args.equipment in str(n.get("label", ""))
                and not is_note(n)]
        entries = [e for e in notes_touching(hits, nodes, out, into)]
        entries += [note_entry(n) for n in all_notes
                    if args.equipment in str(n.get("equipment") or "")
                    and n["note_id"] not in {e["note_id"] for e in entries}]
        entries.sort(key=lambda e: e["note_id"])
        scope = args.equipment
    else:
        entries = sorted((note_entry(n) for n in all_notes), key=lambda e: e["note_id"])
    return {"scope": scope, "practice_notes": entries, "note_notice": NOTE_NOTICE,
            "lookup_hint": BOUNDARY.format(
                articles=",".join(sorted({f"§{str(e['ref_article'] or '')[1:-1]}"
                                          for e in entries if e.get("ref_article")}))
                or "§14-§31")}


def cmd_path(args, nodes, out, into):
    starts = resolve(nodes, getattr(args, "from"))
    goals = set(resolve(nodes, args.to))
    if not starts or not goals:
        sys.exit("起點或終點在圖譜中找不到對應節點。")
    queue = deque([[s] for s in starts])
    seen = set(starts)
    while queue:
        route = queue.popleft()
        current = route[-1]
        if current in goals and len(route) > 1:
            return {"path": [label(nodes, n) for n in route],
                    "related_articles": article_numbers(route, nodes),
                    "lookup_hint": BOUNDARY.format(articles=",".join(article_numbers(route, nodes)) or "§14-§31")}
        if len(route) > args.max_depth:
            continue
        for edge in out.get(current, []) + into.get(current, []):
            for nxt in (edge["source"], edge["target"]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(route + [nxt])
    return {"path": [], "related_articles": [], "lookup_hint": "圖譜中兩者無可達路徑。"}


def render_notes(entries):
    lines = ["\n## 實務註解（實務見解，非法規條文）"]
    for entry in entries:
        head = f"- [{entry['note_id']}] "
        if entry.get("ref_article"):
            head += f"補充 {entry['ref_article']}"
        if entry.get("equipment"):
            head += f"｜{entry['equipment']}"
        if entry.get("decision"):
            head += f"｜{entry['decision']}"
        lines.append(head)
        if entry.get("summary"):
            lines.append(f"    {entry['summary']}")
        if entry.get("path"):
            lines.append(f"    來源：{entry['path']}"
                         + (f"（案件：{entry['source_case']}）" if entry.get("source_case") else ""))
    lines.append(f"⚠️ {NOTE_NOTICE}。")
    return lines


def render(payload):
    lines = []
    if "scope" in payload:
        lines.append(f"# 實務註解查詢：{payload['scope']}")
        if payload["practice_notes"]:
            lines.extend(render_notes(payload["practice_notes"]))
        else:
            lines.append("（查無實務註解。註解須經 /practice-note「確認納入」並語意抽取後併入圖譜——"
                         "以 `python3 tools/practice_note_graph.py check` 確認納入狀態。）")
        lines.append(f"\n⚠️ {payload['lookup_hint']}")
        return "\n".join(lines)
    if "groups" in payload:
        lines.append(f"# {payload['article']} 圖譜關聯")
        for name, entries in payload["groups"].items():
            if not entries:
                continue
            lines.append(f"\n## {name}")
            for entry in entries:
                lines.append(f"- [{entry['relation']}] {entry['label']}")
    elif "equipment" in payload:
        lines.append(f"# 規範「{payload['equipment']}」的條文")
        lines.append("（圖譜比對到的節點：" + "、".join(payload["matched_nodes"]) + "）")
        lines.append("\n" + ("、".join(payload["articles"]) if payload["articles"] else "（無）"))
    else:
        lines.append("# 關聯路徑")
        lines.append(" → ".join(payload["path"]) if payload["path"] else "（無可達路徑）")
    if payload.get("related_articles"):
        lines.append("\n## 相關條號\n" + "、".join(payload["related_articles"]))
    if payload.get("practice_notes"):
        lines.extend(render_notes(payload["practice_notes"]))
    lines.append(f"\n⚠️ {payload['lookup_hint']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="法規知識圖譜查詢（定位條號與關聯，非門檻數值來源）")
    parser.add_argument("--graph", default=DEFAULT_GRAPH, help="graph.json 路徑")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    sub = parser.add_subparsers(dest="command", required=True)

    neighbors = sub.add_parser("neighbors", help="某條文的引用網（引用／被引用／附表圖）")
    neighbors.add_argument("--article", required=True, help="條號，例：§24 或 24")
    neighbors.set_defaults(func=cmd_neighbors)

    articles = sub.add_parser("articles", help="哪些條文規範某設備")
    articles.add_argument("--equipment", required=True, help="設備名稱，例：排煙設備")
    articles.set_defaults(func=cmd_articles)

    notes = sub.add_parser("notes", help="實務註解查詢（某條文／某設備／全部）")
    notes.add_argument("--article", default=None, help="條號，例：§19 或 19")
    notes.add_argument("--equipment", default=None, help="設備名稱，例：自動撒水設備")
    notes.set_defaults(func=cmd_notes)

    path = sub.add_parser("path", help="兩概念間的最短關聯路徑")
    path.add_argument("--from", required=True, dest="from", help="起點概念")
    path.add_argument("--to", required=True, help="終點概念")
    path.add_argument("--max-depth", type=int, default=4)
    path.set_defaults(func=cmd_path)

    args = parser.parse_args(argv)
    nodes, out, into = load_graph(args.graph)
    payload = args.func(args, nodes, out, into)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.format == "json" else render(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())

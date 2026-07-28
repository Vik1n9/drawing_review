#!/usr/bin/env python3
"""法規圖譜重建：確定性骨架 ＋ 保留式語意層。**零安裝、不需要任何 API key。**

只用 Python 標準庫。

    python3 tools/regulation_graph_build.py plan        # 哪些切塊的語意層該重抽（0=齊備 2=有待辦）
    python3 tools/regulation_graph_build.py contract --chunk {id}   # 印契約給對話中的模型填
    python3 tools/regulation_graph_build.py validate --extraction graphify-out/regulation_extractions/{id}.json
    python3 tools/regulation_graph_build.py rebuild     # 產生 graph.rebuilt.json（不覆寫）
    python3 tools/regulation_graph_build.py verify      # 與現行圖譜的差異報表
    python3 tools/regulation_graph_build.py rebuild --commit   # verify 全綠才覆寫 graph.json

**為什麼要把重建收回第一方。** 原本法典層由外部套件 graphifyy 的 `/graphify rules`
產生，它自帶的語意分割要 LLM API key；而 Claude Code 環境只有 OAuth、沒有
`ANTHROPIC_API_KEY`，於是使用者一要更新圖譜就被要求填一把空的金鑰，整條路卡死。
語意工作本來就是由對話中的模型做的（`graphify-out/cost.json` 歷次 run 都是
`input_tokens: 0`），所以正解是把契約寫清楚、讓對話中的模型直接填，不繞外部 API。

**三個不變式，都是為了不要悄悄弄壞既有圖譜：**

1. **不重算 id，只沿用 id。** 既有 id 有四套並存的命名規則，其中 PDF 抽出的用途概念
   （`concept_甲類一_電影片映演場所` ← label `甲類（一）電影片映演場所（戲院、電影院）`）
   是被縮寫過的，**無法從 label 反推**。所以以 `(source_file, label)` 為主鍵查台帳
   `graphify-out/node_ledger.json` 沿用舊 id，只有真正的新 label 才鑄新 id。
   訓練圖譜的跨圖譜參照也靠這條線活著。
2. **重建只增不減。** 確定性 pass 重建條文與附表節點；概念節點與語意邊一律**原樣保留**，
   只有當邊的端點真的消失時才會不見。確定性抽出的引用只在「該對節點之間還沒有任何邊」
   時才新增——不去「更正」既有邊的關聯類型，那種歸位會產生大量無法人工覆核的 diff。
3. **預設不覆寫。** `rebuild` 寫到 `graph.rebuilt.json`；`--commit` 才覆寫，而且會先跑
   `verify`，紅燈類別非 0 就不寫。

邊界（呼應 AGENTS.md 底線 1、2）：圖譜只是索引與導覽，不是門檻數值來源。
本工具不產生任何門檻數值，也不從條文推導法規判斷。
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()
try:
    from tools import graph_labels, practice_note_graph, training_graph_build
except ImportError:
    import graph_labels
    import practice_note_graph
    import training_graph_build

load_json = practice_note_graph.load_json
write_json = practice_note_graph.write_json

GRAPH_PATH = "graphify-out/graph.json"
REBUILT_PATH = "graphify-out/graph.rebuilt.json"
LEDGER_PATH = "graphify-out/node_ledger.json"
EXTRACT_DIR = "graphify-out/regulation_extractions"
ARTICLE_DIR = "rules/regulation_articles"
CORE_DIR = "rules/core"
RULES_README = "rules/README.md"

# graph.json 的 node.source_file 相對於 rules/（graphify 當初的執行根目錄），
# 節點 id 則一律以 rules_ 開頭。兩者都要維持原樣，否則既有 id 對不上。
SOURCE_ROOT = "rules"
ID_PREFIX = "rules_"

DOCUMENT, IMAGE, CONCEPT = "document", "image", "concept"

# 確定性 pass 產生的邊一律標這個信心值，與語意抽取（EXTRACTED）分得開。
MECHANICAL = "MECHANICAL"
EXTRACTED = "EXTRACTED"

# 語意抽取可用的關聯類型——沿用既有圖譜已在用的五種，不擴充。
RELATIONS = ("references", "cites", "conceptually_related_to",
             "semantically_similar_to", "shares_data_with")

EXTRACTION_SCHEMA_VERSION = 1

_ASSET_IMAGE = re.compile(r"^article-(?P<article>[0-9]+(?:-[0-9]+)?)-page-(?P<page>\d+)\.png$")


# ---------------------------------------------------------------------------
# id 台帳

def slug(text):
    """路徑／label → id 片段：非中日文與英數字一律收斂為底線，ASCII 轉小寫。

    ASCII 轉小寫是為了重現既有的 `rules_readme`（來源檔是 `README.md`）。
    """
    cleaned = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", str(text)).strip("_")
    return "".join(c.lower() if c.isascii() else c for c in cleaned)


def mint_id(source_file, label=None):
    """新節點的 id。**只用於台帳查不到的 label**——既有節點一律沿用舊 id。"""
    stem = re.sub(r"\.[0-9A-Za-z]+$", "", str(source_file))
    parts = [ID_PREFIX + slug(stem)]
    if label:
        parts.append(graph_labels.norm_id(label))
    return "_".join(parts)


class Ledger:
    """`(source_file, label) → node id` 的台帳。

    圖譜檔被誤刪時 id 還原得回來——所有抽取檔與訓練圖譜的跨圖譜參照都靠 label→id
    這條線活著，台帳斷了等於訓練成果掛不回法規。
    """

    def __init__(self, records=(), articles=None):
        self._ids = {}
        self._minted = []
        for record in records:
            self._ids[(record.get("source_file"), record.get("label"))] = record.get("id")
        self.articles = dict(articles or {})

    @classmethod
    def load(cls, root):
        doc = load_json(Path(root) / LEDGER_PATH) or {}
        return cls(doc.get("nodes", ()), doc.get("articles"))

    def learn_from_graph(self, graph):
        """既有圖譜就是最權威的台帳來源——重建前先把現況全部認回來。"""
        for node in (graph or {}).get("nodes", []):
            key = (node.get("source_file"), node.get("label"))
            if node.get("id"):
                self._ids.setdefault(key, node["id"])

    def id_for(self, source_file, label, mint_label=None):
        key = (source_file, label)
        if key in self._ids:
            return self._ids[key]
        new_id = mint_id(source_file, mint_label if mint_label is not None else label)
        self._ids[key] = new_id
        self._minted.append({"source_file": source_file, "label": label, "id": new_id})
        return new_id

    @property
    def minted(self):
        return list(self._minted)

    def to_doc(self, articles):
        return {
            "schema_version": 1,
            "note": "節點 id 台帳：重建圖譜時以 (source_file, label) 沿用既有 id，"
                    "不重算。抽取檔與訓練圖譜的跨圖譜參照都依賴 label→id 的穩定性。",
            "nodes": [{"source_file": s, "label": l, "id": i}
                      for (s, l), i in sorted(self._ids.items(),
                                              key=lambda kv: (str(kv[0][0]), str(kv[0][1])))],
            "articles": dict(sorted(articles.items(), key=lambda kv: graph_labels
                                    .article_sort_key(kv[0]))),
        }


# ---------------------------------------------------------------------------
# 素材

def _rel_to_rules(path):
    """repo 相對路徑 → 圖譜用的、相對 rules/ 的 source_file。"""
    text = str(path).replace(os.sep, "/")
    return text[len(SOURCE_ROOT) + 1:] if text.startswith(SOURCE_ROOT + "/") else text


def load_articles(root="."):
    """`rules/regulation_articles/article-*.json` → 依條號排序的條文清單。"""
    directory = Path(root) / ARTICLE_DIR
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("article-*.json")):
        doc = load_json(path)
        if not isinstance(doc, dict) or not doc.get("article_no"):
            continue
        number = graph_labels.parse_article_ref(doc["article_no"])
        if not number:
            continue
        found.append({
            "number": number,
            "label": f"第{number}條",
            "source_file": _rel_to_rules(doc.get("source_file", "")),
            "hierarchy": doc.get("hierarchy") or [],
            "markdown": doc.get("markdown") or "",
            "legal_basis": doc.get("legal_basis"),
            "equipment_tags": doc.get("equipment_tags") or [],
        })
    return sorted(found, key=lambda a: graph_labels.article_sort_key(a["number"]))


def load_assets(root="."):
    """`rules/core/*_assets/article-N-page-P.png` → 附表圖清單。"""
    directory = Path(root) / CORE_DIR
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*_assets/*.png")):
        match = _ASSET_IMAGE.match(path.name)
        if not match:
            continue
        number = graph_labels.parse_article_ref(match.group("article"))
        if not number:
            continue
        found.append({
            "article": number,
            "page": int(match.group("page")),
            "source_file": _rel_to_rules(path.relative_to(Path(root)).as_posix()),
            "label": f"第 {number} 條官方完整條文附件，第 {match.group('page')} 頁",
        })
    return found


def digest_text(markdown):
    """摘要用的條文正規化：**連空白也一起去掉**。

    中文條文裡多一個空格、換行位置不同，都不是語意變更，卻會讓摘要改變而要求重抽。
    顯示用的 `normalize_text` 保留詞間空白，這裡刻意更嚴格。
    """
    return re.sub(r"\s+", "", graph_labels.normalize_text(markdown))


def article_text_sha(article):
    return hashlib.sha256(digest_text(article["markdown"]).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 條文互引（確定性）

_RANGE = re.compile(
    r"第\s*(?:[0-9]+|[〇零一二三四五六七八九十百千]+)\s*條\s*至\s*"
    r"第\s*(?:[0-9]+|[〇零一二三四五六七八九十百千]+)\s*條")


def citations(article, known_numbers, order):
    """條文全文 → 它引用了哪些**本法典**條號（正典條號清單）。

    三條規則，順序敏感：

    1. 外部法排除——`本標準依消防法第六條…` 不是對本標準第 6 條的引用。
       由 `graph_labels.find_article_refs` 處理。
    2. 條號範圍展開——`準用第四十三條至第四十五條` 要展開成實際存在的 43、44、45。
    3. 相對引用——`前條` 指條號序的前一條。`前項`／`前款` 是條**內部**指涉，不建跨條邊。
    """
    text = graph_labels.normalize_text(article["markdown"])
    found = list(graph_labels.find_article_refs(text))

    for span in _RANGE.finditer(text):
        ends = graph_labels.find_article_refs(span.group(0), exclude_external=False)
        if len(ends) != 2:
            continue
        low, high = (graph_labels.article_sort_key(ends[0]),
                     graph_labels.article_sort_key(ends[1]))
        for number in known_numbers:
            if low <= graph_labels.article_sort_key(number) <= high and number not in found:
                found.append(number)

    if "前條" in text:
        index = order.get(article["number"])
        if index:
            previous = order["_sequence"][index - 1]
            if previous not in found:
                found.append(previous)

    return [n for n in found if n in known_numbers and n != article["number"]]


# ---------------------------------------------------------------------------
# 切塊（給語意抽取的契約用）

def chunks(articles):
    """依 hierarchy（編／章／節）分組。實測 25 塊，最大約 1.2 萬字，單輪可處理。"""
    grouped = {}
    for article in articles:
        key = "／".join(article["hierarchy"]) or "（未分編章）"
        grouped.setdefault(key, []).append(article)
    found = []
    for title, members in grouped.items():
        payload = json.dumps(
            [{"article_no": a["number"], "markdown": digest_text(a["markdown"])}
             for a in members], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        found.append({
            "id": f"chunk_{graph_labels.norm_id(title)[:60]}",
            "title": title,
            "articles": [a["number"] for a in members],
            "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "chars": sum(len(a["markdown"]) for a in members),
        })
    return sorted(found, key=lambda c: graph_labels.article_sort_key(c["articles"][0]))


def extraction_for(root, chunk):
    """該切塊的語意抽取檔（沒有或過期時回 None）。"""
    doc = load_json(Path(root) / EXTRACT_DIR / f"{chunk['id']}.json")
    if not isinstance(doc, dict) or doc.get("chunk_sha256") != chunk["sha256"]:
        return None
    return doc


# ---------------------------------------------------------------------------
# 重建

def _node(base, **fields):
    """既有節點的外來欄位（community 等）原樣帶回，只覆寫我們有權威來源的欄位。"""
    node = dict(base or {})
    node.update(fields)
    return node


def rebuild(root=".", graph_path=None):
    """回傳重建後的圖譜與一份重建報告。不寫檔——寫檔由 CLI 決定。"""
    root = Path(root)
    existing = load_json(Path(graph_path) if graph_path else root / GRAPH_PATH) or {}
    ledger = Ledger.load(root)
    ledger.learn_from_graph(existing)

    old_nodes = {n["id"]: n for n in existing.get("nodes", []) if n.get("id")}
    articles = load_articles(root)
    assets = load_assets(root)
    known = {a["number"] for a in articles}
    order = {a["number"]: i for i, a in enumerate(articles)}
    order["_sequence"] = [a["number"] for a in articles]

    nodes, links = [], []
    article_ids, seen_pairs = {}, set()

    # --- 條文節點（確定性）
    for article in articles:
        node_id = ledger.id_for(article["source_file"], article["label"])
        article_ids[article["number"]] = node_id
        nodes.append(_node(old_nodes.get(node_id),
                           id=node_id, label=article["label"], file_type=DOCUMENT,
                           source_file=article["source_file"],
                           norm_label=article["label"],
                           hierarchy=article["hierarchy"],
                           legal_basis=article["legal_basis"]))

    # --- rules/README.md 節點（整檔一個節點，label 沿用台帳）
    readme = root / RULES_README
    if readme.is_file():
        readme_source = _rel_to_rules(RULES_README)
        readme_label = next((n["label"] for n in old_nodes.values()
                             if n.get("source_file") == readme_source), None)
        if readme_label:
            readme_id = ledger.id_for(readme_source, readme_label)
            nodes.append(_node(old_nodes.get(readme_id), id=readme_id, label=readme_label,
                               file_type=DOCUMENT, source_file=readme_source))

    # --- 附表圖節點與 條文→附表圖 邊（確定性）
    for asset in assets:
        existing_label = next((n["label"] for n in old_nodes.values()
                               if n.get("source_file") == asset["source_file"]), None)
        label = existing_label or asset["label"]
        node_id = ledger.id_for(asset["source_file"], label, mint_label=None)
        nodes.append(_node(old_nodes.get(node_id), id=node_id, label=label, file_type=IMAGE,
                           source_file=asset["source_file"], norm_label=label))
        source_id = article_ids.get(asset["article"])
        if source_id:
            links.append(_link(source_id, node_id, "references", MECHANICAL,
                               asset["source_file"],
                               f"附表圖檔名 {Path(asset['source_file']).name} 指向 {asset['article']}"))
            seen_pairs.add((source_id, node_id))

    # --- 條文互引（確定性；只補既有圖譜還沒有的那對節點）
    added_citations = []
    for article in articles:
        source_id = article_ids[article["number"]]
        for target_number in citations(article, known, order):
            target_id = article_ids[target_number]
            # 既有邊照原樣保留，不改它的關聯類型——所以這裡**不能**先佔住 seen_pairs，
            # 否則保留階段會把那條既有邊當成重複而跳過，圖譜就悄悄少了一條邊。
            if (source_id, target_id) in seen_pairs or _pair_exists(existing, source_id, target_id):
                continue
            seen_pairs.add((source_id, target_id))
            links.append(_link(source_id, target_id, "cites", MECHANICAL,
                               article["source_file"],
                               f"{article['label']}條文內引用 第{target_number}條"))
            added_citations.append((article["number"], target_number))

    # --- 保留式語意層：概念節點與既有的邊原樣搬過來
    skeleton_ids = {n["id"] for n in nodes}
    chunk_list = chunks(articles)
    refreshed = {c["id"]: extraction_for(root, c) for c in chunk_list}
    refreshed_articles = {number for c in chunk_list if refreshed.get(c["id"])
                          for number in c["articles"]}
    refreshed_sources = {article_ids[n] for n in refreshed_articles if n in article_ids}

    # 分家前實務註解是併進 graph.json 的。那些節點現在屬於訓練圖譜，
    # 留在法規圖譜裡會讓查詢重複計算——重建時逐出，並回報讓使用者知道搬去哪了。
    evicted = [n for n in existing.get("nodes", [])
               if n.get("layer") in training_graph_build.TRAINING_LAYERS and n.get("id")]
    evicted_ids = {n["id"] for n in evicted}
    concept_nodes = [n for n in existing.get("nodes", [])
                     if n.get("file_type") not in (DOCUMENT, IMAGE) and n.get("id")
                     and n["id"] not in evicted_ids]
    nodes.extend(n for n in concept_nodes if n["id"] not in skeleton_ids)
    live_ids = {n["id"] for n in nodes}

    dropped = []
    for edge in existing.get("links", []):
        if edge.get("source") not in live_ids or edge.get("target") not in live_ids:
            dropped.append(edge)
            continue
        # 有新抽取的切塊：該切塊條文的語意邊由新抽取取代
        if edge.get("source") in refreshed_sources and edge.get("confidence") == EXTRACTED:
            continue
        if (edge["source"], edge["target"]) in seen_pairs:
            continue
        seen_pairs.add((edge["source"], edge["target"]))
        links.append(edge)

    # --- 新抽取的語意層
    index = graph_labels.LabelIndex(nodes)
    unresolved = []
    for chunk in chunk_list:
        doc = refreshed.get(chunk["id"])
        if not doc:
            continue
        for concept in doc.get("concepts", []):
            label = str(concept.get("label", "")).strip()
            if not label or index.resolve(label).node_id:
                continue
            source_file = concept.get("source_file") or articles[0]["source_file"]
            node_id = ledger.id_for(source_file, label,
                                    mint_label=concept.get("id_hint") or label)
            node = {"id": node_id, "label": label, "file_type": CONCEPT,
                    "source_file": source_file, "norm_label": label.lower(),
                    "rationale": concept.get("rationale")}
            nodes.append(node)
            index.bind_declared(label, node_id)
        for edge in doc.get("edges", []):
            source = index.resolve(str(edge.get("source", "")).strip())
            target = index.resolve(str(edge.get("target", "")).strip())
            if not (source.node_id and target.node_id):
                unresolved.append({"chunk": chunk["id"], "source": edge.get("source"),
                                   "target": edge.get("target")})
                continue
            if (source.node_id, target.node_id) in seen_pairs:
                continue
            seen_pairs.add((source.node_id, target.node_id))
            links.append(_link(source.node_id, target.node_id, edge.get("relation"),
                               EXTRACTED, chunk["id"], edge.get("rationale")))

    graph = {
        "directed": existing.get("directed", False),
        "multigraph": existing.get("multigraph", False),
        "graph": existing.get("graph", {}),
        "nodes": nodes,
        "links": links,
        "hyperedges": existing.get("hyperedges", []),
        "built_at_commit": _head_commit(root) or existing.get("built_at_commit"),
    }
    report = {
        "articles": len(articles), "assets": len(assets),
        "nodes": len(nodes), "links": len(links),
        "minted_ids": ledger.minted,
        "added_citations": added_citations,
        "dropped_edges": dropped,
        "evicted_training_nodes": sorted(evicted_ids),
        "refreshed_chunks": sorted(c for c, d in refreshed.items() if d),
        "unresolved": unresolved,
        "hyperedge_problems": _hyperedge_problems(graph),
        "ledger": ledger.to_doc({a["number"]: article_text_sha(a) for a in articles}),
    }
    return graph, report


def _link(source, target, relation, confidence, source_file, rationale):
    return {"relation": relation, "confidence": confidence, "confidence_score": 1.0,
            "source_file": source_file, "source_location": None, "weight": 1.0,
            "rationale": rationale, "source": source, "target": target}


def _pair_exists(graph, source, target):
    for edge in graph.get("links", []):
        if edge.get("source") == source and edge.get("target") == target:
            return True
    return False


def _hyperedge_problems(graph):
    """超邊引用的節點必須都還在——這是 id 相容性的免費回歸檢查。"""
    ids = {n["id"] for n in graph["nodes"]}
    problems = []
    for hyperedge in graph.get("hyperedges", []):
        missing = [n for n in hyperedge.get("nodes", []) if n not in ids]
        if missing:
            problems.append({"id": hyperedge.get("id"), "missing": missing})
    return problems


def _head_commit(root):
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# verify：與現行圖譜的差異報表

# 這五類非空就拒絕覆寫 graph.json。
#
# `edges_lost` 是其中最重要的一項：節點消失、label 變動都看得見，但「邊少了幾條」
# 使用者完全察覺不到——查詢只會少回幾筆，不會報錯。所以凡是**兩個端點都還在、
# 邊卻不見了**的情形一律紅燈；端點真的消失所導致的連帶移除才算可解釋。
RED_CATEGORIES = ("nodes_removed", "labels_changed", "hyperedge_problems", "unresolved",
                  "edges_lost")


def verify(root=".", against=None):
    root = Path(root)
    old = load_json(Path(against) if against else root / GRAPH_PATH) or {}
    new, report = rebuild(root)

    old_nodes = {n["id"]: n for n in old.get("nodes", []) if n.get("id")}
    new_nodes = {n["id"]: n for n in new["nodes"]}
    old_edges = {(e.get("source"), e.get("target")) for e in old.get("links", [])}
    new_edges = {(e.get("source"), e.get("target")) for e in new["links"]}
    removed = sorted(old_edges - new_edges)

    # 舊版遺留的訓練層節點被逐出是**預期**的搬遷，不是流失——它們在訓練圖譜裡。
    evicted = set(report["evicted_training_nodes"])
    return {
        "nodes_removed": sorted(set(old_nodes) - set(new_nodes) - evicted),
        "nodes_moved_to_training": sorted(evicted),
        "nodes_added": sorted(set(new_nodes) - set(old_nodes)),
        "labels_changed": sorted(i for i in set(old_nodes) & set(new_nodes)
                                 if old_nodes[i].get("label") != new_nodes[i].get("label")),
        "edges_removed": removed,
        "edges_lost": [pair for pair in removed
                       if pair[0] in new_nodes and pair[1] in new_nodes
                       and pair[0] not in evicted and pair[1] not in evicted],
        "edges_added": sorted(new_edges - old_edges),
        "hyperedge_problems": report["hyperedge_problems"],
        "unresolved": report["unresolved"],
        "minted_ids": report["minted_ids"],
        "counts": {"old_nodes": len(old_nodes), "new_nodes": len(new_nodes),
                   "old_edges": len(old.get("links", [])), "new_edges": len(new["links"])},
    }


def verify_is_green(result):
    return not any(result[key] for key in RED_CATEGORIES)


def format_verify(result):
    counts = result["counts"]
    lines = ["== 重建差異驗收 ==",
             f"節點 {counts['old_nodes']} → {counts['new_nodes']}｜"
             f"邊 {counts['old_edges']} → {counts['new_edges']}"]
    for key, label in (("nodes_removed", "節點消失（會讓抽取檔與訓練圖譜的參照失效）"),
                       ("labels_changed", "label 變動（跨圖譜參照以 label 為鍵，不得變）"),
                       ("edges_lost", "兩端都還在、邊卻不見了（使用者察覺不到的劣化）"),
                       ("unresolved", "抽取檔的 source／target 解析不到")):
        if result[key]:
            lines.append(f"🔴 {label}：{len(result[key])} 項")
            for item in result[key][:10]:
                lines.append(f"    {item}")
    if result["hyperedge_problems"]:
        lines.append(f"🔴 超邊引用到不存在的節點：{len(result['hyperedge_problems'])} 條")
        for item in result["hyperedge_problems"][:5]:
            lines.append(f"    {item['id']} → {item['missing']}")
    if result.get("nodes_moved_to_training"):
        lines.append(f"ℹ️ {len(result['nodes_moved_to_training'])} 個舊版遺留的訓練層節點"
                     "移出法規圖譜（它們現在住在 training/graph.json）")
    if result["nodes_added"]:
        lines.append(f"🟡 新增節點 {len(result['nodes_added'])} 個（逐一確認）")
        for item in result["nodes_added"][:10]:
            lines.append(f"    {item}")
    if result["edges_added"]:
        lines.append(f"🟡 新增邊 {len(result['edges_added'])} 條（確定性抽出的引用，抽樣核對原文）")
    if result["edges_removed"]:
        lines.append(f"🟡 消失的邊 {len(result['edges_removed'])} 條")
        for item in result["edges_removed"][:10]:
            lines.append(f"    {item[0]} → {item[1]}")
    lines.append("✅ 紅燈類別全為 0，可以 --commit" if verify_is_green(result)
                 else "⛔ 有紅燈類別，rebuild --commit 會拒絕覆寫")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# plan：哪些切塊該重抽語意層

def plan(root="."):
    root = Path(root)
    articles = load_articles(root)
    ledger = Ledger.load(root)
    graph = load_json(root / GRAPH_PATH) or {}
    covered = {e.get("source") for e in graph.get("links", [])
               if e.get("confidence") == EXTRACTED}
    node_by_label = {n.get("label"): n.get("id") for n in graph.get("nodes", [])}

    pending, ready = [], []
    for chunk in chunks(articles):
        extraction = extraction_for(root, chunk)
        if extraction:
            ready.append(chunk["id"])
            continue
        changed = [n for n in chunk["articles"]
                   if ledger.articles.get(n) not in (None, _sha_of(articles, n))]
        uncovered = [n for n in chunk["articles"]
                     if node_by_label.get(f"第{n}條") not in covered]
        if changed:
            pending.append({"chunk": chunk["id"], "title": chunk["title"],
                            "reason": "changed", "articles": changed})
        elif uncovered and not graph:
            pending.append({"chunk": chunk["id"], "title": chunk["title"],
                            "reason": "uncovered", "articles": uncovered})
    return {"chunks": len(chunks(articles)), "ready": ready, "pending": pending}


def _sha_of(articles, number):
    for article in articles:
        if article["number"] == number:
            return article_text_sha(article)
    return None


def format_plan(result):
    lines = ["== 法規圖譜語意層狀態 =="]
    lines.append(f"切塊：{result['chunks']} 個｜已有新抽取：{len(result['ready'])} 個"
                 f"｜建議重抽：{len(result['pending'])} 個")
    for item in result["pending"]:
        lines.append(f"  ⚠️ {item['chunk']}（{item['reason']}）：{item['title']}"
                     f"——條文 {'、'.join(item['articles'][:8])}")
    if result["pending"]:
        lines.append("→ python3 tools/regulation_graph_build.py contract --chunk {id}")
        lines.append("  由對話中的模型依契約產出抽取檔（不需要 API key），再跑 rebuild。")
        lines.append("  註：重建只增不減，不補抽取也不會弄丟既有語意層。")
    else:
        lines.append("✅ 沒有需要重抽的切塊。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# check：供 graph_status 取用

def check(root="."):
    root = Path(root)
    if not (root / GRAPH_PATH).is_file():
        return {"state": "absent", "pending": []}
    result = plan(root)
    return {"state": "stale" if result["pending"] else "fresh", "pending": result["pending"]}


# ---------------------------------------------------------------------------
# 契約

CONTRACT_TEMPLATE = {
    "schema_version": EXTRACTION_SCHEMA_VERSION,
    "chunk_id": "{chunk_id}",
    "chunk_sha256": "{chunk_sha256}",
    "extracted_by": "（填語意抽取者：模型或 agent 名稱）",
    "extracted_at": "（填 ISO 8601 時間）",
    "concepts": [
        {"label": "（概念名稱，例：無開口樓層）",
         "id_hint": "（節點 id 用的短名，通常與 label 相同）",
         "source_file": "（該概念定義所在的來源檔，相對 rules/）",
         "rationale": "（從哪句條文原文讀出這個概念——引原文）"}
    ],
    "edges": [
        {"source": "（既有節點 label，例：第7條）",
         "target": "（既有節點 label 或上面 concepts 的 label）",
         "relation": "|".join(RELATIONS),
         "rationale": "（為什麼有這條關聯——引條文原文）"}
    ],
}


def validate_extraction(extraction, chunk, index):
    problems = []
    if not isinstance(extraction, dict):
        return ["抽取檔不是物件"]
    if extraction.get("chunk_id") != chunk["id"]:
        problems.append(f"chunk_id 與切塊不符：{extraction.get('chunk_id')!r}")
    if extraction.get("chunk_sha256") != chunk["sha256"]:
        problems.append("chunk_sha256 與現行條文不符——條文已變更，須重新語意抽取")
    for field in ("extracted_by", "extracted_at"):
        value = extraction.get(field)
        if not str(value or "").strip() or practice_note_graph.has_placeholder(value):
            problems.append(f"{field} 必填且不得留樣板文字")

    declared = {str(c.get("label", "")).strip() for c in extraction.get("concepts", [])
                if isinstance(c, dict)}
    scoped = index.with_declared(declared)
    for i, concept in enumerate(extraction.get("concepts", [])):
        if not isinstance(concept, dict):
            problems.append(f"concepts[{i}] 須為物件")
            continue
        if not str(concept.get("label", "")).strip():
            problems.append(f"concepts[{i}].label 必填")
        if not str(concept.get("rationale", "")).strip():
            problems.append(f"concepts[{i}].rationale 必填——須引條文原文")
    for i, edge in enumerate(extraction.get("edges", [])):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} 須為物件")
            continue
        for end in ("source", "target"):
            value = str(edge.get(end, "")).strip()
            if not value:
                problems.append(f"{where}.{end} 必填")
                continue
            resolution = scoped.resolve(value)
            if resolution.how not in graph_labels.RESOLVED_HOWS:
                problems.append(f"{where}.{end} {graph_labels.describe(resolution, value)}")
        if edge.get("relation") not in RELATIONS:
            problems.append(f"{where}.relation 應為 {'／'.join(RELATIONS)}")
        if not str(edge.get("rationale", "")).strip():
            problems.append(f"{where}.rationale 必填——須引條文原文")
    return problems


# ---------------------------------------------------------------------------
# CLI

def cmd_plan(args):
    result = plan(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_plan(result))
    return 2 if result["pending"] else 0


def cmd_rebuild(args):
    root = Path(args.root)
    if args.commit:
        result = verify(root)
        if not verify_is_green(result):
            print(format_verify(result), file=sys.stderr)
            print("\n⛔ 拒絕覆寫 graph.json：先處理上列紅燈項目。", file=sys.stderr)
            return 2
    graph, report = rebuild(root)
    target = root / (GRAPH_PATH if args.commit else REBUILT_PATH)
    if not args.dry_run:
        write_json(target, graph)
        write_json(root / LEDGER_PATH, report["ledger"])
    if args.format == "json":
        printable = {k: v for k, v in report.items() if k != "ledger"}
        print(json.dumps(printable, ensure_ascii=False, indent=2))
        return 0
    prefix = "（乾跑，未寫檔）" if args.dry_run else ""
    print(f"✅ 已重建法規圖譜{prefix}：條文 {report['articles']} 條、附表圖 {report['assets']} 張 → "
          f"{report['nodes']} 節點／{report['links']} 邊")
    if report["minted_ids"]:
        print(f"  ⚠️ 新鑄 {len(report['minted_ids'])} 個節點 id（既有節點一律沿用舊 id）：")
        for item in report["minted_ids"][:10]:
            print(f"      {item['label']} → {item['id']}")
    if report["added_citations"]:
        print(f"  ℹ️ 補上 {len(report['added_citations'])} 條原本沒有的條文互引")
    if report["dropped_edges"]:
        print(f"  ⚠️ {len(report['dropped_edges'])} 條邊因端點消失而移除")
    if not args.dry_run:
        print(f"  寫入 {target.relative_to(root).as_posix()}")
        if not args.commit:
            print("  → 先跑 verify 看差異；確認無誤再 rebuild --commit 覆寫 graph.json")
        else:
            print("  → 接續：python3 tools/graph_status.py stamp --graph regulation")
    return 0


def cmd_verify(args):
    result = verify(args.root, args.against)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_verify(result))
    return 0 if verify_is_green(result) else 2


def cmd_contract(args):
    root = Path(args.root)
    articles = load_articles(root)
    found = {c["id"]: c for c in chunks(articles)}
    if args.chunk not in found:
        print(f"⛔ 找不到切塊 {args.chunk}。可用的切塊：", file=sys.stderr)
        for chunk in found.values():
            print(f"    {chunk['id']}（{chunk['title']}，{len(chunk['articles'])} 條）",
                  file=sys.stderr)
        return 1
    chunk = found[args.chunk]
    body = [a for a in articles if a["number"] in chunk["articles"]]
    contract = json.loads(json.dumps(CONTRACT_TEMPLATE)
                          .replace("{chunk_id}", chunk["id"])
                          .replace("{chunk_sha256}", chunk["sha256"]))
    graph = load_json(root / GRAPH_PATH) or {}
    if args.format == "json":
        print(json.dumps({"chunk": chunk, "articles": body, "contract": contract},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"== {chunk['id']} 語意抽取契約 ==")
    print(f"【切塊】{chunk['title']}｜{len(body)} 條｜{chunk['chars']} 字\n")
    print("【條文原文（語意抽取的唯一輸入）】")
    for article in body:
        print(f"\n--- {article['label']} ---\n{article['markdown']}")
    print("\n【既有概念節點 label（優先重用，不要造同義新詞）】")
    labels = sorted(n.get("label") for n in graph.get("nodes", [])
                    if n.get("file_type") == CONCEPT and n.get("label"))
    print("、".join(labels) or "（圖譜尚無概念節點）")
    print(f"\n【可用關聯類型】{'／'.join(RELATIONS)}")
    print(f"\n【輸出檔】{EXTRACT_DIR}/{chunk['id']}.json")
    print(json.dumps(contract, ensure_ascii=False, indent=2))
    print("\n抽取原則：")
    print("  1. **條文內寫明條號的引用已由確定性 pass 抽出，不要重複宣告**；"
          "只補文字裡沒有寫出條號的語意關聯（例：§7 列舉分類 → §8~§11 各自定義）")
    print("  2. 只寫條文原文真的說了的關聯，rationale 必須引原文；不確定就不要抽")
    print("  3. 概念名稱用審圖會拿來查的詞，且優先重用上面列出的既有 label")
    print(f"  4. 寫完跑：python3 tools/regulation_graph_build.py validate "
          f"--extraction {EXTRACT_DIR}/{chunk['id']}.json")
    return 0


def cmd_validate(args):
    root = Path(args.root)
    extraction = load_json(args.extraction)
    if extraction is None:
        print(f"⛔ 讀不到抽取檔：{args.extraction}", file=sys.stderr)
        return 1
    chunk_id = extraction.get("chunk_id") or Path(args.extraction).stem
    found = {c["id"]: c for c in chunks(load_articles(root))}
    if chunk_id not in found:
        print(f"⛔ {chunk_id} 不是現行切塊，無從驗證", file=sys.stderr)
        return 2
    graph = load_json(root / GRAPH_PATH) or {}
    problems = validate_extraction(extraction, found[chunk_id],
                                   graph_labels.LabelIndex(graph.get("nodes", [])))
    if args.format == "json":
        print(json.dumps({"chunk_id": chunk_id, "problems": problems},
                         ensure_ascii=False, indent=2))
    elif problems:
        print(f"🔴 {chunk_id} 抽取檔未通過（{len(problems)} 項）：")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"🟢 {chunk_id} 抽取檔通過，可執行 rebuild。")
    return 2 if problems else 0


def cmd_check(args):
    result = check(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else f"法規圖譜語意層：{result['state']}（待重抽 {len(result['pending'])} 個切塊）")
    return 0 if result["state"] == "fresh" else 2


def build_parser():
    p = argparse.ArgumentParser(
        description="法規圖譜重建（確定性骨架 ＋ 保留式語意層；零安裝、不需 API key）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("plan", help="哪些切塊建議重抽語意層（0=齊備 2=有建議）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("rebuild", help="重建圖譜（預設寫 graph.rebuilt.json，不覆寫）")
    s.add_argument("--commit", action="store_true",
                   help="verify 全綠時覆寫 graphify-out/graph.json")
    s.add_argument("--dry-run", action="store_true", help="只算不寫檔")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_rebuild)

    s = sub.add_parser("verify", help="重建結果與現行圖譜的差異報表（0=紅燈類別全 0）")
    s.add_argument("--against", default=None, help="比對對象（預設 graphify-out/graph.json）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("contract", help="印出某切塊的語意抽取契約")
    s.add_argument("--chunk", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_contract)

    s = sub.add_parser("validate", help="驗證切塊的語意抽取檔（0=通過 2=有問題）")
    s.add_argument("--extraction", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("check", help="語意層是否跟上條文（0=跟上 2=建議重抽）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

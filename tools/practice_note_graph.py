#!/usr/bin/env python3
"""實務註解 → 法規知識圖譜的納入層（LLM 語意抽取 ＋ 確定性合併）。

只用 Python 標準庫。

    python3 tools/practice_note_graph.py plan                 # 誰還沒語意抽取（0=齊備 2=有待辦）
    python3 tools/practice_note_graph.py contract --note {id} # 印出該註解的抽取契約（給 LLM 填）
    python3 tools/practice_note_graph.py validate --extraction practice_notes/graph_extractions/{id}.json
    python3 tools/practice_note_graph.py merge                # 併入 graphify-out/graph.json（冪等）
    python3 tools/practice_note_graph.py check                # 圖譜是否已納入全部 active 註解

為什麼要分成「LLM 抽取」＋「工具合併」兩段：

- 註解的 `scenario.summary`／`judgment.detail` 是自由文字，**沒有固定格式**，
  要抽出「這則註解牽涉哪些概念、關聯到哪些既有條文與設備」只能靠語意理解；
  規則式關鍵字比對會漏抽也會誤抽。語意抽取由 `/practice-note` 第七步的 LLM 完成，
  結果寫成 `practice_notes/graph_extractions/{註解 id}.json`。
- 但**寫進圖譜的動作必須是確定性的**：本工具只搬運抽取檔裡已經寫明的節點與邊，
  自己絕不從註解文字推導任何語意關聯（唯一例外是 `ref_article`／`judgment.equipment`
  這兩個結構化欄位產生的錨點邊，標記為 MECHANICAL，用途是保證可追溯）。

抽取檔以 `note_sha256` 綁定當時的註解內容：註解改了、抽取檔沒跟著更新，
`plan`／`merge`／`check` 一律紅燈，不會拿舊語意去合併。

邊界（呼應 CLAUDE.md 審圖最高原則 2、4、9）：圖譜只是索引與導覽。
註解節點進圖譜是為了「查得到」，不是為了讓它變成法規；查詢輸出一律附註解警語，
援引時必須同時列出所補充的法條與註解 ID。
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ACTIVE_DIR = "practice_notes/active"
EXTRACT_DIR = "practice_notes/graph_extractions"
GRAPH_PATH = "graphify-out/graph.json"

LAYER = "practice_note"
NODE_PREFIX = "practice_note_"
CONCEPT_PREFIX = "practice_note_concept_"
PLACEHOLDER = "（待填）"

NOTE_NOTICE = ("實務註解為消防專業人員確認之實務見解，非法規條文；"
               "援引時須同時列出所補充的法條與註解 ID")

# 語意抽取可用的關聯類型。刻意維持極小集合——多一種關聯就多一種誤讀的可能。
RELATIONS = {
    "supplements": "補充某條文（註解 → 條文）",
    "concerns_equipment": "涉及某設備（註解 → 設備）",
    "applies_when": "觸發條件概念（註解 → 情境概念）",
    "conceptually_related_to": "語意關聯（註解 → 用途分類／其他概念）",
}
CONCEPT_KINDS = ("scenario_condition", "equipment", "place_use", "other")

EXTRACTION_SCHEMA_VERSION = 1

CONTRACT_TEMPLATE = {
    "schema_version": EXTRACTION_SCHEMA_VERSION,
    "note_id": "{note_id}",
    "note_sha256": "{note_sha256}",
    "extracted_by": "（填語意抽取者：模型或 agent 名稱）",
    "extracted_at": "（填 ISO 8601 時間）",
    "summary": "（一句話：這則註解在圖譜中代表什麼，供查詢結果直接顯示）",
    "concepts": [
        {"label": "（概念名稱，例：挑空區）", "kind": "|".join(CONCEPT_KINDS),
         "rationale": "（為什麼從註解讀出這個概念——引註解原文）"}
    ],
    "edges": [
        {"target": "（既有圖譜節點 label，例：第19條／自動撒水設備；或上面 concepts 的 label）",
         "relation": "|".join(RELATIONS),
         "rationale": "（為什麼有這條關聯——引註解原文）"}
    ],
}


# ---------------------------------------------------------------------------
# 讀寫

def load_json(path, default=None):
    path = Path(path)
    if not path.is_file():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def active_notes(root="."):
    """回傳 [(note_id, path, note, sha256)]，只含 status 為 active 者。"""
    directory = Path(root) / ACTIVE_DIR
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        note = load_json(path)
        if not isinstance(note, dict) or note.get("status") != "active":
            continue
        found.append((note.get("id", path.stem), path, note, sha256_file(path)))
    return found


def extraction_path(root, note_id):
    return Path(root) / EXTRACT_DIR / f"{note_id}.json"


def normalize_article(ref):
    return str(ref).lstrip("§第").rstrip("條").strip()


def article_label(ref):
    number = normalize_article(ref)
    return f"第{number}條" if number else None


def norm_id(label):
    """概念 label → 節點 id 片段（保留中日文字，其餘收斂為底線）。"""
    slug = re.sub(r"[^0-9A-Za-z一-鿿]+", "_", str(label)).strip("_")
    return slug or "unnamed"


def node_id_for(note_id):
    return f"{NODE_PREFIX}{note_id}"


# ---------------------------------------------------------------------------
# 抽取檔驗證（純結構檢查，不做法規判斷、不補內容）

def has_placeholder(value):
    return isinstance(value, str) and (PLACEHOLDER in value or value.strip().startswith("（填"))


def validate_extraction(extraction, note, note_sha, graph_labels):
    """回傳 problems 清單。graph_labels 為既有圖譜的 label 集合（用來解析 edge target）。"""
    problems = []
    if not isinstance(extraction, dict):
        return ["抽取檔不是物件"]

    note_id = note.get("id")
    if extraction.get("note_id") != note_id:
        problems.append(f"note_id 與註解不符：抽取檔 {extraction.get('note_id')!r}、註解 {note_id!r}")
    if extraction.get("note_sha256") != note_sha:
        problems.append("note_sha256 與現行註解內容不符——註解已變更，須重新語意抽取")
    for field in ("extracted_by", "extracted_at", "summary"):
        value = extraction.get(field)
        if not str(value or "").strip() or has_placeholder(value):
            problems.append(f"{field} 必填且不得留樣板文字")

    concepts = extraction.get("concepts")
    edges = extraction.get("edges")
    if not isinstance(concepts, list):
        problems.append("concepts 須為陣列")
        concepts = []
    if not isinstance(edges, list):
        problems.append("edges 須為陣列")
        edges = []
    if not concepts and not edges:
        problems.append("concepts 與 edges 全空——語意抽取沒有產出任何可查詢的知識，"
                        "不得合併（要嘛補抽取，要嘛說明該註解為何無法入圖譜）")

    concept_labels = set()
    for i, concept in enumerate(concepts):
        where = f"concepts[{i}]"
        if not isinstance(concept, dict):
            problems.append(f"{where} 須為物件")
            continue
        label = str(concept.get("label", "")).strip()
        if not label or has_placeholder(label):
            problems.append(f"{where}.label 必填且不得留樣板文字")
        else:
            if label in concept_labels:
                problems.append(f"{where}.label 與前面的概念重複：{label}")
            concept_labels.add(label)
        if concept.get("kind") not in CONCEPT_KINDS:
            problems.append(f"{where}.kind 應為 {'／'.join(CONCEPT_KINDS)}，實得 {concept.get('kind')!r}")
        if not str(concept.get("rationale", "")).strip() or has_placeholder(concept.get("rationale")):
            problems.append(f"{where}.rationale 必填——語意抽取須說明從註解哪句話讀出此概念")

    for i, edge in enumerate(edges):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} 須為物件")
            continue
        target = str(edge.get("target", "")).strip()
        if not target or has_placeholder(target):
            problems.append(f"{where}.target 必填且不得留樣板文字")
        elif target not in graph_labels and target not in concept_labels:
            problems.append(f"{where}.target「{target}」在圖譜與本抽取檔的 concepts 都找不到"
                            "——請改用既有節點 label，或先在 concepts 宣告這個概念")
        if edge.get("relation") not in RELATIONS:
            problems.append(f"{where}.relation 應為 {'／'.join(RELATIONS)}，實得 {edge.get('relation')!r}")
        if not str(edge.get("rationale", "")).strip() or has_placeholder(edge.get("rationale")):
            problems.append(f"{where}.rationale 必填——語意抽取須說明此關聯的依據")

    return problems


# ---------------------------------------------------------------------------
# plan：誰還沒抽取

def plan(root="."):
    notes = active_notes(root)
    graph = load_json(Path(root) / GRAPH_PATH)
    graph_labels = {n.get("label") for n in (graph or {}).get("nodes", [])}
    pending, ready = [], []
    for note_id, path, note, sha in notes:
        epath = extraction_path(root, note_id)
        extraction = load_json(epath)
        if extraction is None:
            pending.append({"note_id": note_id, "reason": "missing",
                            "detail": f"缺語意抽取檔 {epath.relative_to(Path(root)).as_posix()}"})
            continue
        if extraction.get("note_sha256") != sha:
            pending.append({"note_id": note_id, "reason": "stale",
                            "detail": "註解內容已變更，抽取檔的 note_sha256 過期，須重新語意抽取"})
            continue
        problems = validate_extraction(extraction, note, sha, graph_labels)
        if problems:
            pending.append({"note_id": note_id, "reason": "invalid", "detail": "；".join(problems)})
        else:
            ready.append(note_id)
    return {"active": len(notes), "ready": sorted(ready), "pending": pending}


def format_plan(result):
    lines = ["== 實務註解語意抽取狀態 =="]
    lines.append(f"active 註解：{result['active']} 則｜已可合併：{len(result['ready'])} 則"
                 f"｜待處理：{len(result['pending'])} 則")
    for item in result["pending"]:
        lines.append(f"  ⛔ {item['note_id']}（{item['reason']}）：{item['detail']}")
    if result["pending"]:
        lines.append("→ 對每一則待處理註解跑："
                     " python3 tools/practice_note_graph.py contract --note {id}")
        lines.append("  依契約做 LLM 語意抽取並寫回 "
                     f"{EXTRACT_DIR}/{{id}}.json，再跑 merge。")
    elif result["active"]:
        lines.append("✅ 全部 active 註解都有有效的語意抽取檔，可執行 merge。")
    else:
        lines.append("（目前沒有 active 註解，無須抽取。）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# merge：把抽取結果併入圖譜（冪等）

def strip_layer(graph):
    """移除既有 practice_note 層，讓 merge 可重複執行。"""
    kept_nodes = [n for n in graph.get("nodes", []) if n.get("layer") != LAYER]
    kept_links = [l for l in graph.get("links", []) if l.get("layer") != LAYER]
    removed = len(graph.get("nodes", [])) - len(kept_nodes)
    graph["nodes"] = kept_nodes
    graph["links"] = kept_links
    return removed


def build_layer(root, notes, graph_nodes):
    """依 active 註解 ＋ 抽取檔產生要併入的節點與邊。呼叫前 plan 必須全綠。"""
    by_label = {}
    for node in graph_nodes:
        by_label.setdefault(node.get("label"), node["id"])

    new_nodes, new_links = [], []
    created = {}

    def resolve(label):
        if label in by_label:
            return by_label[label]
        if label in created:
            return created[label]
        return None

    for note_id, path, note, sha in notes:
        extraction = load_json(extraction_path(root, note_id))
        source_file = Path(path).relative_to(Path(root)).as_posix()
        judgment = note.get("judgment") or {}
        scenario = note.get("scenario") or {}
        pn_id = node_id_for(note_id)
        new_nodes.append({
            "label": note_id,
            "file_type": LAYER,
            "layer": LAYER,
            "source_file": source_file,
            "note_id": note_id,
            "note_sha256": sha,
            "ref_article": article_label(note.get("ref_article", "")),
            "ref_rule_ids": note.get("ref_rule_ids", []),
            "equipment": judgment.get("equipment"),
            "decision": judgment.get("decision"),
            "scenario_summary": scenario.get("summary"),
            "graph_summary": extraction.get("summary"),
            "source_case": note.get("source_case"),
            "extracted_by": extraction.get("extracted_by"),
            "extracted_at": extraction.get("extracted_at"),
            "notice": NOTE_NOTICE,
            "norm_label": note_id.lower(),
            "id": pn_id,
        })
        by_label[note_id] = pn_id

        # 語意抽取宣告的新概念（既有圖譜已有同名節點時一律重用，不製造孤島）
        for concept in extraction.get("concepts", []):
            label = str(concept["label"]).strip()
            if resolve(label):
                continue
            cid = f"{CONCEPT_PREFIX}{norm_id(label)}"
            created[label] = cid
            new_nodes.append({
                "label": label,
                "file_type": "concept",
                "layer": LAYER,
                "source_file": source_file,
                "concept_kind": concept.get("kind"),
                "rationale": concept.get("rationale"),
                "from_practice_note": note_id,
                "notice": NOTE_NOTICE,
                "norm_label": label.lower(),
                "id": cid,
            })

        def add_link(target_id, relation, confidence, rationale, score):
            new_links.append({
                "relation": relation,
                "confidence": confidence,
                "confidence_score": score,
                "source_file": source_file,
                "source_location": None,
                "weight": 1.0,
                "layer": LAYER,
                "practice_note_id": note_id,
                "rationale": rationale,
                "source": pn_id,
                "target": target_id,
            })

        # 錨點邊：來自結構化欄位，保證註解一定掛得回條文（可追溯性底線）
        art_label = article_label(note.get("ref_article", ""))
        art_id = resolve(art_label) if art_label else None
        if art_id:
            add_link(art_id, "supplements", "MECHANICAL",
                     f"註解的 ref_article 欄位指向 {art_label}", 1.0)
        equipment = str(judgment.get("equipment") or "").strip()
        eq_id = resolve(equipment) if equipment else None
        if eq_id:
            add_link(eq_id, "concerns_equipment", "MECHANICAL",
                     f"註解的 judgment.equipment 欄位為「{equipment}」", 1.0)

        # 語意邊：只搬運抽取檔寫明的內容
        seen = {(l["target"], l["relation"]) for l in new_links if l["source"] == pn_id}
        for edge in extraction.get("edges", []):
            target_id = resolve(str(edge["target"]).strip())
            if not target_id or (target_id, edge["relation"]) in seen:
                continue
            seen.add((target_id, edge["relation"]))
            add_link(target_id, edge["relation"], "EXTRACTED", edge.get("rationale"), 1.0)

    return new_nodes, new_links


def merge(root=".", graph_path=None, dry_run=False):
    root = Path(root)
    gpath = Path(graph_path) if graph_path else root / GRAPH_PATH
    graph = load_json(gpath)
    if graph is None:
        return {"ok": False, "error": f"找不到圖譜 {gpath.as_posix()}——請先重建圖譜（/graphify rules）"}

    status = plan(root)
    if status["pending"]:
        return {"ok": False, "error": "有 active 註解尚未完成語意抽取，拒絕合併（避免圖譜與註解庫不一致）",
                "pending": status["pending"]}

    removed = strip_layer(graph)
    notes = active_notes(root)
    new_nodes, new_links = build_layer(root, notes, graph["nodes"])
    graph["nodes"].extend(new_nodes)
    graph["links"].extend(new_links)
    if not dry_run:
        write_json(gpath, graph)
    return {"ok": True, "removed_nodes": removed, "notes": len(notes),
            "added_nodes": len(new_nodes), "added_links": len(new_links),
            "total_nodes": len(graph["nodes"]), "total_links": len(graph["links"]),
            "dry_run": dry_run}


# ---------------------------------------------------------------------------
# check：圖譜是否已納入全部 active 註解（供 graph_status／審圖前置檢查取用）

def check(root=".", graph_path=None):
    root = Path(root)
    gpath = Path(graph_path) if graph_path else root / GRAPH_PATH
    graph = load_json(gpath)
    notes = active_notes(root)
    if graph is None:
        # 圖譜不存在本身由 graph_status 的指紋關卡處理；這裡只回報「沒有註解被納入」。
        return {"state": "covered" if not notes else "uncovered", "graph_present": False,
                "active": len(notes), "merged": 0,
                "missing": [n for n, _, _, _ in notes], "stale": [], "orphan": []}

    in_graph = {n.get("note_id"): n for n in graph.get("nodes", [])
                if n.get("layer") == LAYER and n.get("note_id")}
    missing, stale = [], []
    for note_id, _, _, sha in notes:
        node = in_graph.get(note_id)
        if node is None:
            missing.append(note_id)
        elif node.get("note_sha256") != sha:
            stale.append(note_id)
    orphan = sorted(set(in_graph) - {n for n, _, _, _ in notes})

    state = "uncovered" if (missing or stale or orphan) else "covered"
    return {"state": state, "graph_present": True, "active": len(notes), "merged": len(in_graph),
            "missing": missing, "stale": stale, "orphan": orphan}


MERGE_HINT = ("補納入：python3 tools/practice_note_graph.py plan → 依契約做 LLM 語意抽取 → "
              "python3 tools/practice_note_graph.py merge")


def format_check(result):
    lines = ["== 實務註解圖譜納入狀態 =="]
    if not result.get("graph_present", True):
        lines.append(f"⛔ 找不到 {GRAPH_PATH}——圖譜尚未建立，"
                     f"{result['active']} 則 active 註解無處可併")
        return "\n".join(lines)
    if result["state"] == "covered":
        lines.append("✅ 目前沒有 active 實務註解，圖譜無須納入" if result["active"] == 0 else
                     f"✅ 已納入 —— {result['active']} 則 active 註解全部在圖譜中"
                     f"（節點 {result['merged']} 個）")
        return "\n".join(lines)
    lines.append(f"⛔ 未納入 —— active {result['active']} 則、圖譜內 {result['merged']} 則")
    for note_id in result["missing"]:
        lines.append(f"  [缺漏] {note_id} 不在圖譜中——查圖譜查不到這則訓練成果")
    for note_id in result["stale"]:
        lines.append(f"  [過期] {note_id} 的註解內容已變更，圖譜內是舊版語意")
    for note_id in result["orphan"]:
        lines.append(f"  [殘留] {note_id} 已非 active 註解，卻仍留在圖譜中")
    lines.append(f"→ {MERGE_HINT}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI

def cmd_plan(args):
    result = plan(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_plan(result))
    return 2 if result["pending"] else 0


def cmd_contract(args):
    root = Path(args.root)
    notes = {nid: (path, note, sha) for nid, path, note, sha in active_notes(root)}
    if args.note not in notes:
        print(f"⛔ 找不到 active 註解 {args.note}（{ACTIVE_DIR}/{args.note}.json）", file=sys.stderr)
        return 1
    path, note, sha = notes[args.note]
    contract = json.loads(json.dumps(CONTRACT_TEMPLATE)
                          .replace("{note_id}", args.note).replace("{note_sha256}", sha))
    if args.format == "json":
        print(json.dumps({"note": note, "contract": contract, "relations": RELATIONS},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"== {args.note} 語意抽取契約 ==\n")
    print("【註解原文（語意抽取的唯一輸入）】")
    print(json.dumps(note, ensure_ascii=False, indent=2))
    print("\n【可用關聯類型】")
    for name, desc in RELATIONS.items():
        print(f"  - {name}：{desc}")
    print("\n【concepts.kind 可用值】" + "／".join(CONCEPT_KINDS))
    print(f"\n【輸出檔】{EXTRACT_DIR}/{args.note}.json")
    print(json.dumps(contract, ensure_ascii=False, indent=2))
    print("\n抽取原則：")
    print("  1. 只寫「註解文字真的說了」的概念與關聯，rationale 必須引註解原文；不確定就不要抽")
    print("  2. edges.target 優先用既有圖譜節點 label（先用 regulation_graph.py 查過），"
          "查不到才在 concepts 新增")
    print("  3. 概念名稱用審圖會拿來查的詞（「挑空區」而非「本案特殊空間」）")
    print(f"  4. 寫完跑：python3 tools/practice_note_graph.py validate "
          f"--extraction {EXTRACT_DIR}/{args.note}.json")
    return 0


def cmd_validate(args):
    root = Path(args.root)
    extraction = load_json(args.extraction)
    if extraction is None:
        print(f"⛔ 讀不到抽取檔：{args.extraction}", file=sys.stderr)
        return 1
    note_id = extraction.get("note_id") or Path(args.extraction).stem
    notes = {nid: (path, note, sha) for nid, path, note, sha in active_notes(root)}
    if note_id not in notes:
        print(f"⛔ {note_id} 不是 active 註解，無從驗證（抽取檔只對 {ACTIVE_DIR}/ 有效）", file=sys.stderr)
        return 2
    _, note, sha = notes[note_id]
    graph = load_json(root / GRAPH_PATH) or {"nodes": []}
    labels = {n.get("label") for n in graph.get("nodes", [])}
    problems = validate_extraction(extraction, note, sha, labels)
    if args.format == "json":
        print(json.dumps({"note_id": note_id, "problems": problems}, ensure_ascii=False, indent=2))
    elif problems:
        print(f"🔴 {note_id} 抽取檔未通過（{len(problems)} 項）：")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"🟢 {note_id} 抽取檔通過，可執行 merge。")
    return 2 if problems else 0


def cmd_merge(args):
    result = merge(args.root, args.graph, args.dry_run)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2
    if not result["ok"]:
        print(f"⛔ {result['error']}", file=sys.stderr)
        for item in result.get("pending", []):
            print(f"  - {item['note_id']}（{item['reason']}）：{item['detail']}", file=sys.stderr)
        return 2
    prefix = "（乾跑，未寫檔）" if result["dry_run"] else ""
    print(f"✅ 已併入實務註解層{prefix}：{result['notes']} 則註解 → "
          f"{result['added_nodes']} 節點／{result['added_links']} 邊"
          f"（重建前先移除舊註解節點 {result['removed_nodes']} 個）")
    print(f"   圖譜現況：{result['total_nodes']} 節點／{result['total_links']} 邊")
    if not result["dry_run"]:
        print("   接續：python3 tools/graph_status.py stamp 蓋章")
    return 0


def cmd_check(args):
    result = check(args.root, args.graph)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_check(result))
    return 0 if result["state"] == "covered" else 2


def build_parser():
    p = argparse.ArgumentParser(description="實務註解 → 知識圖譜納入層（LLM 語意抽取 ＋ 確定性合併）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("plan", help="列出待語意抽取的 active 註解（0=齊備 2=有待辦）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("contract", help="印出某註解的語意抽取契約（給 LLM 依此產出抽取檔）")
    s.add_argument("--note", required=True, help="註解 id，例：PN-20260725-001")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_contract)

    s = sub.add_parser("validate", help="驗證語意抽取檔（0=通過 2=有問題）")
    s.add_argument("--extraction", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("merge", help="把註解層併入 graph.json（冪等；抽取未齊備則拒絕）")
    s.add_argument("--graph", default=None, help="graph.json 路徑（預設 graphify-out/graph.json）")
    s.add_argument("--dry-run", action="store_true", help="只算不寫檔")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_merge)

    s = sub.add_parser("check", help="圖譜是否已納入全部 active 註解（0=已納入 2=未納入）")
    s.add_argument("--graph", default=None)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

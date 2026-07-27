#!/usr/bin/env python3
"""訓練圖譜建置：把使用者的訓練成果變成可查詢的圖譜。

只用 Python 標準庫。

    python3 tools/training_graph_build.py plan      # 哪些素材還缺語意抽取（0=齊備 2=有待辦）
    python3 tools/training_graph_build.py contract --entry {id}   # 印抽取契約給對話中的模型填
    python3 tools/training_graph_build.py validate --extraction training/graph_extractions/{id}.json
    python3 tools/training_graph_build.py build     # 產生 training/graph.json
    python3 tools/training_graph_build.py check     # 圖譜是否跟上訓練素材（0=跟上 2=沒跟上）

**為什麼訓練圖譜要跟法規圖譜分家。** 早期兩者混在同一個 graph.json：法典層一重建就會
把訓練層沖掉，所以每次重建都被迫「先把註解併回去才准蓋章」，把兩件本來各自獨立的事
綁成一條必須全過的鏈——鏈上任何一環卡住，整條路就斷，訓練成果就進不了圖譜。
更糟的是 `update_guard.py` 把 `graphify-out/*` 標為 SHARED（與上游共編、更新時可能被覆寫），
等於使用者的訓練成果住在會被蓋掉的地段，與 AGENTS.md 底線 6 直接衝突。

分家之後：訓練圖譜是 `training/graph.json`（USER 所有），法規圖譜重建碰不到它；
查詢端由 `regulation_graph.py` 在**記憶體裡**同時載入兩份，審圖指令完全不必改。

**跨圖譜參照以 label 為耐久鍵。** 訓練圖譜的邊會指向法規圖譜的節點（`第19條`、
`自動撒水設備`）。邊上同時記 `target_label`（正典寫法，跨重建穩定）與 `target_id`
（建置當下解析出來的快取）。法規圖譜重建後 id 若對不上，邊會被標 `dangling` 留在圖譜裡
並由 `check` 紅字列出——**絕不因為解析不到就把使用者的訓練成果刪掉**。

三個來源層：

- **實務註解層**：`practice_notes/active/*.json`，走 `practice_note_graph.py` 的語意抽取契約。
- **修正筆記層**：`rules/review_corrections.md`，結構規則（`### 日期 — 標題` ＋ 七個固定欄位），
  骨架確定性解析，條號引用直接從欄位文字抽。
- **判斷慣例層**：`rules/stage_two_judgment_rules.md`，`### §14 滅火器` 的條號寫在標題裡。

後兩層的**骨架不需要 LLM 也不需要 API key**；語意抽取只用來補「文字裡沒寫出條號的關聯」，
而且是選用的加值，缺了不會擋住建置——這與實務註解層不同（註解的語意抽取是它的全部價值）。

邊界（呼應 AGENTS.md 底線 1、2）：圖譜只是索引與導覽，不是門檻數值來源。
本層所有節點都帶警語欄位，援引時必須回到條文原文核對。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tools import graph_labels, practice_note_graph
except ImportError:
    import graph_labels
    import practice_note_graph

load_json = practice_note_graph.load_json
write_json = practice_note_graph.write_json

TRAINING_GRAPH_PATH = "training/graph.json"
EXTRACT_DIR = "training/graph_extractions"
REGULATION_GRAPH_PATH = "graphify-out/graph.json"

CORRECTIONS_PATH = "rules/review_corrections.md"
JUDGMENT_PATH = "rules/stage_two_judgment_rules.md"

LAYER_NOTE = practice_note_graph.LAYER
LAYER_CORRECTION = "review_correction"
LAYER_JUDGMENT = "judgment_rule"
TRAINING_LAYERS = (LAYER_NOTE, LAYER_CORRECTION, LAYER_JUDGMENT)

CORRECTION_NOTICE = ("審圖修正筆記為使用者確認之實務慣例，未經 governance/ 核定；"
                     "援引時須附「本判斷慣例未經消防專業人員核定，以現行法規為準」")
JUDGMENT_NOTICE = ("第二階段判斷慣例，非法規條文且未經 governance/ 核定；"
                   "門檻數值一律回條文原文與 fire_code_calc.py 核對")

EXTRACTION_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# 法規圖譜（只讀，用來解析跨圖譜參照）

def regulation_index(root="."):
    """法規圖譜的 LabelIndex。

    法規圖譜缺席時回空索引而不是報錯——訓練圖譜必須能獨立建置，
    否則又會回到「法典層卡住連帶訓練成果也進不了圖譜」的老問題。
    """
    graph = load_json(Path(root) / REGULATION_GRAPH_PATH)
    return graph_labels.LabelIndex((graph or {}).get("nodes", []))


# ---------------------------------------------------------------------------
# markdown 筆記解析（純確定性）

_H2 = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_H3 = re.compile(r"^###\s+(?P<title>.+?)\s*$")
_CORRECTION_HEAD = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})\s*[—–-]\s*(?P<title>.+)$")
CORRECTION_FIELDS = ("Status", "Last confirmed", "Error", "Correction",
                     "Scope", "Evidence", "Notes")
_FIELD = re.compile(r"^-\s+(?P<name>" + "|".join(CORRECTION_FIELDS) + r")\s*[:：]\s*(?P<value>.*)$")
_BULLET = re.compile(r"^-\s+(?P<body>.+)$")
_BOLD_TERM = re.compile(r"^\*\*(?P<term>[^*]+)\*\*")

# 修正筆記中影響語意的欄位——`Last confirmed` 只是複核日期，變動不該觸發重抽。
CORRECTION_SEMANTIC_FIELDS = ("Status", "Error", "Correction", "Scope", "Notes")


def _strip_markup(text):
    """去掉行內強調與行內程式碼標記，讓欄位值可以直接當人看的文字用。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", str(text))
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return graph_labels.normalize_text(text)


def _sections(lines, pattern):
    """依標題切段，回傳 [(標題, [內文行])]。"""
    found, title, body = [], None, []
    for line in lines:
        match = pattern.match(line)
        if match:
            if title is not None:
                found.append((title, body))
            title, body = match.group("title"), []
        elif title is not None:
            body.append(line)
    if title is not None:
        found.append((title, body))
    return found


def parse_corrections(text):
    """`rules/review_corrections.md` → [{date,title,fields,...}]。

    欄位值可跨行（續行是縮排的），一律併回同一個欄位。
    """
    entries = []
    for heading, body in _sections(text.splitlines(), _H3):
        head = _CORRECTION_HEAD.match(graph_labels.normalize_text(heading))
        if not head:
            continue
        fields, current = {}, None
        for line in body:
            match = _FIELD.match(line)
            if match:
                current = match.group("name")
                fields[current] = match.group("value").strip()
            elif current and line.strip():
                fields[current] = (fields[current] + " " + line.strip()).strip()
            elif not line.strip():
                current = None
        entries.append({
            "date": head.group("date"),
            "title": _strip_markup(head.group("title")),
            "status": _strip_markup(fields.get("Status", "")) or "Active",
            "fields": {k: _strip_markup(v) for k, v in fields.items()},
        })
    return entries


def parse_judgment_rules(text):
    """`rules/stage_two_judgment_rules.md` → [{kind,label,body,...}]。

    兩種條目：`## 通案認定` 底下的每個通則 bullet，與 `## 逐條判斷差異` 底下的
    每個 `### §X 設備名` 小節。
    """
    lines = text.splitlines()
    entries = []
    for heading, body in _sections(lines, _H2):
        title = graph_labels.normalize_text(heading)
        if title.startswith("通案認定"):
            for bullet in _top_level_bullets(body):
                term = _BOLD_TERM.match(bullet)
                label = _strip_markup(term.group("term")) if term else _strip_markup(bullet)[:24]
                entries.append({"kind": "general", "label": label,
                                "article": None, "body": _strip_markup(bullet)})
        elif title.startswith("逐條判斷差異"):
            for sub, sub_body in _sections(body, _H3):
                sub = graph_labels.normalize_text(sub)
                number = graph_labels.parse_article_ref(sub.split()[0]) if sub.split() else None
                body_text = "\n".join(_strip_markup(b) for b in _top_level_bullets(sub_body))
                entries.append({"kind": "article", "label": sub,
                                "article": number, "body": body_text})
    return entries


def _top_level_bullets(lines):
    """頂層 `- ` 條列（續行併入同一則）。"""
    bullets, current = [], None
    for line in lines:
        match = _BULLET.match(line)
        if match:
            if current is not None:
                bullets.append(current)
            current = match.group("body").strip()
        elif current is not None and line.strip():
            current = current + " " + line.strip()
        elif not line.strip():
            if current is not None:
                bullets.append(current)
            current = None
    if current is not None:
        bullets.append(current)
    return bullets


def _digest(*parts):
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def correction_entries(root="."):
    path = Path(root) / CORRECTIONS_PATH
    if not path.is_file():
        return []
    entries = parse_corrections(path.read_text(encoding="utf-8"))
    for entry in entries:
        entry["id"] = (f"correction_{entry['date'].replace('-', '')}_"
                       f"{graph_labels.norm_id(entry['title'])[:40]}")
        entry["semantic_sha256"] = _digest(
            entry["title"], *(entry["fields"].get(f, "") for f in CORRECTION_SEMANTIC_FIELDS))
        entry["source_file"] = CORRECTIONS_PATH
    return entries


def judgment_entries(root="."):
    path = Path(root) / JUDGMENT_PATH
    if not path.is_file():
        return []
    entries = parse_judgment_rules(path.read_text(encoding="utf-8"))
    for entry in entries:
        slug = (f"article_{entry['article']}" if entry["article"]
                else f"general_{graph_labels.norm_id(entry['label'])[:40]}")
        entry["id"] = f"judgment_{slug}"
        entry["semantic_sha256"] = _digest(entry["label"], entry["body"])
        entry["source_file"] = JUDGMENT_PATH
    return entries


def markdown_entries(root="."):
    return correction_entries(root) + judgment_entries(root)


# ---------------------------------------------------------------------------
# 建層

def _link(source_id, target, relation, confidence, rationale, index, layer,
          source_file, evidence=None):
    """建一條邊。解析不到 target 時**不丟棄**，標 dangling 留在圖譜裡等修。"""
    resolution = index.resolve(target)
    canonical = graph_labels.article_label(target) or resolution.matched_label or str(target)
    resolved = resolution.how in graph_labels.RESOLVED_HOWS and resolution.node_id
    return {
        "relation": relation,
        "confidence": confidence,
        "confidence_score": 1.0,
        "weight": 1.0,
        "layer": layer,
        "source_file": source_file,
        "source_location": None,
        "rationale": rationale,
        "evidence": evidence,
        "source": source_id,
        "target": resolution.node_id,
        "target_label": canonical,
        # 解析不到時仍記下「本來要指向法規圖譜」——訓練層的概念節點是同一次建置產生的，
        # 一定解析得到，所以懸空的目標必然屬於法規圖譜。
        "target_graph": (practice_note_graph._target_graph(resolution.node_id)
                         if resolved else "regulation"),
        "dangling": not resolved,
    }


def build_markdown_layer(root, entries, index):
    """修正筆記層與判斷慣例層的節點與邊（骨架確定性，語意抽取為選用加值）。"""
    nodes, links = [], []
    for entry in entries:
        is_correction = entry["source_file"] == CORRECTIONS_PATH
        layer = LAYER_CORRECTION if is_correction else LAYER_JUDGMENT
        notice = CORRECTION_NOTICE if is_correction else JUDGMENT_NOTICE
        label = (f"{entry['date']} {entry['title']}" if is_correction else entry["label"])
        node = {
            "label": label,
            "file_type": layer,
            "layer": layer,
            "source_file": entry["source_file"],
            "entry_id": entry["id"],
            "entry_semantic_sha256": entry["semantic_sha256"],
            "status": entry.get("status", "Active"),
            "notice": notice,
            "norm_label": label.lower(),
            "id": entry["id"],
        }
        if is_correction:
            node.update({"correction_date": entry["date"],
                         "summary": entry["fields"].get("Correction", ""),
                         "scope": entry["fields"].get("Scope", ""),
                         "evidence": entry["fields"].get("Evidence", "")})
        else:
            node.update({"summary": entry["body"][:400], "judgment_kind": entry["kind"]})
        nodes.append(node)
        index.add_node(node)

        # 條號引用：修正筆記從各欄位文字抽，判斷慣例的條號直接寫在標題裡。
        if is_correction:
            haystack = " ".join(entry["fields"].get(f, "") for f in CORRECTION_SEMANTIC_FIELDS)
            numbers = graph_labels.find_article_refs(haystack)
        else:
            numbers = ([entry["article"]] if entry["article"]
                       else graph_labels.find_article_refs(entry["body"]))
        for number in numbers:
            label_ = graph_labels.article_label(number)
            links.append(_link(entry["id"], label_, "supplements", "MECHANICAL",
                               f"筆記文字引用了 {label_}", index, layer,
                               entry["source_file"], evidence=label_))

        # 語意抽取（選用）：補「文字裡沒寫出條號」的關聯
        extraction = load_json(Path(root) / EXTRACT_DIR / f"{entry['id']}.json")
        if not extraction or extraction.get("entry_semantic_sha256") != entry["semantic_sha256"]:
            continue
        for edge in extraction.get("edges", []):
            target = str(edge.get("target", "")).strip()
            if not target:
                continue
            links.append(_link(entry["id"], target, edge.get("relation"), "EXTRACTED",
                               edge.get("rationale"), index, layer, entry["source_file"]))
    return nodes, links


# ---------------------------------------------------------------------------
# build

def build(root=".", dry_run=False, only=None, skip_pending=False):
    root = Path(root)
    index = regulation_index(root)

    notes = practice_note_graph.active_notes(root)
    status = practice_note_graph.plan(root, index)
    pending_ids = {p["note_id"] for p in status["pending"]}

    selected, skipped = [], []
    for ref in notes:
        if only and ref.note_id not in only:
            continue
        if ref.note_id in pending_ids:
            reason = next(p for p in status["pending"] if p["note_id"] == ref.note_id)
            skipped.append(reason)
            continue
        selected.append(ref)

    if pending_ids and not (skip_pending or only):
        return {"ok": False,
                "error": "有 active 註解尚未完成語意抽取，拒絕建層"
                         "（避免圖譜與註解庫不一致；確知要先建其餘者用 --skip-pending）",
                "pending": status["pending"]}

    note_nodes, note_links, unresolved = practice_note_graph.build_layer(root, selected, index)
    entries = markdown_entries(root)
    md_nodes, md_links = build_markdown_layer(root, entries, index)

    nodes = note_nodes + md_nodes
    links = note_links + md_links
    dangling = [l for l in links if l["dangling"]]

    graph = {
        "directed": True,
        "multigraph": False,
        "graph": {
            "kind": "training",
            "built_at": datetime.now(timezone.utc).isoformat(),
            "regulation_graph_present": bool(index.labels()),
            "build_report": {
                "notes": [r.note_id for r in selected],
                "skipped": skipped,
                "markdown_entries": len(entries),
                "unresolved": unresolved,
                "dangling": len(dangling),
            },
        },
        "nodes": nodes,
        "links": links,
    }
    if not dry_run:
        write_json(root / TRAINING_GRAPH_PATH, graph)
    return {"ok": True, "dry_run": dry_run, "notes": len(selected), "skipped": skipped,
            "markdown_entries": len(entries), "nodes": len(nodes), "links": len(links),
            "dangling": len(dangling), "unresolved": unresolved}


def format_build(result):
    if not result["ok"]:
        lines = [f"⛔ {result['error']}"]
        for item in result.get("pending", []):
            lines.append(f"  - {item['note_id']}（{item['reason']}）：{item['detail']}")
        return "\n".join(lines)
    prefix = "（乾跑，未寫檔）" if result["dry_run"] else ""
    lines = [f"✅ 已建訓練圖譜{prefix}：實務註解 {result['notes']} 則、"
             f"markdown 筆記 {result['markdown_entries']} 則 → "
             f"{result['nodes']} 節點／{result['links']} 邊"]
    for item in result["skipped"]:
        lines.append(f"  ⚠️ 略過 {item['note_id']}（{item['reason']}）：{item['detail']}")
    if result["dangling"]:
        lines.append(f"  ⚠️ {result['dangling']} 條邊指向法規圖譜中找不到的節點（已標 dangling 保留）"
                     "——跑 check 看明細")
    if not result["dry_run"]:
        lines.append("   接續：python3 tools/graph_status.py stamp --graph training")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# check：圖譜是否跟上訓練素材

def check(root="."):
    root = Path(root)
    graph = load_json(root / TRAINING_GRAPH_PATH)
    notes = practice_note_graph.active_notes(root)
    entries = markdown_entries(root)

    if graph is None:
        # 訓練圖譜是**衍生**產物，隨時可由素材重建。倉庫本身就帶了 markdown 筆記，
        # 所以「還沒建」是全新安裝的正常狀態，不該讓開場導引亮紅燈；
        # 但只要使用者有了自己的實務註解，沒建就是查不到訓練成果，那才是紅燈。
        state = "absent" if notes else ("not_built" if entries else "covered")
        return {"state": state, "graph_present": False, "active": len(notes),
                "entries": len(entries), "merged": 0,
                "missing": [r.note_id for r in notes] + [e["id"] for e in entries],
                "stale": [], "orphan": [], "dangling": [], "skipped": []}

    in_graph = {n.get("note_id"): n for n in graph.get("nodes", [])
                if n.get("layer") == LAYER_NOTE and n.get("note_id")}
    by_entry = {n.get("entry_id"): n for n in graph.get("nodes", []) if n.get("entry_id")}

    missing, stale = [], []
    for ref in notes:
        node = in_graph.get(ref.note_id)
        if node is None:
            missing.append(ref.note_id)
        elif node.get("note_semantic_sha256") != ref.semantic_sha:
            stale.append(ref.note_id)
    for entry in entries:
        node = by_entry.get(entry["id"])
        if node is None:
            missing.append(entry["id"])
        elif node.get("entry_semantic_sha256") != entry["semantic_sha256"]:
            stale.append(entry["id"])

    known = {r.note_id for r in notes} | {e["id"] for e in entries}
    orphan = sorted((set(in_graph) | set(by_entry)) - known)
    dangling = [{"source": l.get("source"), "target_label": l.get("target_label")}
                for l in graph.get("links", []) if l.get("dangling")]
    skipped = (graph.get("graph", {}).get("build_report", {}) or {}).get("skipped", [])

    state = "covered" if not (missing or stale or orphan or dangling or skipped) else "uncovered"
    return {"state": state, "graph_present": True, "active": len(notes),
            "entries": len(entries), "merged": len(in_graph) + len(by_entry),
            "missing": missing, "stale": stale, "orphan": orphan,
            "dangling": dangling, "skipped": skipped}


BUILD_HINT = ("重建訓練圖譜：python3 tools/training_graph_build.py plan → "
              "依契約做語意抽取 → python3 tools/training_graph_build.py build")


def format_check(result):
    lines = ["== 訓練圖譜納入狀態 =="]
    if not result.get("graph_present", True):
        if result["state"] == "covered":
            lines.append("✅ 尚無訓練成果，訓練圖譜無須建立")
        elif result["state"] == "not_built":
            lines.append(f"ℹ️ 訓練圖譜尚未建置——倉庫內已有 {result['entries']} 則審圖筆記與"
                         "判斷慣例，建起來審圖時就查得到")
            lines.append("→ python3 tools/training_graph_build.py build")
        else:
            lines.append(f"⛔ 找不到 {TRAINING_GRAPH_PATH}——"
                         f"{result['active']} 則註解、{result['entries']} 則筆記無處可查")
            lines.append(f"→ {BUILD_HINT}")
        return "\n".join(lines)
    if result["state"] == "covered":
        lines.append(f"✅ 已納入 —— 實務註解 {result['active']} 則、markdown 筆記 "
                     f"{result['entries']} 則全部在訓練圖譜中")
        return "\n".join(lines)
    lines.append(f"⛔ 未跟上 —— 註解 {result['active']} 則、筆記 {result['entries']} 則，"
                 f"圖譜內 {result['merged']} 則")
    for item in result["missing"]:
        lines.append(f"  [缺漏] {item} 不在訓練圖譜中——查圖譜查不到這則訓練成果")
    for item in result["stale"]:
        lines.append(f"  [過期] {item} 的內容已變更，圖譜內是舊版")
    for item in result["orphan"]:
        lines.append(f"  [殘留] {item} 已非現行素材，卻仍留在圖譜中")
    for item in result["skipped"]:
        lines.append(f"  [略過] {item['note_id']}（{item['reason']}）：{item['detail']}")
    for item in result["dangling"]:
        lines.append(f"  [懸空] {item['source']} 指向的「{item['target_label']}」"
                     "在法規圖譜中找不到——訓練成果已保留，但查不到這條關聯")
    lines.append(f"→ {BUILD_HINT}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# plan／contract／validate（markdown 筆記的選用語意抽取）

CONTRACT_TEMPLATE = {
    "schema_version": EXTRACTION_SCHEMA_VERSION,
    "entry_id": "{entry_id}",
    "entry_semantic_sha256": "{entry_semantic_sha256}",
    "extracted_by": "（填語意抽取者：模型或 agent 名稱）",
    "extracted_at": "（填 ISO 8601 時間）",
    "edges": [
        {"target": "（既有圖譜節點 label，例：自動撒水設備／無開口樓層）",
         "relation": "|".join(practice_note_graph.RELATIONS),
         "rationale": "（為什麼有這條關聯——引筆記原文）"}
    ],
}


def plan(root="."):
    """markdown 筆記的語意抽取狀態。缺抽取檔不是錯——骨架已經確定性建好了。"""
    root = Path(root)
    entries = markdown_entries(root)
    enriched, pending = [], []
    for entry in entries:
        extraction = load_json(root / EXTRACT_DIR / f"{entry['id']}.json")
        if extraction is None:
            pending.append({"entry_id": entry["id"], "reason": "missing"})
        elif extraction.get("entry_semantic_sha256") != entry["semantic_sha256"]:
            pending.append({"entry_id": entry["id"], "reason": "stale"})
        else:
            enriched.append(entry["id"])
    notes = practice_note_graph.plan(root, regulation_index(root))
    return {"entries": len(entries), "enriched": enriched, "pending": pending, "notes": notes}


def format_plan(result):
    lines = [practice_note_graph.format_plan(result["notes"]), "",
             "== markdown 筆記語意抽取狀態（選用加值）=="]
    lines.append(f"筆記條目：{result['entries']} 則｜已加值：{len(result['enriched'])} 則"
                 f"｜可加值：{len(result['pending'])} 則")
    if result["pending"]:
        lines.append("  骨架（條目節點與條號引用）已確定性建好，不缺這一步也查得到；")
        lines.append("  要補「文字裡沒寫出條號的關聯」才需要語意抽取：")
        for item in result["pending"][:8]:
            lines.append(f"    · {item['entry_id']}（{item['reason']}）")
        if len(result["pending"]) > 8:
            lines.append(f"    · …另有 {len(result['pending']) - 8} 則")
        lines.append("  → python3 tools/training_graph_build.py contract --entry {id}")
    return "\n".join(lines)


def validate_entry_extraction(extraction, entry, index):
    problems = []
    if not isinstance(extraction, dict):
        return ["抽取檔不是物件"]
    if extraction.get("entry_id") != entry["id"]:
        problems.append(f"entry_id 與筆記不符：{extraction.get('entry_id')!r}")
    if extraction.get("entry_semantic_sha256") != entry["semantic_sha256"]:
        problems.append("與現行筆記內容不符——筆記已變更，須重新語意抽取")
    for field in ("extracted_by", "extracted_at"):
        value = extraction.get(field)
        if not str(value or "").strip() or practice_note_graph.has_placeholder(value):
            problems.append(f"{field} 必填且不得留樣板文字")
    edges = extraction.get("edges")
    if not isinstance(edges, list) or not edges:
        problems.append("edges 須為非空陣列——沒有產出關聯就不需要抽取檔")
        edges = []
    for i, edge in enumerate(edges):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} 須為物件")
            continue
        target = str(edge.get("target", "")).strip()
        if not target or practice_note_graph.has_placeholder(target):
            problems.append(f"{where}.target 必填且不得留樣板文字")
        else:
            resolution = index.resolve(target)
            if resolution.how not in graph_labels.RESOLVED_HOWS:
                problems.append(f"{where}.target {graph_labels.describe(resolution, target)}")
        if edge.get("relation") not in practice_note_graph.RELATIONS:
            problems.append(f"{where}.relation 應為 "
                            f"{'／'.join(practice_note_graph.RELATIONS)}")
        if not str(edge.get("rationale", "")).strip():
            problems.append(f"{where}.rationale 必填——須說明此關聯的依據")
    return problems


# ---------------------------------------------------------------------------
# CLI

def cmd_plan(args):
    result = plan(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_plan(result))
    return 2 if result["notes"]["pending"] else 0


def cmd_build(args):
    result = build(args.root, dry_run=args.dry_run, only=set(args.only or ()),
                   skip_pending=args.skip_pending)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_build(result), file=sys.stderr if not result["ok"] else sys.stdout)
    return 0 if result["ok"] else 2


OK_STATES = ("covered", "not_built")


def cmd_check(args):
    result = check(args.root)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_check(result))
    return 0 if result["state"] in OK_STATES else 2


def cmd_contract(args):
    root = Path(args.root)
    entries = {e["id"]: e for e in markdown_entries(root)}
    if args.entry not in entries:
        print(f"⛔ 找不到筆記條目 {args.entry}", file=sys.stderr)
        return 1
    entry = entries[args.entry]
    contract = json.loads(json.dumps(CONTRACT_TEMPLATE)
                          .replace("{entry_id}", entry["id"])
                          .replace("{entry_semantic_sha256}", entry["semantic_sha256"]))
    if args.format == "json":
        print(json.dumps({"entry": entry, "contract": contract}, ensure_ascii=False, indent=2))
        return 0
    print(f"== {entry['id']} 語意抽取契約 ==\n")
    print("【筆記原文（語意抽取的唯一輸入）】")
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    print("\n【可用關聯類型】")
    for name, desc in practice_note_graph.RELATIONS.items():
        print(f"  - {name}：{desc}")
    print(f"\n【輸出檔】{EXTRACT_DIR}/{entry['id']}.json")
    print(json.dumps(contract, ensure_ascii=False, indent=2))
    print("\n抽取原則：")
    print("  1. 條號引用已由工具確定性抽出，**不要重複宣告**；只補文字裡沒寫出條號的關聯")
    print("  2. 只寫筆記文字真的說了的關聯，rationale 必須引原文；不確定就不要抽")
    print("  3. target 優先用既有圖譜節點 label（先用 regulation_graph.py 查過）")
    return 0


def cmd_validate(args):
    root = Path(args.root)
    extraction = load_json(args.extraction)
    if extraction is None:
        print(f"⛔ 讀不到抽取檔：{args.extraction}", file=sys.stderr)
        return 1
    entry_id = extraction.get("entry_id") or Path(args.extraction).stem
    entries = {e["id"]: e for e in markdown_entries(root)}
    if entry_id not in entries:
        print(f"⛔ {entry_id} 不是現行筆記條目，無從驗證", file=sys.stderr)
        return 2
    problems = validate_entry_extraction(extraction, entries[entry_id], regulation_index(root))
    if args.format == "json":
        print(json.dumps({"entry_id": entry_id, "problems": problems},
                         ensure_ascii=False, indent=2))
    elif problems:
        print(f"🔴 {entry_id} 抽取檔未通過（{len(problems)} 項）：")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"🟢 {entry_id} 抽取檔通過，可執行 build。")
    return 2 if problems else 0


def build_parser():
    p = argparse.ArgumentParser(description="訓練圖譜建置（實務註解 ＋ markdown 筆記）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("plan", help="哪些素材還缺語意抽取（0=齊備 2=有待辦）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("build", help="產生 training/graph.json")
    s.add_argument("--dry-run", action="store_true", help="只算不寫檔")
    s.add_argument("--only", action="append", metavar="NOTE_ID",
                   help="只重建指名的註解（可重複給）")
    s.add_argument("--skip-pending", action="store_true",
                   help="尚未完成語意抽取的註解列入略過清單，先建其餘者")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("check", help="訓練圖譜是否跟上素材（0=跟上 2=沒跟上）")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("contract", help="印出某筆記條目的語意抽取契約")
    s.add_argument("--entry", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_contract)

    s = sub.add_parser("validate", help="驗證筆記條目的語意抽取檔（0=通過 2=有問題）")
    s.add_argument("--extraction", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_validate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

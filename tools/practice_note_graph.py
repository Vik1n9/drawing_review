#!/usr/bin/env python3
"""實務註解 → 訓練圖譜的註解層（LLM 語意抽取 ＋ 確定性建層）。

只用 Python 標準庫。

    python3 tools/practice_note_graph.py plan                 # 誰還沒語意抽取（0=齊備 2=有待辦）
    python3 tools/practice_note_graph.py contract --note {id} # 印出該註解的抽取契約（給 LLM 填）
    python3 tools/practice_note_graph.py validate --extraction practice_notes/graph_extractions/{id}.json
    python3 tools/practice_note_graph.py migrate              # v1 抽取檔升版（預設乾跑）

建圖譜請跑 `python3 tools/training_graph_build.py build`——本模組只負責**註解層**，
不自己寫檔。訓練圖譜還含 markdown 筆記層與判斷慣例層，由該工具統籌。

為什麼要分成「LLM 抽取」＋「工具建層」兩段：

- 註解的 `scenario.summary`／`judgment.detail` 是自由文字，**沒有固定格式**，
  要抽出「這則註解牽涉哪些概念、關聯到哪些既有條文與設備」只能靠語意理解；
  規則式關鍵字比對會漏抽也會誤抽。語意抽取由 `/practice-note` 第七步的 LLM 完成，
  結果寫成 `practice_notes/graph_extractions/{註解 id}.json`。
- 但**寫進圖譜的動作必須是確定性的**：本模組只搬運抽取檔裡已經寫明的節點與邊，
  自己絕不從註解文字推導任何語意關聯（唯一例外是 `ref_article`／`judgment.equipment`
  這兩個結構化欄位產生的錨點邊，標記為 MECHANICAL，用途是保證可追溯）。

**抽取檔綁的是註解的「語意摘要」，不是整個檔案的位元組。** 早期版本對整檔取 sha256，
結果補填 `approved` 這種與語意無關的治理欄位就會判定抽取過期、整批拒絕建層——
訓練成果因此進不了圖譜。現在只有 SEMANTIC_FIELDS 變動才要求重新抽取；
但**未知的新欄位一律保守計入摘要**，寧可多判過期，也不要漏掉真正的語意變更（底線 3）。

邊界（呼應 AGENTS.md 底線 1、2）：圖譜只是索引與導覽。
註解節點進圖譜是為了「查得到」，不是為了讓它變成法規；查詢輸出一律附註解警語，
援引時必須同時列出所補充的法條與註解 ID。
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tools import graph_labels
except ImportError:
    import graph_labels

ACTIVE_DIR = "practice_notes/active"
EXTRACT_DIR = "practice_notes/graph_extractions"

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

EXTRACTION_SCHEMA_VERSION = 2

# 影響語意的欄位——這些變了就必須重新語意抽取。
SEMANTIC_FIELDS = ("id", "ref_article", "ref_rule_ids", "scenario", "judgment", "source_case")
# 治理／流程欄位——變動不影響「這則註解在說什麼」，不該要求重抽。
GOVERNANCE_FIELDS = ("approved", "governance_log", "created", "updated", "status", "notice",
                     "verified_by", "verified_date", "reviewer", "review_log", "last_confirmed")

CONTRACT_TEMPLATE = {
    "schema_version": EXTRACTION_SCHEMA_VERSION,
    "note_id": "{note_id}",
    "note_semantic_sha256": "{note_semantic_sha256}",
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


# ---------------------------------------------------------------------------
# 語意摘要

def unknown_fields(note):
    """既不在語意白名單、也不在治理白名單的頂層欄位。

    白名單制下，新增的欄位預設會被排除在摘要外——那正是「語意變了卻沒判過期」的破口。
    所以未知欄位一律保守計入摘要，並向使用者回報，要求把它歸類。
    """
    return sorted(set(note) - set(SEMANTIC_FIELDS) - set(GOVERNANCE_FIELDS))


def _canonical(value):
    """字串正規化到「肉眼看起來一樣就算一樣」的程度，避免空白差異觸發重抽。"""
    if isinstance(value, str):
        return graph_labels.normalize_text(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def semantic_view(note):
    """註解 → 只含語意相關內容的正規化檢視（摘要的輸入）。"""
    view = {}
    for field in SEMANTIC_FIELDS:
        if field not in note:
            continue
        if field == "ref_article":
            view[field] = graph_labels.article_label(note[field]) or _canonical(note[field])
        elif field == "ref_rule_ids":
            ids = note[field] if isinstance(note[field], list) else [note[field]]
            view[field] = sorted({str(i).strip() for i in ids})
        else:
            view[field] = _canonical(note[field])
    for field in unknown_fields(note):
        view[field] = _canonical(note[field])
    return view


def semantic_digest(note):
    payload = json.dumps(semantic_view(note), sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


NoteRef = namedtuple("NoteRef", "note_id path note byte_sha semantic_sha")


def active_notes(root="."):
    """回傳 [NoteRef]，只含 status 為 active 者。"""
    directory = Path(root) / ACTIVE_DIR
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        note = load_json(path)
        if not isinstance(note, dict) or note.get("status") != "active":
            continue
        found.append(NoteRef(note.get("id", path.stem), path, note,
                             sha256_file(path), semantic_digest(note)))
    return found


def extraction_path(root, note_id):
    return Path(root) / EXTRACT_DIR / f"{note_id}.json"


def node_id_for(note_id):
    return f"{NODE_PREFIX}{note_id}"


# 舊名保留：其他模組與文件仍以這兩個名字稱呼條號正規化。
normalize_article = graph_labels.parse_article_ref
article_label = graph_labels.article_label
norm_id = graph_labels.norm_id


# ---------------------------------------------------------------------------
# 抽取檔與註解的綁定狀態

DIGEST_OK, DIGEST_STALE, DIGEST_LEGACY = "ok", "stale", "legacy"


def digest_state(extraction, ref):
    """抽取檔是否仍對應現行註解內容。

    v2 比語意摘要；v1 比整檔位元組摘要——位元組都沒變，語意當然也沒變，
    所以 v1 檔只要位元組對得上就照樣可用，不必為了升版而重跑語意抽取。
    """
    if not isinstance(extraction, dict):
        return DIGEST_STALE
    if int(extraction.get("schema_version") or 1) >= 2:
        return DIGEST_OK if extraction.get("note_semantic_sha256") == ref.semantic_sha \
            else DIGEST_STALE
    return DIGEST_LEGACY if extraction.get("note_sha256") == ref.byte_sha else DIGEST_STALE


# ---------------------------------------------------------------------------
# 抽取檔驗證（純結構檢查，不做法規判斷、不補內容）

def has_placeholder(value):
    return isinstance(value, str) and (PLACEHOLDER in value or value.strip().startswith("（填"))


def _as_index(labels_or_index):
    if isinstance(labels_or_index, graph_labels.LabelIndex):
        return labels_or_index
    return graph_labels.LabelIndex.from_labels(labels_or_index or ())


def validate_extraction(extraction, ref, index):
    """回傳 problems 清單。`index` 為 LabelIndex（或 label 集合）供解析 edge target。"""
    problems = []
    if not isinstance(extraction, dict):
        return ["抽取檔不是物件"]
    index = _as_index(index)

    if extraction.get("note_id") != ref.note_id:
        problems.append(f"note_id 與註解不符：抽取檔 {extraction.get('note_id')!r}、"
                        f"註解 {ref.note_id!r}")
    if digest_state(extraction, ref) == DIGEST_STALE:
        problems.append("與現行註解內容不符——註解的語意欄位已變更，須重新語意抽取")
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
                        "不得建層（要嘛補抽取，要嘛說明該註解為何無法入圖譜）")

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
            problems.append(f"{where}.kind 應為 {'／'.join(CONCEPT_KINDS)}，"
                            f"實得 {concept.get('kind')!r}")
        if not str(concept.get("rationale", "")).strip() or has_placeholder(concept.get("rationale")):
            problems.append(f"{where}.rationale 必填——語意抽取須說明從註解哪句話讀出此概念")

    # 本抽取檔自己宣告的概念也是合法的 edge target，但它們還不在圖譜裡，
    # 所以驗證時用一份衍生索引，不動呼叫端持有的那份。
    scoped = index.with_declared(concept_labels)
    # 法規圖譜不在時無從分辨「target 打錯字」與「圖譜還沒建」——此時不驗 target，
    # 讓那些邊在建層時標為懸空即可。訓練成果不該因為法規圖譜缺席就進不了圖譜。
    check_targets = bool(index.labels())
    for i, edge in enumerate(edges):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            problems.append(f"{where} 須為物件")
            continue
        target = str(edge.get("target", "")).strip()
        if not target or has_placeholder(target):
            problems.append(f"{where}.target 必填且不得留樣板文字")
        elif check_targets:
            resolution = scoped.resolve(target)
            if resolution.how not in graph_labels.RESOLVED_HOWS:
                problems.append(f"{where}.target {graph_labels.describe(resolution, target)}")
        if edge.get("relation") not in RELATIONS:
            problems.append(f"{where}.relation 應為 {'／'.join(RELATIONS)}，"
                            f"實得 {edge.get('relation')!r}")
        if not str(edge.get("rationale", "")).strip() or has_placeholder(edge.get("rationale")):
            problems.append(f"{where}.rationale 必填——語意抽取須說明此關聯的依據")

    return problems


# ---------------------------------------------------------------------------
# plan：誰還沒抽取

def plan(root=".", index=None):
    """回報每一則 active 註解的語意抽取狀態。`index` 為法規圖譜的 LabelIndex。"""
    notes = active_notes(root)
    index = _as_index(index)
    pending, ready, migratable, unknown = [], [], [], []
    for ref in notes:
        if unknown_fields(ref.note):
            unknown.append({"note_id": ref.note_id, "fields": unknown_fields(ref.note)})
        epath = extraction_path(root, ref.note_id)
        extraction = load_json(epath)
        if extraction is None:
            pending.append({"note_id": ref.note_id, "reason": "missing",
                            "detail": f"缺語意抽取檔 {epath.relative_to(Path(root)).as_posix()}"})
            continue
        state = digest_state(extraction, ref)
        if state == DIGEST_STALE:
            pending.append({"note_id": ref.note_id, "reason": "stale",
                            "detail": "註解的語意欄位已變更，抽取檔過期，須重新語意抽取"})
            continue
        problems = validate_extraction(extraction, ref, index)
        if problems:
            pending.append({"note_id": ref.note_id, "reason": "invalid",
                            "detail": "；".join(problems)})
            continue
        if state == DIGEST_LEGACY:
            migratable.append(ref.note_id)
        ready.append(ref.note_id)
    return {"active": len(notes), "ready": sorted(ready), "pending": pending,
            "migratable": sorted(migratable), "unknown_fields": unknown}


def format_plan(result):
    lines = ["== 實務註解語意抽取狀態 =="]
    lines.append(f"active 註解：{result['active']} 則｜已可建層：{len(result['ready'])} 則"
                 f"｜待處理：{len(result['pending'])} 則")
    for item in result["pending"]:
        lines.append(f"  ⛔ {item['note_id']}（{item['reason']}）：{item['detail']}")
    for item in result.get("unknown_fields", []):
        lines.append(f"  ⚠️ {item['note_id']} 含未分類欄位 {'、'.join(item['fields'])}"
                     "——已保守計入語意摘要；若確為治理欄位請加進 GOVERNANCE_FIELDS")
    if result.get("migratable"):
        lines.append(f"  ℹ️ {len(result['migratable'])} 份抽取檔仍是舊格式（可用，內容未變）"
                     "——python3 tools/practice_note_graph.py migrate 可升版")
    if result["pending"]:
        lines.append("→ 對每一則待處理註解跑："
                     " python3 tools/practice_note_graph.py contract --note {id}")
        lines.append("  依契約做 LLM 語意抽取並寫回 "
                     f"{EXTRACT_DIR}/{{id}}.json，再跑 training_graph_build.py build。")
    elif result["active"]:
        lines.append("✅ 全部 active 註解都有有效的語意抽取檔，可執行 build。")
    else:
        lines.append("（目前沒有 active 註解，無須抽取。）")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# build_layer：把抽取結果變成訓練圖譜的節點與邊

def build_layer(root, notes, index):
    """依 active 註解 ＋ 抽取檔產生註解層的節點與邊。

    回傳 `(nodes, links, unresolved)`。**解析不到的 target 不再靜默丟棄**——
    它會出現在 unresolved 裡，由呼叫端決定拒絕建層或標記為待修的懸空參照。
    """
    new_nodes, new_links, unresolved = [], [], []

    for ref in notes:
        extraction = load_json(extraction_path(root, ref.note_id)) or {}
        source_file = Path(ref.path).relative_to(Path(root)).as_posix()
        judgment = ref.note.get("judgment") or {}
        scenario = ref.note.get("scenario") or {}
        pn_id = node_id_for(ref.note_id)
        new_nodes.append({
            "label": ref.note_id,
            "file_type": LAYER,
            "layer": LAYER,
            "source_file": source_file,
            "note_id": ref.note_id,
            "note_semantic_sha256": ref.semantic_sha,
            "ref_article": graph_labels.article_label(ref.note.get("ref_article", "")),
            "ref_rule_ids": ref.note.get("ref_rule_ids", []),
            "equipment": judgment.get("equipment"),
            "decision": judgment.get("decision"),
            "scenario_summary": scenario.get("summary"),
            "graph_summary": extraction.get("summary"),
            "source_case": ref.note.get("source_case"),
            "extracted_by": extraction.get("extracted_by"),
            "extracted_at": extraction.get("extracted_at"),
            "notice": NOTE_NOTICE,
            "norm_label": ref.note_id.lower(),
            "id": pn_id,
        })
        index.add_node(new_nodes[-1])

        # 語意抽取宣告的新概念（既有節點已有同名者一律重用，不製造孤島）
        for concept in extraction.get("concepts", []):
            label = str(concept.get("label", "")).strip()
            if not label or index.resolve(label).node_id:
                continue
            cid = f"{CONCEPT_PREFIX}{graph_labels.norm_id(label)}"
            node = {
                "label": label,
                "file_type": "concept",
                "layer": LAYER,
                "source_file": source_file,
                "concept_kind": concept.get("kind"),
                "rationale": concept.get("rationale"),
                "from_practice_note": ref.note_id,
                "notice": NOTE_NOTICE,
                "norm_label": label.lower(),
                "id": cid,
            }
            new_nodes.append(node)
            index.bind_declared(label, cid)

        seen = set()

        def add_link(target, relation, confidence, rationale, index=index, pn_id=pn_id,
                     note_id=ref.note_id, source_file=source_file, seen=seen):
            resolution = index.resolve(target)
            canonical = graph_labels.article_label(target) or resolution.matched_label or str(target)
            if (canonical, relation) in seen:
                return
            seen.add((canonical, relation))
            ok = resolution.how in graph_labels.RESOLVED_HOWS and resolution.node_id
            if not ok:
                unresolved.append({"note_id": note_id, "target": str(target),
                                   "relation": relation, "how": resolution.how,
                                   "candidates": resolution.candidates})
            new_links.append({
                "relation": relation,
                "confidence": confidence,
                "confidence_score": 1.0,
                "source_file": source_file,
                "source_location": None,
                "weight": 1.0,
                "layer": LAYER,
                "practice_note_id": note_id,
                "rationale": rationale,
                "source": pn_id,
                # target 是「解析出來的 id」，target_label 才是耐久鍵：
                # 法規圖譜重建後 id 可能變，label 不會。
                "target": resolution.node_id,
                "target_label": canonical,
                "target_graph": _target_graph(resolution.node_id),
                "dangling": not ok,
            })

        # 錨點邊：來自結構化欄位，保證註解一定掛得回條文（可追溯性底線）
        art_label = graph_labels.article_label(ref.note.get("ref_article", ""))
        if art_label:
            add_link(art_label, "supplements", "MECHANICAL",
                     f"註解的 ref_article 欄位指向 {art_label}")
        equipment = str(judgment.get("equipment") or "").strip()
        if equipment:
            add_link(equipment, "concerns_equipment", "MECHANICAL",
                     f"註解的 judgment.equipment 欄位為「{equipment}」")

        # 語意邊：只搬運抽取檔寫明的內容
        for edge in extraction.get("edges", []):
            target = str(edge.get("target", "")).strip()
            if target:
                add_link(target, edge.get("relation"), "EXTRACTED", edge.get("rationale"))

    return new_nodes, new_links, unresolved


def _target_graph(node_id):
    """節點 id 屬於哪個圖譜——訓練層節點以固定前綴命名，其餘一律視為法規圖譜。"""
    if node_id and str(node_id).startswith((NODE_PREFIX, CONCEPT_PREFIX)):
        return "training"
    return "regulation"


# ---------------------------------------------------------------------------
# migrate：v1 抽取檔升版

def _git_blobs(root, path):
    """該檔在 git 歷史中出現過的所有 blob 內容（新→舊）。"""
    rel = Path(path).relative_to(Path(root)).as_posix()
    try:
        log = subprocess.run(["git", "-C", str(root), "log", "--all", "--format=%H", "--", rel],
                             capture_output=True, text=True, timeout=30)
        if log.returncode != 0:
            return []
        for commit in log.stdout.split():
            show = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{rel}"],
                                  capture_output=True, timeout=30)
            if show.returncode == 0:
                yield show.stdout
    except (OSError, subprocess.SubprocessError):
        return []


def migrate(root=".", dry_run=True):
    """把 v1 抽取檔升為 v2。

    位元組摘要仍相符者可直接升版（語意必然未變）。位元組摘要對不上時**不猜**：
    先到 git 歷史找出當初被抽取的那個版本，比對它與現行註解的語意摘要——
    相同才代表這次變更純屬治理欄位，才自動升版並記下憑據；找不到憑據就要求重新抽取。
    """
    root = Path(root)
    results = []
    for ref in active_notes(root):
        epath = extraction_path(root, ref.note_id)
        extraction = load_json(epath)
        if extraction is None or int(extraction.get("schema_version") or 1) >= 2:
            continue
        recorded = extraction.get("note_sha256")
        evidence = None
        if recorded == ref.byte_sha:
            evidence = "bytes"
        else:
            for blob in _git_blobs(root, ref.path):
                if hashlib.sha256(blob).hexdigest() != recorded:
                    continue
                try:
                    historical = json.loads(blob.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    break
                if semantic_digest(historical) == ref.semantic_sha:
                    evidence = "git"
                break
        if evidence is None:
            results.append({"note_id": ref.note_id, "action": "needs_reextraction",
                            "detail": "無法自證語意未變——註解已變更且找不到當初抽取的版本"})
            continue
        upgraded = dict(extraction)
        upgraded["schema_version"] = EXTRACTION_SCHEMA_VERSION
        upgraded["note_semantic_sha256"] = ref.semantic_sha
        upgraded["migrated_from"] = {"schema_version": 1, "note_sha256": recorded,
                                     "evidence": evidence}
        if not dry_run:
            write_json(epath, upgraded)
        results.append({"note_id": ref.note_id, "action": "upgraded", "evidence": evidence})
    return results


# ---------------------------------------------------------------------------
# CLI

def _regulation_index(root):
    """法規圖譜的 LabelIndex（缺席時回空索引——訓練圖譜不該因為法規圖譜不在就不能做事）。"""
    try:
        from tools import training_graph_build
    except ImportError:
        import training_graph_build
    return training_graph_build.regulation_index(root)


def cmd_plan(args):
    result = plan(args.root, _regulation_index(args.root))
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json"
          else format_plan(result))
    return 2 if result["pending"] else 0


def cmd_contract(args):
    root = Path(args.root)
    notes = {ref.note_id: ref for ref in active_notes(root)}
    if args.note not in notes:
        print(f"⛔ 找不到 active 註解 {args.note}（{ACTIVE_DIR}/{args.note}.json）", file=sys.stderr)
        return 1
    ref = notes[args.note]
    contract = json.loads(json.dumps(CONTRACT_TEMPLATE)
                          .replace("{note_id}", args.note)
                          .replace("{note_semantic_sha256}", ref.semantic_sha))
    if args.format == "json":
        print(json.dumps({"note": ref.note, "contract": contract, "relations": RELATIONS},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"== {args.note} 語意抽取契約 ==\n")
    print("【註解原文（語意抽取的唯一輸入）】")
    print(json.dumps(ref.note, ensure_ascii=False, indent=2))
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
    notes = {ref.note_id: ref for ref in active_notes(root)}
    if note_id not in notes:
        print(f"⛔ {note_id} 不是 active 註解，無從驗證（抽取檔只對 {ACTIVE_DIR}/ 有效）",
              file=sys.stderr)
        return 2
    problems = validate_extraction(extraction, notes[note_id], _regulation_index(root))
    if args.format == "json":
        print(json.dumps({"note_id": note_id, "problems": problems}, ensure_ascii=False, indent=2))
    elif problems:
        print(f"🔴 {note_id} 抽取檔未通過（{len(problems)} 項）：")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print(f"🟢 {note_id} 抽取檔通過，可執行 build。")
    return 2 if problems else 0


def cmd_migrate(args):
    results = migrate(args.root, dry_run=not args.apply)
    if args.format == "json":
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif not results:
        print("✅ 沒有需要升版的抽取檔。")
    else:
        prefix = "（乾跑，未寫檔）" if not args.apply else ""
        print(f"== v1 抽取檔升版{prefix} ==")
        for item in results:
            if item["action"] == "upgraded":
                print(f"  🟢 {item['note_id']}：可升版（憑據：{item['evidence']}）")
            else:
                print(f"  🔴 {item['note_id']}：{item['detail']}")
        if not args.apply:
            print("→ 確認無誤後加 --apply 實際寫檔。")
    return 2 if any(r["action"] != "upgraded" for r in results) else 0


def build_parser():
    p = argparse.ArgumentParser(description="實務註解 → 訓練圖譜註解層（LLM 語意抽取 ＋ 確定性建層）")
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

    s = sub.add_parser("migrate", help="v1 抽取檔升為 v2（預設乾跑；語意無法自證時拒絕）")
    s.add_argument("--apply", action="store_true", help="實際寫檔")
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.set_defaults(func=cmd_migrate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

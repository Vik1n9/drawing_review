#!/usr/bin/env python3
"""實務註解引擎：把案件中「法典涵蓋不到」的實務見解，結構化為 Practice Note。

只用 Python 標準庫。

    python3 tools/practice_note_engine.py draft --gap {gap_candidates.json} --case {案件名}
    python3 tools/practice_note_engine.py conflict-check --draft practice_notes/staging/PN-….json
    python3 tools/practice_note_engine.py apply --draft practice_notes/staging/PN-….json \\
        --approved-by "○○○" --confirm 確認納入
    python3 tools/practice_note_engine.py reindex
    python3 tools/practice_note_engine.py test --strict

法典／註解雙軌制（見 skills/practice-note.md）：

- `rules/` 是**法典層**，只能經先紅再綠變更；本引擎絕不寫入。
- `practice_notes/` 是**註解層**，記錄法典未涵蓋情境下的實務見解。
- 本專案使用者本身即為消防專業人員，「確認納入」就是專業判斷的表示，**不另設核定關卡**；
  但註解終究是實務見解而非法規條文，援引時必須同時列出所補充的法條供覆核。
- 註解**只補充、不推翻法典**。免除法定應設設備的註解一律紅色警示，須人工具名確認法源。
- staging → active 必須由使用者明確輸入「確認納入」，工具在程式層強制此關卡。
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

NOTES_DIR = "practice_notes"
ACTIVE_DIR = "practice_notes/active"
STAGING_DIR = "practice_notes/staging"
INDEX_PATH = "practice_notes/index.json"
GOVERNANCE_DIR = "governance/註解紀錄"
RULES_PATH = "rules/equipment_rules.json"
REG_INDEX_PATH = "rules/regulation_index.json"

CONFIRM_PHRASE = "確認納入"
PLACEHOLDER = "（待填）"
# 本專案使用者本身即為消防專業人員，「確認納入」就是專業判斷的表示，不另設核定關卡。
# 但註解終究是實務見解而非法規條文——援引時仍須列出所補充的法條供覆核。
NOTE_NOTICE = "本實務註解為消防專業人員確認之實務見解，非法規條文；援引時須同時列出所補充的法條"

DECISIONS = ("exempt", "exempt_with_alternatives", "strengthen", "replace")
STATUSES = ("active", "superseded", "deprecated")
EXEMPTING_DECISIONS = ("exempt", "exempt_with_alternatives", "replace")

REQUIRED_FIELDS = [
    ("id", str),
    ("ref_article", str),
    ("ref_rule_ids", list),
    ("scenario", dict),
    ("judgment", dict),
    ("source_case", str),
    ("status", str),
    ("created", str),
]

TAIPEI = timezone(timedelta(hours=8))


def now_iso():
    return datetime.now(TAIPEI).replace(microsecond=0).isoformat()


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


def iter_notes(root=".", subdir=ACTIVE_DIR):
    directory = Path(root) / subdir
    if not directory.is_dir():
        return []
    notes = []
    for path in sorted(directory.glob("*.json")):
        doc = load_json(path)
        if isinstance(doc, dict):
            notes.append((path, doc))
    return notes


# ---------------------------------------------------------------------------
# Schema 驗證（純結構檢查，不做法規判斷）

def validate_schema(note):
    problems = []
    for field, kind in REQUIRED_FIELDS:
        if field not in note:
            problems.append(f"缺少必填欄位 {field}")
        elif not isinstance(note[field], kind):
            problems.append(f"{field} 型別應為 {kind.__name__}")

    if isinstance(note.get("id"), str) and not re.fullmatch(r"PN-\d{8}-\d{3}", note["id"]):
        problems.append(f"id 格式應為 PN-YYYYMMDD-NNN，實得 {note['id']}")
    if isinstance(note.get("ref_rule_ids"), list) and not note["ref_rule_ids"]:
        problems.append("ref_rule_ids 不得為空——註解必須掛在既有規則上，否則無從追溯")
    if note.get("status") not in STATUSES:
        problems.append(f"status 應為 {'/'.join(STATUSES)}，實得 {note.get('status')}")

    scenario = note.get("scenario") or {}
    if not str(scenario.get("summary", "")).strip():
        problems.append("scenario.summary 必填")
    if not isinstance(scenario.get("conditions"), dict) or not scenario.get("conditions"):
        problems.append("scenario.conditions 必填且須為非空物件（結構化觸發條件）")

    judgment = note.get("judgment") or {}
    if not str(judgment.get("equipment", "")).strip():
        problems.append("judgment.equipment 必填")
    if judgment.get("decision") not in DECISIONS:
        problems.append(f"judgment.decision 應為 {'/'.join(DECISIONS)}，實得 {judgment.get('decision')}")
    if not str(judgment.get("detail", "")).strip():
        problems.append("judgment.detail 必填")
    effect = judgment.get("effect")
    if effect is not None:
        if not isinstance(effect, dict):
            problems.append("judgment.effect 須為物件")
        else:
            for key in ("remove", "add"):
                if key in effect and not isinstance(effect[key], list):
                    problems.append(f"judgment.effect.{key} 須為陣列")

    for path_str in placeholders(note):
        problems.append(f"{path_str} 仍是 {PLACEHOLDER}——草案必須由人工填實，"
                        "嚴禁以推測填充（AGENTS.md 底線 3）")
    return problems


def placeholders(node, prefix=""):
    """回傳所有仍是「（待填）」的欄位路徑。"""
    found = []
    if isinstance(node, dict):
        for k, v in node.items():
            found.extend(placeholders(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            found.extend(placeholders(v, f"{prefix}.{i}"))
    elif isinstance(node, str) and PLACEHOLDER in node:
        found.append(prefix or "(root)")
    return found


# ---------------------------------------------------------------------------
# conflict-check

def known_rule_ids(root="."):
    doc = load_json(Path(root) / RULES_PATH, {"rules": []})
    return {r["id"]: r for r in doc.get("rules", [])}


def known_articles(root="."):
    doc = load_json(Path(root) / REG_INDEX_PATH)
    return set(doc.get("by_article", {})) if doc else set()


def normalize_article(ref):
    return str(ref).lstrip("§第").rstrip("條").strip()


def conflict_check(note, root="."):
    """機械式牴觸檢查。回傳 {blocking: [...], warnings: [...]}。

    工具只做「可機械驗證」的檢查（欄位、引用是否存在、是否重複、是否免除法定應設），
    不代為判斷該註解在法規上是否成立——那是消防專業人員的職責。
    """
    blocking = validate_schema(note)
    warnings = []

    rules = known_rule_ids(root)
    for rid in note.get("ref_rule_ids", []) or []:
        if rid not in rules:
            blocking.append(f"ref_rule_ids 的 {rid} 不存在於 {RULES_PATH}——註解無法掛回法典")

    articles = known_articles(root)
    art = normalize_article(note.get("ref_article", ""))
    if articles and art not in articles:
        blocking.append(f"ref_article §{art} 不存在於 {REG_INDEX_PATH}"
                        "（法規換版後請先跑 regulation_index.py build）")

    judgment = note.get("judgment") or {}
    effect = judgment.get("effect") or {}
    removed = effect.get("remove") or []
    if judgment.get("decision") in EXEMPTING_DECISIONS or removed:
        bases = sorted({rules[r].get("legal_basis") for r in note.get("ref_rule_ids", [])
                        if r in rules})
        warnings.append(
            f"🔴 本註解免除／替換法定設備（decision: {judgment.get('decision')}"
            f"{'，remove: ' + '、'.join(map(str, removed)) if removed else ''}）。"
            f"法典依據 {'、'.join(str(b) for b in bases) or '（無）'} 仍要求該設備——"
            "註解只能補充法典未涵蓋的情境，不得推翻條文。"
            "請人工確認免除的法源（但書、解釋令、替代方案條款）並記入 judgment.detail")

    conditions = (note.get("scenario") or {}).get("conditions") or {}
    for path, other in iter_notes(root, ACTIVE_DIR):
        if other.get("id") == note.get("id"):
            continue
        if other.get("status") != "active":
            continue
        if normalize_article(other.get("ref_article", "")) != art:
            continue
        other_conditions = (other.get("scenario") or {}).get("conditions") or {}
        if other_conditions == conditions:
            blocking.append(f"與既有 active 註解 {other['id']} 的條號與觸發條件完全相同——"
                            "請改為修訂該註解（舊註解標 superseded）而非新增重複註解")
        elif set(other_conditions) == set(conditions):
            warnings.append(f"⚠️ 註解 {other['id']} 有相同的條號與觸發條件欄位組合，"
                            "條件值不同；請確認兩者不會同時命中同一案件")

    return {"blocking": blocking, "warnings": warnings}


# ---------------------------------------------------------------------------
# draft

def next_note_id(root=".", day=None):
    day = day or datetime.now(TAIPEI).strftime("%Y%m%d")
    used = set()
    for subdir in (ACTIVE_DIR, STAGING_DIR):
        for path, doc in iter_notes(root, subdir):
            match = re.fullmatch(rf"PN-{day}-(\d{{3}})", str(doc.get("id", path.stem)))
            if match:
                used.add(int(match.group(1)))
    return f"PN-{day}-{max(used, default=0) + 1:03d}"


def draft_from_candidate(candidate, source_case, note_id, created=None):
    """由 gap candidate 產出草案骨架。判讀內容一律留 PLACEHOLDER 交人工填實。"""
    return {
        "id": note_id,
        "ref_article": normalize_article(candidate.get("article", "")),
        "ref_rule_ids": [candidate["rule_id"]] if candidate.get("rule_id") else [],
        "scenario": {
            "summary": candidate.get("case_context") or PLACEHOLDER,
            "conditions": {"_待結構化": PLACEHOLDER},
        },
        "judgment": {
            "equipment": candidate.get("equipment", PLACEHOLDER),
            "decision": PLACEHOLDER,
            "detail": PLACEHOLDER,
            "effect": {"remove": [], "add": []},
        },
        "source_case": source_case,
        "status": "active",
        "created": created or now_iso(),
        "approved": None,
        "governance_log": None,
        "notice": NOTE_NOTICE,
    }


def cmd_draft(args):
    root = Path(args.root)
    gap = load_json(args.gap)
    if not gap:
        print(f"⛔ 讀不到 gap 檔：{args.gap}", file=sys.stderr)
        return 1
    candidates = gap.get("candidates", [])
    if args.rule_id:
        candidates = [c for c in candidates if c.get("rule_id") == args.rule_id]
    if not candidates:
        print("沒有可草擬的 gap candidate（可用 --rule-id 指定其中一項）。")
        return 0

    day = (args.date or datetime.now(TAIPEI).strftime("%Y-%m-%d")).replace("-", "")
    written = []
    for candidate in candidates:
        note_id = next_note_id(root, day)
        note = draft_from_candidate(candidate, args.case or gap.get("case_name", PLACEHOLDER),
                                    note_id, created=args.created)
        path = root / STAGING_DIR / f"{note_id}.json"
        write_json(path, note)
        written.append(path)

    print(f"✅ 已產出 {len(written)} 份草案到 {STAGING_DIR}/：")
    for path in written:
        print(f"  - {path.relative_to(root).as_posix()}")
    print(f"\n⚠️ 草案的判讀欄位一律是「{PLACEHOLDER}」，必須由使用者填實後才能通過 conflict-check。")
    print("   嚴禁由 Agent 以推測填充（AGENTS.md 底線 3）。")
    print("\n接續：")
    print("  1. 與使用者逐欄確認並填實 scenario.conditions / judgment.decision / judgment.detail")
    print(f"  2. python3 tools/practice_note_engine.py conflict-check --draft {STAGING_DIR}/{{id}}.json")
    print(f"  3. 使用者輸入「{CONFIRM_PHRASE}」後才可 apply")
    return 0


def cmd_conflict_check(args):
    note = load_json(args.draft)
    if not note:
        print(f"⛔ 讀不到草案：{args.draft}", file=sys.stderr)
        return 1
    result = conflict_check(note, args.root)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"== 法典牴觸檢查：{note.get('id')} （§{normalize_article(note.get('ref_article',''))}）==")
        for msg in result["blocking"]:
            print(f"⛔ {msg}")
        for msg in result["warnings"]:
            print(f"{msg}")
        if not result["blocking"] and not result["warnings"]:
            print("✅ 無阻擋問題、無牴觸警示。")
        elif not result["blocking"]:
            print(f"\n可繼續，但上列警示須人工確認；apply 時以 --acknowledge-conflict 記錄確認理由。")
        else:
            print(f"\n⛔ 有阻擋問題，不得 apply。")
    return 2 if result["blocking"] else (1 if result["warnings"] and args.strict else 0)


# ---------------------------------------------------------------------------
# apply

GOVERNANCE_TEMPLATE = """# {id} 追溯紀錄

- **註解 ID**：{id}
- **引用法條**：§{article}
- **對應規則**：{rule_ids}
- **來源案件**：{source_case}
- **建立時間**：{created}
- **批准時間**：{approved}
- **批准人**：{approved_by}
- **狀態**：{status}

## 判讀摘要

{summary} → {detail}

## 檢查結果

- [{conflict_mark}] conflict-check：{conflict_text}
- [{ack_mark}] 牴觸警示人工確認：{ack_text}

## 效力

本註解為**實務補充見解**，非法規條文。{notice}。
援引本註解的審查結論，必須同時列出所補充的法條（§{article}）與本註解 ID，供覆核。
"""


def cmd_apply(args):
    root = Path(args.root)
    note = load_json(args.draft)
    if not note:
        print(f"⛔ 讀不到草案：{args.draft}", file=sys.stderr)
        return 1

    if args.confirm != CONFIRM_PHRASE:
        print(f"⛔ 未取得使用者確認：--confirm 必須是「{CONFIRM_PHRASE}」四字。"
              "未經使用者明確確認的註解，禁止從 staging 移至 active。", file=sys.stderr)
        return 2

    result = conflict_check(note, root)
    if result["blocking"]:
        print("⛔ 牴觸檢查有阻擋問題，不得套用：", file=sys.stderr)
        for msg in result["blocking"]:
            print(f"  - {msg}", file=sys.stderr)
        return 2
    if result["warnings"] and not args.acknowledge_conflict:
        print("⛔ 有牴觸警示未經確認，不得套用：", file=sys.stderr)
        for msg in result["warnings"]:
            print(f"  - {msg}", file=sys.stderr)
        print("\n人工確認後，以 --acknowledge-conflict \"{確認理由與法源}\" 記錄後重跑。", file=sys.stderr)
        return 2

    approved = args.approved or now_iso()
    note["status"] = note.get("status") or "active"
    note["approved"] = approved
    note["approved_by"] = args.approved_by
    note["governance_log"] = f"{GOVERNANCE_DIR}/{note['id']}.md"
    note["notice"] = NOTE_NOTICE
    if args.acknowledge_conflict:
        note["conflict_acknowledgement"] = args.acknowledge_conflict

    active_path = root / ACTIVE_DIR / f"{note['id']}.json"
    write_json(active_path, note)

    judgment = note.get("judgment", {})
    log = GOVERNANCE_TEMPLATE.format(
        id=note["id"],
        article=normalize_article(note.get("ref_article", "")),
        rule_ids="、".join(note.get("ref_rule_ids", [])) or "（無）",
        source_case=note.get("source_case", "（未記錄）"),
        created=note.get("created", "（未記錄）"),
        approved=approved,
        approved_by=args.approved_by,
        status=note["status"],
        summary=(note.get("scenario") or {}).get("summary", ""),
        detail=judgment.get("detail", ""),
        conflict_mark="x",
        conflict_text="無阻擋問題" + ("（有警示，見下）" if result["warnings"] else "、無警示"),
        ack_mark="x" if args.acknowledge_conflict else " ",
        ack_text=args.acknowledge_conflict or "無警示需確認",
        notice=NOTE_NOTICE,
    )
    log_path = root / GOVERNANCE_DIR / f"{note['id']}.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(log, encoding="utf-8")

    staging_path = Path(args.draft)
    if staging_path.is_file() and staging_path.resolve() != active_path.resolve():
        staging_path.unlink()

    index = reindex(root)
    print(f"✅ 已套用 {note['id']} → {active_path.relative_to(root).as_posix()}")
    print(f"   追溯紀錄：{log_path.relative_to(root).as_posix()}")
    print(f"   索引已更新：{index['count']} 則 active 註解")
    print(f"\n⚠️ {NOTE_NOTICE}——援引本註解的結論必附此警語。")
    print("\n迴歸驗收：python3 tools/practice_note_engine.py test --strict")
    return 0


# ---------------------------------------------------------------------------
# reindex / test

def reindex(root="."):
    root = Path(root)
    by_article, by_equipment, by_rule = {}, {}, {}
    entries = []
    for path, note in iter_notes(root, ACTIVE_DIR):
        if note.get("status") != "active":
            continue
        art = normalize_article(note.get("ref_article", ""))
        equipment = (note.get("judgment") or {}).get("equipment", "")
        entry = {
            "id": note.get("id", path.stem),
            "path": path.relative_to(root).as_posix(),
            "ref_article": art,
            "ref_rule_ids": note.get("ref_rule_ids", []),
            "equipment": equipment,
            "decision": (note.get("judgment") or {}).get("decision"),
            "summary": (note.get("scenario") or {}).get("summary"),
            "source_case": note.get("source_case"),
            "approved": note.get("approved"),
        }
        entries.append(entry)
        by_article.setdefault(art, []).append(entry["id"])
        if equipment:
            by_equipment.setdefault(equipment, []).append(entry["id"])
        for rid in note.get("ref_rule_ids", []):
            by_rule.setdefault(rid, []).append(entry["id"])

    entries.sort(key=lambda e: e["id"])
    index = {
        "schema_version": 1,
        "note": "實務註解索引，由 practice_note_engine.py reindex 產生。"
                "註解為實務補充見解，非法規條文；援引必附未核定警語。",
        "notice": NOTE_NOTICE,
        "count": len(entries),
        "notes": entries,
        "by_article": {k: sorted(v) for k, v in sorted(by_article.items())},
        "by_equipment": {k: sorted(v) for k, v in sorted(by_equipment.items())},
        "by_rule_id": {k: sorted(v) for k, v in sorted(by_rule.items())},
    }
    write_json(root / INDEX_PATH, index)
    return index


def cmd_reindex(args):
    index = reindex(args.root)
    print(f"✅ 已重建 {INDEX_PATH}：{index['count']} 則 active 註解"
          f"（涵蓋 {len(index['by_article'])} 個條號、{len(index['by_equipment'])} 種設備）")
    return 0


def run_tests(root="."):
    """迴歸檢查：註解庫自身的一致性，以及與法典的引用完整性。"""
    root = Path(root)
    failures = []
    seen = {}
    for path, note in iter_notes(root, ACTIVE_DIR):
        label = path.relative_to(root).as_posix()
        for problem in validate_schema(note):
            failures.append(f"[{label}] {problem}")
        nid = note.get("id")
        if nid in seen:
            failures.append(f"[{label}] 註解 id {nid} 與 {seen[nid]} 重複")
        seen[nid] = label
        if nid and path.stem != nid:
            failures.append(f"[{label}] 檔名與 id 不一致（id={nid}）")
        result = conflict_check(note, root)
        for problem in result["blocking"]:
            failures.append(f"[{label}] {problem}")

    index = load_json(root / INDEX_PATH)
    active_ids = sorted(n.get("id") for _, n in iter_notes(root, ACTIVE_DIR)
                        if n.get("status") == "active")
    if index is None:
        if active_ids:
            failures.append(f"{INDEX_PATH} 不存在，但有 {len(active_ids)} 則 active 註解——請跑 reindex")
    elif sorted(e["id"] for e in index.get("notes", [])) != active_ids:
        failures.append(f"{INDEX_PATH} 與 {ACTIVE_DIR}/ 不同步——請跑 reindex")

    staging = iter_notes(root, STAGING_DIR)
    return failures, len(active_ids), len(staging)


def cmd_test(args):
    failures, active, staging = run_tests(args.root)
    if failures:
        print(f"🔴 註解庫檢查未通過（{len(failures)} 項）：")
        for f in failures:
            print(f"  - {f}")
        return 1 if args.strict else 0
    print(f"🟢 註解庫檢查通過：{active} 則 active、{staging} 則 staging 待確認。")
    if staging:
        print(f"⚠️ staging 有 {staging} 則草案未經使用者「{CONFIRM_PHRASE}」，尚未生效。")
    print(f"提醒：{NOTE_NOTICE}。")
    return 0


# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="實務註解引擎（法典／註解雙軌制的註解層）")
    p.add_argument("--root", default=".", help="專案根目錄（預設為當前目錄）")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("draft", help="由 gap_candidates.json 產出註解草案到 staging/")
    s.add_argument("--gap", required=True, help="fire_code_calc.py check-gap 的輸出")
    s.add_argument("--case", default=None, help="來源案件名稱")
    s.add_argument("--rule-id", default=None, help="只草擬指定 rule_id 的 candidate")
    s.add_argument("--date", default=None, help="草案日期（預設今天，影響 id）")
    s.add_argument("--created", default=None, help="建立時間 ISO 8601（預設現在）")
    s.set_defaults(func=cmd_draft)

    s = sub.add_parser("conflict-check", help="法典牴觸與重複檢查（0=通過 2=有阻擋問題）")
    s.add_argument("--draft", required=True)
    s.add_argument("--format", choices=("text", "json"), default="text")
    s.add_argument("--strict", action="store_true", help="有警示也以非零離開")
    s.set_defaults(func=cmd_conflict_check)

    s = sub.add_parser("apply", help=f"staging → active（需使用者「{CONFIRM_PHRASE}」）")
    s.add_argument("--draft", required=True)
    s.add_argument("--approved-by", required=True, help="批准人（責任追溯，必填）")
    s.add_argument("--confirm", required=True, help=f"必須是使用者輸入的「{CONFIRM_PHRASE}」")
    s.add_argument("--acknowledge-conflict", default=None, help="人工確認牴觸警示的理由與法源")
    s.add_argument("--approved", default=None, help="批准時間 ISO 8601（預設現在）")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("reindex", help="重建 practice_notes/index.json")
    s.set_defaults(func=cmd_reindex)

    s = sub.add_parser("test", help="註解庫一致性與引用完整性檢查")
    s.add_argument("--strict", action="store_true", help="有問題時以非零離開（供 CI）")
    s.set_defaults(func=cmd_test)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

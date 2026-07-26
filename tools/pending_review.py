#!/usr/bin/env python3
"""待確認事項的裁示與自動修正 for drawing_review.

規則參數與現行條文比對出的差異寫在 `governance/待確認清單/rule-discrepancies-*.json`。
本工具把「列給使用者確認 → 裁示 → 自動修正 → 回填 verified → 更新文件 → 移除疑義檔」
串成一條可全自動執行的迴路，且修正一律走先紅再綠（`skills/red-green.md`）：

    先把法條原文抄錄進 rule_tests.json 的 expected（測試轉紅）
    → 確認紅得正確 → 才改規則參數（測試轉綠）

任何一步不如預期（該紅的沒紅、改完沒轉綠）就整筆回滾，不留半套狀態。

Zero external dependencies — Python stdlib only。

Usage:
    python3 tools/pending_review.py status            # 開場檢查（有待確認事項 → 結束碼 2）
    python3 tools/pending_review.py list              # 逐則列給使用者確認
    python3 tools/pending_review.py show --id D-015-01
    python3 tools/pending_review.py decide --id D-015-01 --decision 採納更正 --by "○○○"
    python3 tools/pending_review.py decide --results decisions.json      # 一次裁示多則
    python3 tools/pending_review.py apply --all       # 執行已裁示者：先紅再綠 → 回填 verified
    python3 tools/pending_review.py render            # 重產 待確認事項.md 並同步 README

裁示值：
    採納更正 — 依 suggested_fix／auto_fix 更正參數（走先紅再綠）
    維持現值 — 現值正確或屬有意簡化，不改參數，該規則可回填 verified
    另有更正 — 使用者提供不同的正確值；需附 note，由人接手改 auto_fix 後再 apply
"""

import argparse
import copy
import json
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import fire_code_calc as calc  # noqa: E402
from tools import verification_sheet as vs  # noqa: E402

TESTS_PATH = "rules/rule_tests.json"
DOC_PATH = "待確認事項.md"
README_PATH = "README.md"
ARCHIVE_DIR = os.path.join(vs.DISCREPANCY_DIR, "已裁示")
RECORD_DIR = os.path.join("governance", "核定紀錄")

BEGIN_MARK = "<!-- PENDING-REVIEW:BEGIN -->"
END_MARK = "<!-- PENDING-REVIEW:END -->"

DECISIONS = ("採納更正", "維持現值", "另有更正")

EXIT_OK, EXIT_PENDING = 0, 2


# ---------------------------------------------------------------------------
# 讀寫
# ---------------------------------------------------------------------------

def load_sheet(path=None):
    resolved = vs.latest_discrepancy_path(path)
    if not resolved or not os.path.exists(resolved):
        return None, None
    with open(resolved, encoding="utf-8") as f:
        return resolved, json.load(f)


def save_sheet(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def open_findings(doc):
    return [f for f in doc.get("findings", []) if f.get("status") != "resolved"]


def decided_findings(doc):
    return [f for f in open_findings(doc) if f.get("decision")]


# ---------------------------------------------------------------------------
# status / list / show
# ---------------------------------------------------------------------------

def cmd_status(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        print("✅ 沒有待確認事項（governance/待確認清單/ 無疑義檔）。")
        return EXIT_OK
    pending = open_findings(doc)
    if not pending:
        print(f"✅ 疑義檔 {path} 內所有事項都已裁示——跑 "
              "`python3 tools/pending_review.py render` 收尾即可移除疑義檔。")
        return EXIT_PENDING
    undecided = [f for f in pending if not f.get("decision")]
    print(f"⚪ 有 {len(pending)} 則待確認事項（{path}）")
    print(f"   其中 {len(undecided)} 則尚未裁示、{len(pending) - len(undecided)} 則已裁示待執行")
    print(f"   影響規則：{'、'.join(sorted({f.get('rule_id', '?') for f in pending}))}")
    print("   → 列給使用者逐則確認：python3 tools/pending_review.py list")
    print("   → 裁示後執行修正：python3 tools/pending_review.py apply --all --by \"{確認人}\"")
    return EXIT_PENDING


def format_finding(f, index=None, verbose=True):
    head = f"[{f.get('id')}] {f.get('equipment')}｜{f.get('article')}｜`{f.get('rule_id')}`（{f.get('type')}）"
    lines = [f"{index}. {head}" if index else head]
    lines.append(f"   檔案：{f.get('target_file')}")
    lines.append(f"   條文原文：{f.get('article_quote', '')}")
    lines.append(f"   規則現值：{f.get('current_value', '')}")
    lines.append(f"   差異：{f.get('difference', '')}")
    lines.append(f"   影響：{f.get('impact', '')}")
    lines.append(f"   建議更正：{f.get('suggested_fix', '')}")
    if verbose and f.get("note"):
        lines.append(f"   備註：{f['note']}")
    lines.append(f"   可自動修正：{'是（先紅再綠）' if f.get('auto_fix') else '否——需人工步驟'}")
    for step in f.get("manual_steps") or []:
        lines.append(f"     · {step}")
    if f.get("decision"):
        lines.append(f"   已裁示：{f['decision']}"
                     + (f"（{f.get('decision_note')}）" if f.get("decision_note") else ""))
    return "\n".join(lines)


def cmd_list(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        print("✅ 沒有待確認事項。")
        return EXIT_OK
    findings = doc.get("findings", []) if args.all else open_findings(doc)
    if not findings:
        print("✅ 所有事項都已裁示。")
        return EXIT_OK
    print(f"# 待確認事項（{doc.get('sheet_id')}｜{path}）")
    print(f"法規版本：{doc.get('regulation_version', '未注明')}｜共 {len(findings)} 則\n")
    for i, f in enumerate(findings, 1):
        print(format_finding(f, i))
        print()
    print("請逐則回覆「採納更正」／「維持現值」／「另有更正＋正確值」。")
    print("回覆後執行：python3 tools/pending_review.py decide --id {ID} --decision {裁示} --by \"{確認人}\"")
    return EXIT_PENDING


def cmd_show(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        sys.exit("沒有待確認事項。")
    found = next((f for f in doc.get("findings", []) if f.get("id") == args.id), None)
    if found is None:
        sys.exit(f"找不到事項：{args.id}")
    print(format_finding(found))
    if found.get("auto_fix"):
        print("\n自動修正內容（先紅再綠）：")
        print(json.dumps(found["auto_fix"], ensure_ascii=False, indent=2))
    return EXIT_OK


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------

def record_decision(finding, decision, note, by, when):
    if decision not in DECISIONS:
        sys.exit(f"未知裁示值：{decision}（僅接受 {'／'.join(DECISIONS)}）")
    if decision == "另有更正" and not note:
        sys.exit("裁示為「另有更正」時必須附 --note 說明正確值與依據。")
    finding["decision"] = decision
    finding["decision_note"] = note
    finding["decided_by"] = by
    finding["decided_date"] = when


def cmd_decide(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        sys.exit("沒有待確認事項。")
    by = args.by or "使用者本人（消防專業人員）"
    when = args.date or date.today().isoformat()
    by_id = {f.get("id"): f for f in doc.get("findings", [])}

    items = []
    if args.results:
        spec = load_json(args.results)
        by = spec.get("decided_by") or by
        when = spec.get("decided_date") or when
        items = [(d["id"], d["decision"], d.get("note")) for d in spec["decisions"]]
    elif args.id and args.decision:
        items = [(args.id, args.decision, args.note)]
    else:
        sys.exit("請提供 --id 與 --decision，或以 --results 指定裁示 JSON。")

    for fid, decision, note in items:
        finding = by_id.get(fid)
        if finding is None:
            sys.exit(f"找不到事項：{fid}")
        record_decision(finding, decision, note, by, when)
        print(f"✅ 已記錄裁示：{fid} → {decision}")
    save_sheet(path, doc)
    print(f"\n裁示人：{by}｜日期：{when}")
    print("下一步：python3 tools/pending_review.py apply --all")
    return EXIT_OK


# ---------------------------------------------------------------------------
# apply — 先紅再綠自動修正
# ---------------------------------------------------------------------------

def dig_set(container, path, value, remove=False):
    """以 'params.low_rise.per_floor_area_threshold.甲1' 這種點分路徑寫入或刪除。"""
    keys = path.split(".")
    node = container
    for key in keys[:-1]:
        if isinstance(node, list):
            node = node[int(key)]
        else:
            node = node.setdefault(key, {})
    last = keys[-1]
    if isinstance(node, list):
        index = int(last)
        if remove:
            node.pop(index)
        else:
            node[index] = value
    elif remove:
        node.pop(last, None)
    else:
        node[last] = value


def upsert_test(tests_doc, test):
    for i, existing in enumerate(tests_doc["tests"]):
        if existing.get("id") == test.get("id"):
            tests_doc["tests"][i] = test
            return
    tests_doc["tests"].append(test)


def rules_doc_cache(cache, path):
    if path not in cache:
        cache[path] = load_json(path)
    return cache[path]


def run_red_green(finding, tests_doc, docs):
    """回傳 (ok, 訊息)。docs 是 {規則檔路徑: doc} 的暫存，全部就地修改。

    先紅再綠的三個關卡：
      1. 測試抄錄法條原文後必須是「紅」——紅得不對（已經綠／INVALID）就不是有鑑別力的測試
      2. 套用參數修正
      3. 全部測試必須轉綠
    """
    auto = finding.get("auto_fix") or {}
    patched_ids = []
    for patch in auto.get("tests", []):
        upsert_test(tests_doc, patch)
        patched_ids.append(patch["id"])

    # 關卡 1：Verify RED
    for test_id in patched_ids:
        test = next(t for t in tests_doc["tests"] if t["id"] == test_id)
        doc = docs.get(test.get("rules_file") or vs.RULES_PATH)
        status, detail = calc._eval_test(doc, test)
        if status == "pass":
            return False, (f"{test_id} 沒有轉紅（{detail}）——測試無鑑別力："
                           "規則參數已經是這個值，或測試測到別的東西")
        if status == "invalid":
            return False, f"{test_id} 是 INVALID 而非紅（{detail}）——先修測試本身"

    # 關卡 2：套用參數修正（rule_id 省略時代表改規則檔本身的結構）
    for patch in auto.get("params", []):
        doc = docs[patch["file"]]
        if patch.get("rule_id"):
            target = vs.verifiable_entries(doc).get(patch["rule_id"])
            if target is None:
                return False, f"規則不存在：{patch['rule_id']}（{patch['file']}）"
        else:
            target = doc
        dig_set(target, patch["path"], patch.get("value"), remove=patch.get("op") == "remove")

    # 關卡 3：全部轉綠
    for test in tests_doc["tests"]:
        doc = docs.get(test.get("rules_file") or vs.RULES_PATH)
        status, detail = calc._eval_test(doc, test)
        if status != "pass":
            return False, f"套用參數後 {test['id']} 仍未轉綠（{status}：{detail}）"
    return True, f"先紅再綠完成（測試 {'、'.join(patched_ids) or '無新增'}）"


def cmd_apply(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        print("✅ 沒有待確認事項。")
        return EXIT_OK

    targets = [f for f in decided_findings(doc) if args.all or f.get("id") in (args.id or [])]
    if not targets:
        print("沒有「已裁示但尚未執行」的事項。先跑 "
              "`python3 tools/pending_review.py decide` 記錄裁示。")
        return EXIT_PENDING

    when = args.date or date.today().isoformat()
    tests_doc = load_json(TESTS_PATH)
    docs = {}
    for f in targets:
        rules_doc_cache(docs, f.get("target_file", vs.RULES_PATH))
    rules_doc_cache(docs, vs.RULES_PATH)
    backup = (copy.deepcopy(tests_doc), copy.deepcopy(docs))

    applied, skipped = [], []
    for f in targets:
        decision = f["decision"]
        if decision == "維持現值":
            f["status"] = "resolved"
            applied.append((f["id"], "維持現值，未改參數"))
            continue
        if decision == "另有更正":
            skipped.append((f["id"], "裁示為「另有更正」：請先把使用者提供的正確值寫進 auto_fix，再重跑 apply"))
            continue
        if not f.get("auto_fix"):
            skipped.append((f["id"], "本則無 auto_fix（需引擎或結構調整）：依 manual_steps 人工完成後，"
                                     "再以 decide 標記並手動將 status 改為 resolved"))
            continue
        ok, message = run_red_green(f, tests_doc, docs)
        if not ok:
            tests_doc, docs = backup  # 任一則失敗即整批回滾，不留半套狀態
            sys.exit(f"🔴 {f['id']} 自動修正失敗，已全部回滾：{message}")
        f["status"] = "resolved"
        applied.append((f["id"], message))

    if applied:
        save_json(TESTS_PATH, tests_doc)
        for rules_path, rules in docs.items():
            save_json(rules_path, rules)

    print(f"✅ 已執行 {len(applied)} 則：")
    for fid, message in applied:
        print(f"   - {fid}：{message}")
    if skipped:
        print(f"\n⚪ {len(skipped)} 則未執行：")
        for fid, message in skipped:
            print(f"   - {fid}：{message}")

    verified = writeback_verified(doc, args.by, when, args.sheet) if applied else []
    if verified:
        print(f"\n✅ 差異全部裁示完畢，已回填 verified: true：{'、'.join(verified)}")
    save_sheet(path, doc)
    render_all(path, doc)
    print("\n收尾：python3 tools/fire_code_calc.py self-test && "
          "python3 tools/fire_code_calc.py run-tests --strict")
    return EXIT_OK


def writeback_verified(doc, by, when, sheet_path):
    """差異已全部裁示完畢的規則 → 產生核定紀錄並回填 verified: true。"""
    still_open = {f.get("rule_id") for f in open_findings(doc)}
    ready = {}
    for f in doc.get("findings", []):
        rid = f.get("rule_id")
        if f.get("status") != "resolved" or rid in still_open:
            continue
        ready.setdefault(f.get("target_file", vs.RULES_PATH), {}).setdefault(rid, []).append(f)

    verified_by = by or "使用者本人（消防專業人員）"
    done = []
    for rules_path, rules in ready.items():
        results = []
        for rid, findings in rules.items():
            entry = vs.verifiable_entries(load_json(rules_path)).get(rid)
            if entry is None or entry.get("verified"):
                continue
            notes = "；".join(f"{f['id']} 裁示{f['decision']}"
                             + (f"（{f['decision_note']}）" if f.get("decision_note") else "")
                             for f in findings)
            results.append({"rule_id": rid, "result": "correct", "override_discrepancy": True,
                            "note": f"待確認事項全部裁示完畢：{notes}"})
        if not results:
            continue
        spec = {
            "verified_by": verified_by,
            "verified_date": when,
            "evidence": f"待確認事項逐則裁示並經 pending_review.py apply 先紅再綠更正（疑義檔：{sheet_path or vs.DISCREPANCY_DIR}）",
            "results": results,
        }
        os.makedirs(RECORD_DIR, exist_ok=True)
        record = os.path.join(RECORD_DIR, f"results-{when.replace('-', '')}-pending-review.json")
        save_json(record, spec)
        applied, _ = vs.apply_results(rules_path, spec, sheet_path)
        done.extend(applied)
    return done


# ---------------------------------------------------------------------------
# render — 產生 待確認事項.md 並同步 README
# ---------------------------------------------------------------------------

def doc_markdown(sheet_path, doc):
    pending = open_findings(doc)
    lines = [
        "# 待確認事項（規則參數 vs 現行條文）",
        "",
        f"> 本檔由 `python3 tools/pending_review.py render` 自動產生，資料來源 `{sheet_path}`。",
        "> **請勿手動編輯**——裁示請走 `python3 tools/pending_review.py decide`。",
        "",
        f"- 法規版本：{doc.get('regulation_version', '未注明')}",
        f"- 清單編號：{doc.get('sheet_id', '?')}（建立於 {doc.get('created_date', '?')}）",
        f"- 待確認：**{len(pending)} 則**（本檔共 {len(doc.get('findings', []))} 則）",
        "",
        "## 這份檔案在做什麼",
        "",
        "規則庫的參數必須逐條對得上現行條文。比對出差異的項目**不會**被標成已確認，",
        "而是逐則列在這裡，等具消防專業的使用者裁示。裁示後系統會自動走先紅再綠完成更正、",
        "回填 `verified`、更新 README，並在全部裁示完畢時移除本檔。",
        "",
        "```bash",
        "python3 tools/pending_review.py list                      # 逐則列出（AI 開場會自動跑）",
        "python3 tools/pending_review.py decide --id D-015-01 \\",
        "        --decision 採納更正 --by \"○○○（消防設備師）\"    # 記錄裁示",
        "python3 tools/pending_review.py apply --all               # 先紅再綠自動更正並回填 verified",
        "```",
        "",
        "裁示值：`採納更正`（依建議更正參數）／`維持現值`（現值正確，不改）／",
        "`另有更正`（提供不同的正確值，須附說明）。",
        "",
    ]
    if not pending:
        lines += ["## 目前沒有待確認事項", "",
                  "所有差異都已裁示完畢，本檔可以刪除。", ""]
        return "\n".join(lines)

    lines += ["## 待確認清單", "",
              "| # | 編號 | 條號 | 規則 | 類型 | 可自動修正 | 裁示 |",
              "|---|------|------|------|------|-----------|------|"]
    for i, f in enumerate(pending, 1):
        lines.append(f"| {i} | {f.get('id')} | {f.get('article')} | `{f.get('rule_id')}` | "
                     f"{f.get('type')} | {'✅' if f.get('auto_fix') else '⚪ 需人工步驟'} | "
                     f"{f.get('decision') or '待裁示'} |")
    lines.append("")

    for i, f in enumerate(pending, 1):
        lines += [
            f"### {i}. {f.get('id')}｜{f.get('equipment')}｜{f.get('article')}",
            "",
            f"- **規則**：`{f.get('rule_id')}`（{f.get('target_file')}）",
            f"- **差異類型**：{f.get('type')}",
            "",
            "**條文原文**",
            "",
            f"> {f.get('article_quote', '')}",
            "",
            f"**規則現值**：{f.get('current_value', '')}",
            "",
            f"**差異**：{f.get('difference', '')}",
            "",
            f"**影響**：{f.get('impact', '')}",
            "",
            f"**建議更正**：{f.get('suggested_fix', '')}",
            "",
        ]
        if f.get("note"):
            lines += [f"**備註**：{f['note']}", ""]
        if f.get("auto_fix"):
            lines += ["**可自動修正**：是。裁示「採納更正」後 `apply` 會先把條文原文寫進 "
                      "`rule_tests.json` 的 expected（測試轉紅），確認紅得正確才改參數（轉綠）。", ""]
        else:
            lines += ["**可自動修正**：否，需人工步驟：", ""]
            for step in f.get("manual_steps") or ["（未填）"]:
                lines.append(f"1. {step}")
            lines.append("")
        if f.get("decision"):
            lines += [f"**已裁示**：{f['decision']}"
                      + (f"（{f.get('decision_note')}）" if f.get("decision_note") else ""), ""]
    return "\n".join(lines)


def readme_block(doc, doc_exists):
    pending = open_findings(doc) if doc else []
    if not pending:
        return "\n".join([
            BEGIN_MARK,
            "### ✅ 目前沒有待確認事項",
            "",
            "規則參數與現行條文的比對差異都已裁示完畢。本區塊由 "
            "`python3 tools/pending_review.py render` 自動維護。",
            END_MARK,
        ])
    undecided = [f for f in pending if not f.get("decision")]
    rules = sorted({f.get("rule_id", "?") for f in pending})
    return "\n".join([
        BEGIN_MARK,
        f"### ⚠️ 有 {len(pending)} 則待確認事項——請先處理再開始審圖",
        "",
        f"規則參數與現行條文（{doc.get('regulation_version', '未注明')}）比對出 {len(pending)} 則差異，"
        f"其中 {len(undecided)} 則尚未裁示。受影響的規則："
        + "、".join(f"`{r}`" for r in rules) + "。",
        "",
        f"完整內容見 **[`{DOC_PATH}`]({DOC_PATH})**" + ("" if doc_exists else "（尚未產生）") + "。",
        "",
        "```bash",
        "python3 tools/pending_review.py status   # 開場檢查（有待確認事項會回結束碼 2）",
        "python3 tools/pending_review.py list     # 逐則列出，交給具消防專業的使用者裁示",
        "python3 tools/pending_review.py apply --all --by \"○○○（消防設備師）\"",
        "```",
        "",
        "裁示完成後 `apply` 會自動走先紅再綠更正參數、回填 `verified`、更新本區塊並移除疑義檔。"
        "在此之前，這些規則的輸出一律附「本參數尚未逐條確認」警語。",
        END_MARK,
    ])


def sync_readme(doc, doc_exists, readme_path=README_PATH):
    with open(readme_path, encoding="utf-8") as f:
        text = f.read()
    block = readme_block(doc, doc_exists)
    if BEGIN_MARK in text and END_MARK in text:
        head, rest = text.split(BEGIN_MARK, 1)
        _, tail = rest.split(END_MARK, 1)
        text = head + block + tail
    else:
        anchor = "\n---\n\n## 一、目標與範圍"
        if anchor in text:
            text = text.replace(anchor, "\n---\n\n" + block + "\n" + anchor, 1)
        else:
            text = text.rstrip() + "\n\n" + block + "\n"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(text)


def archive_sheet(sheet_path):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    target = os.path.join(ARCHIVE_DIR, os.path.basename(sheet_path))
    shutil.move(sheet_path, target)
    return target


def render_all(sheet_path, doc):
    """重產待確認事項文件並同步 README；全部裁示完畢時移除疑義檔並封存。"""
    pending = open_findings(doc)
    if pending:
        with open(DOC_PATH, "w", encoding="utf-8") as f:
            f.write(doc_markdown(sheet_path, doc))
        sync_readme(doc, doc_exists=True)
        print(f"📄 已更新 {DOC_PATH}（{len(pending)} 則待確認）與 README 待確認區塊")
        return EXIT_PENDING
    archived = archive_sheet(sheet_path)
    if os.path.exists(DOC_PATH):
        os.remove(DOC_PATH)
    sync_readme(doc, doc_exists=False)
    print(f"✅ 全部裁示完畢：已移除 {DOC_PATH}，疑義檔封存至 {archived}，README 區塊已更新")
    return EXIT_OK


def cmd_render(args):
    path, doc = load_sheet(args.sheet)
    if path is None:
        if os.path.exists(DOC_PATH):
            os.remove(DOC_PATH)
        sync_readme(None, doc_exists=False)
        print(f"✅ 沒有疑義檔：已移除 {DOC_PATH}（若存在）並更新 README 區塊")
        return EXIT_OK
    return render_all(path, doc)


def main():
    p = argparse.ArgumentParser(description="待確認事項：列出、裁示、先紅再綠自動修正")
    sub = p.add_subparsers(dest="command", required=True)

    def add_sheet(parser):
        parser.add_argument("--sheet", help="疑義檔路徑（預設取 governance/待確認清單/ 最新一份）")

    s = sub.add_parser("status", help="開場檢查：有待確認事項時結束碼 2")
    add_sheet(s)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("list", help="逐則列出待確認事項，交給使用者裁示")
    add_sheet(s)
    s.add_argument("--all", action="store_true", help="含已裁示者")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="顯示單一事項（含自動修正內容）")
    add_sheet(s)
    s.add_argument("--id", required=True)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("decide", help="記錄使用者裁示")
    add_sheet(s)
    s.add_argument("--id")
    s.add_argument("--decision", choices=DECISIONS)
    s.add_argument("--note", help="裁示說明（裁示為「另有更正」時必填）")
    s.add_argument("--by", help="裁示人（預設「使用者本人（消防專業人員）」）")
    s.add_argument("--date", help="裁示日期（預設今天）")
    s.add_argument("--results", help="一次裁示多則的 JSON：{decided_by, decided_date, decisions:[{id,decision,note}]}")
    s.set_defaults(func=cmd_decide)

    s = sub.add_parser("apply", help="執行已裁示事項：先紅再綠更正參數並回填 verified")
    add_sheet(s)
    s.add_argument("--id", action="append", help="只執行指定事項（可重複）")
    s.add_argument("--all", action="store_true", help="執行全部已裁示事項")
    s.add_argument("--by", help="確認人（寫入核定紀錄）")
    s.add_argument("--date", help="日期（預設今天）")
    s.set_defaults(func=cmd_apply)

    s = sub.add_parser("render", help="重產 待確認事項.md 並同步 README 區塊")
    add_sheet(s)
    s.set_defaults(func=cmd_render)

    args = p.parse_args()
    sys.exit(args.func(args) or EXIT_OK)


if __name__ == "__main__":
    main()

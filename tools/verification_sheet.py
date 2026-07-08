#!/usr/bin/env python3
"""規則核定表工具 for drawing_review.

給不使用 GitHub / AI 的消防專業人員用的核定介面：
- export：把規則庫匯出成人類可讀、可列印勾選的「核定表 HTML」
          （每條規則一列：目前參數、法條原文引用、勾選欄、簽名欄）
- apply ：消防人員核定回傳後，由架構管理者填寫結果 JSON，
          本命令回填 verified / verified_by / verified_date / evidence

Zero external dependencies — Python stdlib only.

Usage:
    # 匯出未核定規則的核定表（--all 匯出全部）
    python3 tools/verification_sheet.py export
    python3 tools/verification_sheet.py export --all --output governance/核定表/核定表-20260710.html

    # 回填核定結果
    python3 tools/verification_sheet.py apply --results governance/核定紀錄/results-20260710.json

apply 的 results JSON 格式：
{
  "evidence": "governance/核定紀錄/核定表-20260710-簽名掃描.pdf",
  "verified_by": "○○○（消防設備師）",
  "verified_date": "2026-07-10",
  "results": [
    {"rule_id": "extinguisher-count", "result": "correct"},
    {"rule_id": "indoor-hydrant-coverage", "result": "incorrect", "note": "第二種水平距離應更正為 25m"}
  ]
}

紀律：
- result=correct  → 回填 verified: true（僅此路徑可把規則轉為已核定）
- result=incorrect → 本工具「不會」自動改參數——參數修正必須走先紅再綠：
                     先依核定意見更正 rule_tests.json 的 expected（紅）→ 改規則參數（綠）
                     → 下一輪核定表再送核定
"""

import argparse
import html
import json
import sys
from datetime import date

RULES_PATH = "rules/equipment_rules.json"
TESTS_PATH = "rules/rule_tests.json"

CSS = """
body { font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif; margin: 1.5rem; color: #222; }
h1 { font-size: 1.25rem; } .meta { color: #555; font-size: .85rem; margin-bottom: .8rem; }
.howto { background: #f6f8fa; border: 1px solid #ccc; padding: .8rem 1rem; font-size: .9rem; margin-bottom: 1rem; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { border: 1px solid #888; padding: 6px 8px; vertical-align: top; text-align: left; }
th { background: #efefef; }
pre { margin: 0; white-space: pre-wrap; font-size: .8rem; }
.quote { font-size: .8rem; color: #333; } .quote .pg { color: #777; }
td.check { white-space: nowrap; }
.line { display: inline-block; border-bottom: 1px solid #444; min-width: 8rem; }
.sig td { height: 3.5rem; }
.footer { margin-top: 1rem; font-size: .8rem; color: #a00; }
@media print { .howto { background: #f6f8fa !important; } tr { page-break-inside: avoid; } }
"""


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def quotes_for_rule(tests_doc, rule_id):
    out = []
    for t in tests_doc.get("tests", []):
        if t.get("rule_id") == rule_id:
            src = t.get("source", {})
            out.append((t.get("id", ""), src.get("page"), src.get("quote", "")))
    return out


def cmd_export(args):
    rules_doc = load(args.rules)
    tests_doc = load(args.tests)
    rules = rules_doc["rules"] if args.all else [r for r in rules_doc["rules"] if not r.get("verified")]
    if not rules:
        print("沒有待核定規則（全部 verified: true）。用 --all 匯出全部。")
        return

    rows = []
    for i, r in enumerate(rules, 1):
        params = html.escape(json.dumps(r.get("params", {}), ensure_ascii=False, indent=1))
        qs = quotes_for_rule(tests_doc, r["id"])
        if qs:
            quote_html = "<br>".join(
                f'<span class="quote"><span class="pg">[{html.escape(str(tid))}｜p.{pg if pg is not None else "？"}]</span> {html.escape(q)}</span>'
                for tid, pg, q in qs)
        else:
            quote_html = '<span class="quote" style="color:#a00">（此規則尚無測試引用——核定前應先補測試）</span>'
        status = "已核定" if r.get("verified") else "未核定"
        rows.append(
            f"<tr>"
            f"<td>{i}</td>"
            f"<td><b>{html.escape(r['equipment'])}</b><br>{html.escape(r.get('legal_basis', ''))}<br>"
            f"<small>{html.escape(r['id'])}｜{status}</small></td>"
            f"<td><pre>{params}</pre><small>{html.escape(r.get('note', ''))}</small></td>"
            f"<td>{quote_html}</td>"
            f'<td class="check">☐ 正確<br><br>☐ 錯誤，更正為：<br><span class="line"></span><br><span class="line"></span></td>'
            f"<td></td>"
            f"</tr>"
        )

    today = date.today().isoformat()
    doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="utf-8"><title>規則核定表 {today}</title><style>{CSS}</style></head>
<body>
<h1>消防設備規則核定表</h1>
<div class="meta">匯出日期：{today}｜法規版本：{html.escape(rules_doc.get('regulation_version', '未注明'))}｜
本表 {len(rules)} 條規則（{'全部' if args.all else '僅未核定'}）</div>
<div class="howto">
<b>核定方式（給消防專業人員）：</b>
逐列對照右方「法條原文引用」與您手上的法條清單，檢查「系統目前參數」是否正確。
正確請勾「☐ 正確」；有誤請勾「☐ 錯誤」並寫上正確數值與依據（條號或函釋文號）。
有補充說明（但書、實務認定、函釋差異）請寫在「備註」欄。完成後於表末簽名，回傳紙本或掃描檔即可，
<b>不需要操作任何系統</b>。
</div>
<table>
<thead><tr><th>#</th><th>設備／條號</th><th>系統目前參數</th><th>法條原文引用（頁碼）</th><th>核定結果</th><th>備註／函釋補充</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<table style="margin-top:1rem; width:60%">
<tbody class="sig">
<tr><th style="width:8rem">核定人簽名</th><td></td><th style="width:8rem">日期</th><td></td></tr>
<tr><th>資格／證號</th><td colspan="3"></td></tr>
</tbody>
</table>
<div class="footer">本表為規則庫核定用文件；簽名後的紙本／掃描檔將存檔於 governance/核定紀錄/，作為每條規則 verified 狀態的責任追溯依據。</div>
</body>
</html>
"""
    out = args.output or f"governance/核定表/核定表-{today.replace('-', '')}.html"
    import os
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    no_test = sum(1 for r in rules if not quotes_for_rule(tests_doc, r["id"]))
    print(f"✅ 已匯出核定表：{out}（{len(rules)} 條）")
    if no_test:
        print(f"⚠️ 其中 {no_test} 條規則沒有任何測試引用，核定前應先補 rule_tests.json（先紅再綠）")


def cmd_apply(args):
    spec = load(args.results)
    rules_doc = load(args.rules)
    by_id = {r["id"]: r for r in rules_doc["rules"]}
    verified_by = spec.get("verified_by")
    verified_date = spec.get("verified_date")
    evidence = spec.get("evidence")
    if not (verified_by and verified_date and evidence):
        sys.exit("results JSON 必須包含 verified_by、verified_date、evidence（簽名掃描檔路徑）——缺一不可，這是責任追溯鏈")

    applied, corrections = [], []
    for item in spec["results"]:
        rid = item["rule_id"]
        rule = by_id.get(rid)
        if rule is None:
            sys.exit(f"規則不存在：{rid}")
        if item["result"] == "correct":
            rule["verified"] = True
            rule["verified_by"] = verified_by
            rule["verified_date"] = verified_date
            rule["verification_evidence"] = evidence
            applied.append(rid)
        elif item["result"] == "incorrect":
            corrections.append((rid, item.get("note", "（未附更正說明）")))
        else:
            sys.exit(f"未知 result 值：{item['result']}（僅接受 correct / incorrect）")

    if applied:
        with open(args.rules, "w", encoding="utf-8") as f:
            json.dump(rules_doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
    print(f"✅ 已核定 {len(applied)} 條：{', '.join(applied) if applied else '—'}")
    print(f"   核定人：{verified_by}｜日期：{verified_date}｜存證：{evidence}")
    if corrections:
        print(f"\n🔴 {len(corrections)} 條核定為「錯誤」，本工具不自動改參數，請走先紅再綠：")
        for rid, note in corrections:
            print(f"   - {rid}：{note}")
        print("   步驟：1) 依核定意見更正 rule_tests.json 的 expected（跑 run-tests 應轉紅）")
        print("        2) 更正 equipment_rules.json 參數（轉綠）  3) 下一輪核定表再送核定")
    print("\n收尾：python3 tools/fire_code_calc.py self-test && python3 tools/fire_code_calc.py run-tests --strict")


def main():
    p = argparse.ArgumentParser(description="規則核定表匯出／回填")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("export", help="匯出核定表 HTML（可列印勾選）")
    s.add_argument("--rules", default=RULES_PATH)
    s.add_argument("--tests", default=TESTS_PATH)
    s.add_argument("--all", action="store_true", help="含已核定規則（預設僅未核定）")
    s.add_argument("--output", help="輸出路徑（預設 governance/核定表/核定表-{日期}.html）")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("apply", help="回填核定結果到規則庫")
    s.add_argument("--rules", default=RULES_PATH)
    s.add_argument("--results", required=True, help="核定結果 JSON")
    s.set_defaults(func=cmd_apply)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

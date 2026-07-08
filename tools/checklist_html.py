#!/usr/bin/env python3
"""法條檢核清單 HTML 產生工具 for fire-review.

依檢核結果 JSON 產出「核對用法條清單」HTML：維持標準表格格式，
每一檢核項打勾（☑ 符合 / ☒ 不符合 / ⚪ 需人工判讀 / — 不適用），
條號連結到 rules/regulation-checklist.html 的條文錨點。

Zero external dependencies — Python stdlib only.

Usage:
    python3 checklist_html.py --results output/{案件名}-{日期}/check_results.json

check_results.json 格式：
{
  "case_name": "示範案件",
  "date": "2026-07-08",
  "regulation_version": "…",
  "regulation_html": "../../rules/regulation-checklist.html",
  "items": [
    {"article": "§14", "anchor": "art-14", "equipment": "滅火器", "floor": "1F",
     "requirement": "甲類場所應設", "status": "fail",
     "finding": "應設滅火效能值 5，圖面僅 2 具", "source_page": 12}
  ]
}
status: pass | fail | manual | na
"""

import argparse
import html
import json
from datetime import date

STATUS = {
    "pass":   ("☑", "符合", "pass"),
    "fail":   ("☒", "不符合", "fail"),
    "manual": ("⚪", "需人工判讀", "manual"),
    "na":     ("—", "不適用", "na"),
}

CSS = """
body { font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif; margin: 2rem; color: #222; }
h1 { font-size: 1.3rem; } .meta { color: #555; font-size: .9rem; margin-bottom: 1rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border: 1px solid #999; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
td.mark { text-align: center; font-size: 1.1rem; width: 3.5rem; white-space: nowrap; }
tr.fail td { background: #fdecec; } tr.manual td { background: #f5f5f5; }
.summary { margin: 1rem 0; font-size: .95rem; }
.disclaimer { margin-top: 1.5rem; font-size: .8rem; color: #a00; border-top: 1px solid #ccc; padding-top: .5rem; }
a { color: #0645ad; text-decoration: none; }
@media print { tr.fail td { background: #fdecec !important; } }
"""


def render(results):
    rows = []
    counts = {"pass": 0, "fail": 0, "manual": 0, "na": 0}
    for i, item in enumerate(results["items"], 1):
        mark, label, cls = STATUS.get(item.get("status", "manual"), STATUS["manual"])
        counts[cls] = counts.get(cls, 0) + 1
        reg_html = results.get("regulation_html", "")
        anchor = item.get("anchor", "")
        article = html.escape(item.get("article", ""))
        article_cell = (f'<a href="{html.escape(reg_html)}#{html.escape(anchor)}">{article}</a>'
                        if reg_html and anchor else article)
        src = item.get("source_page")
        src_txt = f"p.{src}" if src else "—"
        rows.append(
            f'<tr class="{cls}">'
            f'<td>{i}</td>'
            f'<td class="mark">{mark} {label}</td>'
            f'<td>{article_cell}</td>'
            f'<td>{html.escape(str(item.get("floor", "—")))}</td>'
            f'<td>{html.escape(item.get("equipment", ""))}</td>'
            f'<td>{html.escape(item.get("requirement", ""))}</td>'
            f'<td>{html.escape(item.get("finding", ""))}</td>'
            f'<td>{src_txt}</td>'
            f"</tr>"
        )

    total = len(results["items"])
    not_coded = results.get("not_coded_articles", [])
    not_coded_note = (f"｜⚪ 規則未入庫 {len(not_coded)} 條（{html.escape('、'.join(not_coded))}）"
                      if not_coded else "")
    scope_note = (f"檢核範圍：{html.escape(results['article_range'])}<br>"
                  if results.get("article_range") else "")
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{html.escape(results['case_name'])} — 法條檢核清單</title>
<style>{CSS}</style>
</head>
<body>
<h1>法條檢核清單 — {html.escape(results['case_name'])}</h1>
<div class="meta">
檢核日期：{html.escape(results.get('date', str(date.today())))}｜
法規版本：{html.escape(results.get('regulation_version', '未注明'))}
</div>
<div class="summary">
{scope_note}共 {total} 項：☑ 符合 {counts['pass']}｜☒ 不符合 {counts['fail']}｜⚪ 需人工判讀 {counts['manual']}｜— 不適用 {counts['na']}{not_coded_note}
</div>
<table>
<thead><tr>
<th>#</th><th>檢核</th><th>法條</th><th>樓層</th><th>設備</th><th>應設要求</th><th>檢核說明</th><th>法條來源頁</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<div class="disclaimer">
本清單由 AI 審圖輔助系統產生，僅供審查參考，最終判斷歸屬專業消防人員；法條內容以現行法規原文為準（點擊條號可開啟法條清單 HTML 對照原文）。
</div>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="法條檢核清單 HTML 產生")
    parser.add_argument("--results", required=True, help="check_results.json 路徑")
    parser.add_argument("--output", help="輸出 HTML 路徑（預設與 results 同目錄，檔名 {案件名}-法條檢核清單.html）")
    args = parser.parse_args()

    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)

    out = args.output
    if not out:
        import os
        out = os.path.join(os.path.dirname(args.results),
                           f"{results['case_name']}-法條檢核清單.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(results))
    fails = sum(1 for i in results["items"] if i.get("status") == "fail")
    print(f"✅ 已輸出檢核清單：{out}（{len(results['items'])} 項，不符合 {fails} 項）")


if __name__ == "__main__":
    main()

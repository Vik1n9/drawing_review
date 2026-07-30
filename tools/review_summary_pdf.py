#!/usr/bin/env python3
"""審查摘要報告 HTML 產生工具 for fire-review.

彙整 case.json、check_results.json 與 annotations.json（可選），
產出列印友善的 HTML 報告，可由瀏覽器直接存為 PDF。

報告結構：
  一、案件基本資料
  二、複合用途判定摘要
  三、應設設備檢核統計
  四、檢核結果明細
  五、缺失摘要（如有 annotations.json）
  六、免責聲明

Zero external dependencies — Python stdlib only.

Usage:
    python3 tools/review_summary_pdf.py --case output/case.json --results output/check_results.json
    python3 tools/review_summary_pdf.py --case output/case.json --results output/check_results.json \
        --annotations output/annotations.json
"""

import argparse
import html
import json
import os
import sys
from datetime import date

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

MANUAL = "⚪需人工判讀"

STATUS_MAP = {
    "pass":   ("☑", "符合"),
    "fail":   ("☒", "不符合"),
    "manual": ("⚪", "需人工判讀"),
    "na":     ("—", "不適用"),
}

SEVERITY_LABEL = {
    "重大缺失": "🔴 重大缺失",
    "一般缺失": "🟠 一般缺失",
    "配置疑義": "🟡 配置疑義",
    "需人工判讀": "⚪ 需人工判讀",
    "建議事項": "🔵 建議事項",
}

CSS = """
@page { size: A4; margin: 2cm; }
* { box-sizing: border-box; }
body {
    font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC", sans-serif;
    margin: 0; padding: 0; color: #222; font-size: 10pt; line-height: 1.6;
}
.page-header {
    border-bottom: 2px solid #17365D; padding-bottom: 8px; margin-bottom: 16px;
}
.page-header h1 { font-size: 16pt; margin: 0; color: #17365D; }
.page-header .meta { font-size: 9pt; color: #555; margin-top: 4px; }
h2 {
    font-size: 13pt; color: #17365D; border-bottom: 1px solid #ccc;
    padding-bottom: 4px; margin-top: 24px; margin-bottom: 12px;
    page-break-after: avoid;
}
h3 { font-size: 11pt; margin-top: 16px; margin-bottom: 8px; page-break-after: avoid; }
table {
    border-collapse: collapse; width: 100%; font-size: 9pt; margin-bottom: 12px;
}
th, td {
    border: 1px solid #999; padding: 5px 7px; text-align: left; vertical-align: top;
}
th { background: #D9EAF7; color: #17365D; font-weight: bold; }
tr.fail td { background: #FDECEC; }
tr.manual td { background: #F5F5F5; }
td.center { text-align: center; }
.stat-box {
    display: inline-block; border: 1px solid #ccc; border-radius: 6px;
    padding: 8px 14px; margin: 4px 6px 4px 0; text-align: center; min-width: 100px;
}
.stat-box .num { font-size: 18pt; font-weight: bold; display: block; }
.stat-box .label { font-size: 8pt; color: #555; }
.stat-box.pass { border-color: #82B366; background: #E2F0D9; }
.stat-box.fail { border-color: #B85450; background: #FDECEC; }
.stat-box.manual { border-color: #999; background: #F5F5F5; }
.stat-box.na { border-color: #ccc; background: #FFF; }
.info-grid { display: grid; grid-template-columns: 180px 1fr; gap: 2px 12px; margin-bottom: 12px; }
.info-grid dt { font-weight: bold; color: #555; padding: 3px 0; }
.info-grid dd { margin: 0; padding: 3px 0; }
.disclaimer {
    margin-top: 24px; padding-top: 12px; border-top: 2px solid #B85450;
    font-size: 8.5pt; color: #B85450; line-height: 1.8;
}
.severity-tag { font-weight: bold; }
.severity-重大缺失 { color: #B85450; }
.severity-一般缺失 { color: #C55A11; }
.severity-配置疑義 { color: #BF9000; }
.severity-需人工判讀 { color: #666; }
.severity-建議事項 { color: #2E75B6; }
@media print {
    body { margin: 0; }
    h2 { page-break-before: auto; }
    table { page-break-inside: avoid; }
    tr.fail td { background: #FDECEC !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    tr.manual td { background: #F5F5F5 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .stat-box { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    th { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


# ---------------------------------------------------------------- 資料萃取

def get_value(field):
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def get_confidence(field):
    return field.get("confidence") if isinstance(field, dict) else None


def extract_case_info(case):
    """從 case.json 萃取基本案件資訊。"""
    permit = case.get("use_permit") or {}
    renovation = case.get("interior_renovation") or {}
    floors = case.get("floors") or []

    permit_no = get_value(permit.get("permit_no")) or MANUAL
    renovation_floors = get_value(renovation.get("floors")) or []
    renovation_area = get_value(renovation.get("area"))
    total_area = sum(get_value(fl.get("area")) or 0 for fl in floors)

    return {
        "case_name": case.get("case_name") or MANUAL,
        "permit_no": permit_no,
        "renovation_floors": "、".join(str(f) for f in renovation_floors) or MANUAL,
        "renovation_area": f"{renovation_area} m²" if renovation_area is not None else MANUAL,
        "floor_count": len(floors),
        "total_area": f"{total_area} m²",
        "regulation_version": case.get("regulation_version", "未注明"),
    }


def extract_mixed_use(case):
    """從 case.json 萃取複合用途判定資訊。"""
    floors = case.get("floors") or []
    building = case.get("building") or {}
    assessment = building.get("mixed_use_assessment") or {}

    floor_uses = []
    for fl in floors:
        use = fl.get("use_category") or {}
        label = use.get("label") if isinstance(use, dict) else None
        value = get_value(use)
        legal = use.get("legal_basis") if isinstance(use, dict) else None
        floor_uses.append({
            "floor": fl.get("floor", MANUAL),
            "use": f"{label}（{value}）" if label and value else str(label or value or MANUAL),
            "legal_basis": legal or MANUAL,
        })

    is_mixed = assessment.get("is_mixed_use")
    if is_mixed is True:
        candidate = assessment.get("category_candidate", "")
        verdict = f"{candidate} 複合用途建築物" if candidate else "複合用途建築物"
    elif is_mixed is False:
        verdict = "單一用途建築物"
    else:
        verdict = MANUAL

    return {"floor_uses": floor_uses, "verdict": verdict, "source": assessment.get("source", "")}


def extract_annotation_stats(annotations):
    """從 annotations.json 統計缺失分級。"""
    if not annotations:
        return {}
    stats = {}
    for ann in annotations.get("annotations", []):
        sev = ann.get("severity", "需人工判讀")
        stats[sev] = stats.get(sev, 0) + 1
    return stats


# ---------------------------------------------------------------- HTML 渲染

def render_section_case_info(info, check_date):
    return f"""
<h2>一、案件基本資料</h2>
<dl class="info-grid">
  <dt>案名</dt><dd>{html.escape(str(info['case_name']))}</dd>
  <dt>使用執照字號</dt><dd>{html.escape(str(info['permit_no']))}</dd>
  <dt>申請範圍樓層</dt><dd>{html.escape(str(info['renovation_floors']))}</dd>
  <dt>申請範圍面積</dt><dd>{html.escape(str(info['renovation_area']))}</dd>
  <dt>樓層數</dt><dd>{info['floor_count']} 層</dd>
  <dt>總樓地板面積</dt><dd>{html.escape(str(info['total_area']))}</dd>
  <dt>法規版本</dt><dd>{html.escape(str(info['regulation_version']))}</dd>
  <dt>檢核日期</dt><dd>{html.escape(str(check_date))}</dd>
</dl>
"""


def render_section_mixed_use(mixed_use):
    rows = ""
    for fu in mixed_use["floor_uses"]:
        rows += (f"<tr><td>{html.escape(str(fu['floor']))}</td>"
                 f"<td>{html.escape(str(fu['use']))}</td>"
                 f"<td>{html.escape(str(fu['legal_basis']))}</td></tr>\n")

    return f"""
<h2>二、複合用途判定摘要</h2>
<table>
<thead><tr><th>樓層</th><th>用途</th><th>§12 分類</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p><strong>判定結果：</strong>{html.escape(str(mixed_use['verdict']))}
{"（來源：人工確認）" if mixed_use['source'] == 'manual' else ""}</p>
"""


def render_section_stats(results):
    counts = {"pass": 0, "fail": 0, "manual": 0, "na": 0}
    for item in results.get("items", []):
        s = item.get("status", "manual")
        if s in counts:
            counts[s] += 1
    total = len(results.get("items", []))

    # 未核定參數統計
    unverified = sum(
        1 for i in results.get("items", [])
        if "本參數尚未逐條確認" in str(i.get("finding", ""))
    )
    unverified_ratio = f"{unverified / total * 100:.1f}%" if total > 0 else "0.0%"

    return f"""
<h2>三、應設設備檢核統計</h2>
<div>
  <div class="stat-box pass"><span class="num">{counts['pass']}</span><span class="label">☑ 符合</span></div>
  <div class="stat-box fail"><span class="num">{counts['fail']}</span><span class="label">☒ 不符合</span></div>
  <div class="stat-box manual"><span class="num">{counts['manual']}</span><span class="label">⚪ 需人工判讀</span></div>
  <div class="stat-box na"><span class="num">{counts['na']}</span><span class="label">— 不適用</span></div>
</div>
<p>共 {total} 項檢核｜未核定參數比例：{unverified_count_text(unverified, total, unverified_ratio)}</p>
"""


def unverified_count_text(count, total, ratio):
    return f"{count} / {total}（{ratio}）"


def render_section_details(results):
    rows = ""
    for idx, item in enumerate(results.get("items", []), start=1):
        status = item.get("status", "manual")
        mark, label = STATUS_MAP.get(status, STATUS_MAP["manual"])
        cls = f' class="{status}"' if status in ("fail", "manual") else ""
        rows += (
            f"<tr{cls}>"
            f"<td class='center'>{idx}</td>"
            f"<td class='center'>{mark} {html.escape(label)}</td>"
            f"<td>{html.escape(str(item.get('article', '')))}</td>"
            f"<td>{html.escape(str(item.get('floor', '—')))}</td>"
            f"<td>{html.escape(str(item.get('equipment', '')))}</td>"
            f"<td>{html.escape(str(item.get('requirement', '')))}</td>"
            f"<td>{html.escape(str(item.get('finding', '')))}</td>"
            f"</tr>\n"
        )

    return f"""
<h2>四、檢核結果明細</h2>
<p>檢核範圍：{html.escape(str(results.get('article_range', '§14~§31')))}</p>
<table>
<thead><tr>
<th style="width:30px">#</th><th style="width:90px">檢核狀態</th><th>法條</th>
<th>樓層</th><th>設備</th><th>應設要求</th><th>檢核說明</th>
</tr></thead>
<tbody>{rows}</tbody>
</table>
"""


def render_section_annotations(annotations):
    if not annotations:
        return ""
    anns = annotations.get("annotations", [])
    if not anns:
        return ""

    stats = extract_annotation_stats(annotations)
    stat_items = ""
    for sev in ("重大缺失", "一般缺失", "配置疑義", "需人工判讀", "建議事項"):
        count = stats.get(sev, 0)
        if count > 0:
            tag = SEVERITY_LABEL.get(sev, sev)
            stat_items += f'<div class="stat-box"><span class="num">{count}</span><span class="label">{html.escape(tag)}</span></div>\n'

    rows = ""
    for ann in anns:
        sev = ann.get("severity", "需人工判讀")
        sev_cls = f"severity-{sev}"
        rows += (
            f"<tr>"
            f"<td class='center'>{ann.get('issue_id', '')}</td>"
            f"<td><span class='severity-tag {sev_cls}'>{html.escape(SEVERITY_LABEL.get(sev, sev))}</span></td>"
            f"<td>{html.escape(str(ann.get('label', '')))}</td>"
            f"<td>{html.escape(str(ann.get('note', '')))}</td>"
            f"</tr>\n"
        )

    low_conf = any(a.get("position_confidence") == "low" for a in anns)
    low_conf_note = ""
    if low_conf:
        low_conf_note = '<p style="color:#B85450;font-size:8.5pt;">⚠ 部分標註位置為 AI 推定（position_confidence: low），以文字說明為準。</p>'

    return f"""
<h2>五、缺失摘要</h2>
<div>{stat_items}</div>
{low_conf_note}
<table>
<thead><tr><th style="width:30px">#</th><th style="width:100px">嚴重程度</th><th>項目</th><th>說明</th></tr></thead>
<tbody>{rows}</tbody>
</table>
"""


def render_disclaimer(results):
    not_coded = results.get("not_coded_articles", [])
    not_coded_note = ""
    if not_coded:
        not_coded_note = (
            f"<p>規則未入庫條號（{len(not_coded)} 條）："
            f"{html.escape('、'.join(not_coded))}。"
            f"上述條號因門檻尚未結構化入庫，以需人工判讀列出。</p>"
        )

    reg_ver = html.escape(str(results.get("regulation_version", "未注明")))
    not_coded_block = not_coded_note

    return (
        '<h2>六、免責聲明</h2>'
        '<div class="disclaimer">'
        '<p><strong>AI 輔助審查聲明：</strong>本報告由 AI 審圖輔助系統產生，僅供審查參考。'
        '最終判斷與法律責任歸屬專業消防人員。</p>'
        '<p><strong>法規版本聲明：</strong>本報告依據《各類場所消防安全設備設置標準》'
        f'（法規版本：{reg_ver}）'
        '進行檢核，法條內容以現行法規原文為準。</p>'
        '<p><strong>判斷慣例警語：</strong>本報告若援引 rules/stage_two_judgment_rules.md 或 '
        'rules/review_corrections.md 之判斷慣例，該等慣例未經消防專業人員核定，'
        '以現行法規為準。</p>'
        f'{not_coded_block}'
        '</div>'
    )


def render_report(case, results, annotations):
    """組合完整報告 HTML。"""
    info = extract_case_info(case)
    mixed_use = extract_mixed_use(case)
    check_date = results.get("date", str(date.today()))

    sections = [
        render_section_case_info(info, check_date),
        render_section_mixed_use(mixed_use),
        render_section_stats(results),
        render_section_details(results),
        render_section_annotations(annotations),
        render_disclaimer(results),
    ]

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{html.escape(str(info['case_name']))} — 審查摘要報告</title>
<style>{CSS}</style>
</head>
<body>
<div class="page-header">
  <h1>審查摘要報告 — {html.escape(str(info['case_name']))}</h1>
  <div class="meta">
    產出日期：{html.escape(str(check_date))}｜
    法規版本：{html.escape(str(info['regulation_version']))}｜
    AI 審圖輔助系統
  </div>
</div>
{"".join(sections)}
</body>
</html>
"""


# ---------------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(description="審查摘要報告 HTML 產生")
    parser.add_argument("--case", required=True, help="case.json 路徑")
    parser.add_argument("--results", required=True, help="check_results.json 路徑")
    parser.add_argument("--annotations", help="annotations.json 路徑（可選，用於缺失摘要）")
    parser.add_argument("--output", help="輸出 HTML 路徑（預設與 case.json 同目錄）")
    args = parser.parse_args(argv)

    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)
    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)

    annotations = None
    if args.annotations and os.path.exists(args.annotations):
        with open(args.annotations, encoding="utf-8") as f:
            annotations = json.load(f)

    report_html = render_report(case, results, annotations)

    out = args.output
    if not out:
        out = os.path.join(os.path.dirname(args.case),
                           f"{case.get('case_name', '案件')}-審查摘要報告.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(report_html)

    total = len(results.get("items", []))
    fails = sum(1 for i in results.get("items", []) if i.get("status") == "fail")
    ann_count = len((annotations or {}).get("annotations", []))
    print(f"✅ 已輸出審查摘要報告：{out}（檢核 {total} 項、不符合 {fails} 項"
          f"{f'、缺失標註 {ann_count} 處' if ann_count else ''}）")
    print("   提示：以瀏覽器開啟 HTML 後可使用「列印 → 另存 PDF」功能產出 PDF。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

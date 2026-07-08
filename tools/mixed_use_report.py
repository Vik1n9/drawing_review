#!/usr/bin/env python3
"""複合用途建築物及樓層屬性檢討表 HTML 產生工具 for fire-review.

依 case.json（正典資料）產出「複合用途建築物及樓層屬性檢討」HTML，
主表格式對齊消防實務範例（input/範例/複合用途建築物及樓層屬性檢討-範例.pdf）：

    樓層｜各層用途｜樓地板面積(㎡)｜本次申請範圍樓地板面積(㎡)｜樓層屬性

另附審圖輔助欄（§12 款目、主/從角色、判定依據、來源、信心度），
表尾為「複合用途建築物判定」編號結論段。null 或 confidence: low 一律顯示「⚪需人工判讀」。

Zero external dependencies — Python stdlib only.

Usage:
    python3 tools/mixed_use_report.py --case output/{案件名}-{日期}/case.json
"""

import argparse
import html
import json
import os
from datetime import date

MANUAL = "⚪需人工判讀"

CSS = """
body { font-family: "Noto Sans TC", "Microsoft JhengHei", sans-serif; margin: 2rem; color: #222; }
h1 { font-size: 1.3rem; } h2 { font-size: 1.05rem; margin-top: 1.5rem; }
.meta { color: #555; font-size: .9rem; margin-bottom: 1rem; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border: 1px solid #999; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f0f0f0; }
td.num { text-align: right; white-space: nowrap; }
tr.total td { font-weight: bold; background: #f7f7f7; }
td.manual { color: #666; }
ol.verdict { font-size: .95rem; line-height: 1.7; }
.disclaimer { margin-top: 1.5rem; font-size: .8rem; color: #a00; border-top: 1px solid #ccc; padding-top: .5rem; }
"""


def get_value(field):
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def get_confidence(field):
    if isinstance(field, dict):
        return field.get("confidence")
    return None


def cell(field, fmt=lambda v: str(v)):
    """欄位 → (顯示文字, 是否需人工判讀)。null 或 low 信心 → 需人工判讀。"""
    v = get_value(field)
    if v is None or get_confidence(field) == "low":
        return MANUAL, True
    return fmt(v), False


def floor_attribute(fl):
    """樓層屬性：地下層／屋頂層／無開口樓層／一般樓層；判定不明 → 需人工判讀。"""
    pos = get_value(fl.get("floor_position", None))
    pos_conf = get_confidence(fl.get("floor_position", None))
    windowless = get_value(fl.get("windowless", None))
    if pos is None or pos_conf == "low":
        return MANUAL, True
    if isinstance(pos, dict):
        pos = pos.get("value")
    if pos == "basement":
        return "地下層", False
    if pos in ("roof_level", "roof"):
        return "屋頂層", False
    if windowless is True:
        return "無開口樓層", False
    if windowless is None:
        return f"一般樓層（無開口判定：{MANUAL}）", True
    return "一般樓層", False


def renovation_area_for(case, floor_label):
    """本次申請範圍樓地板面積：僅裝修樓層顯示。"""
    reno = case.get("interior_renovation", {}) or {}
    reno_floors = get_value(reno.get("floors", None)) or []
    if floor_label in reno_floors:
        area = get_value(reno.get("area", None))
        if area is not None:
            return f"{area} ㎡"
        return MANUAL
    return ""


def use_relation_text(fl):
    rel = fl.get("use_relation", {}) or {}
    role = rel.get("role")
    labels = {"principal": "主用途", "subordinate": "從屬用途", "independent": "獨立用途（非從屬）"}
    if role is None or rel.get("confidence") == "low":
        return MANUAL, True
    text = labels.get(role, str(role))
    sub_to = rel.get("subordinate_to")
    if role == "subordinate" and sub_to:
        text += f"（從屬於 {sub_to}）"
    return text, False


def build_verdict_lines(case):
    """表尾「複合用途建築物判定」編號結論。"""
    lines = []

    # 1) 各用途區段歸納
    groups = {}
    for fl in case.get("floors", []):
        use = fl.get("use_category", {}) or {}
        key = get_value(use) or "（用途未確認）"
        label = use.get("label", "") if isinstance(use, dict) else ""
        groups.setdefault((key, label), []).append(fl.get("floor", "?"))
    for (key, label), floors in groups.items():
        shown = key + (f"（{label}）" if label else "")
        lines.append(f"本建物 {'、'.join(floors)} 之用途為 {shown}。")

    # 2) 主用途
    pu = (case.get("building", {}) or {}).get("principal_use", {}) or {}
    pu_text, pu_manual = cell(pu)
    if pu_manual:
        lines.append(f"主用途：{MANUAL}——{pu.get('basis', '主從關係尚未依對照表判定')}。")
    else:
        lines.append(f"本建物主用途為 {pu_text}（{pu.get('legal_basis') or ''}；{pu.get('basis', '')}）。")

    # 3) 複合用途判定與 §12 分類
    mua = (case.get("building", {}) or {}).get("mixed_use_assessment", {}) or {}
    is_mixed = mua.get("is_mixed_use")
    candidate = mua.get("category_candidate")
    basis = mua.get("basis", "")
    conf = mua.get("confidence")
    if is_mixed is True and conf != "low":
        lines.append(f"本場所判定為複合用途建築物，§12 分類：{candidate or MANUAL}（{basis}）。")
    elif is_mixed is False and conf != "low":
        lines.append(f"本場所非複合用途建築物（{basis}）。")
    else:
        lines.append(f"是否構成複合用途建築物：{MANUAL}——{basis}"
                     f"{'；候選分類 ' + candidate if candidate else ''}。")
    return lines


def render(case):
    case_name = case.get("case_name", "(未命名案件)")
    rows = []
    total_area = 0
    total_area_known = True
    total_reno = 0
    has_reno = False

    for fl in case.get("floors", []):
        label = fl.get("floor", "?")
        area_text, area_manual = cell(fl.get("area"), lambda v: f"{v} ㎡")
        v = get_value(fl.get("area"))
        if isinstance(v, (int, float)) and not area_manual:
            total_area += v
        else:
            total_area_known = False
        use = fl.get("use_category", {}) or {}
        use_text, use_manual = cell(use, lambda v: str(v))
        use_label = use.get("label", "") if isinstance(use, dict) else ""
        legal = (use.get("legal_basis") or "") if isinstance(use, dict) else ""
        attr_text, attr_manual = floor_attribute(fl)
        reno_text = renovation_area_for(case, label)
        if reno_text and reno_text != MANUAL:
            has_reno = True
            try:
                total_reno += float(reno_text.rstrip(" ㎡"))
            except ValueError:
                pass
        rel_text, rel_manual = use_relation_text(fl)
        rel = fl.get("use_relation", {}) or {}
        src = rel.get("source", "") or ""
        conf = rel.get("confidence", "") or ""
        basis = rel.get("basis", "") or ""

        def td(text, manual, cls=""):
            classes = " ".join(c for c in [cls, "manual" if manual else ""] if c)
            return f'<td class="{classes}">{html.escape(text)}</td>' if classes else f"<td>{html.escape(text)}</td>"

        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            + td(f"{use_label}" if not use_manual and use_label else use_text, use_manual)
            + td(area_text, area_manual, "num")
            + f'<td class="num">{html.escape(reno_text)}</td>'
            + td(attr_text, attr_manual)
            + td(use_text if not use_manual else MANUAL, use_manual)
            + f"<td>{html.escape(legal)}</td>"
            + td(rel_text, rel_manual)
            + f"<td>{html.escape(basis)}</td>"
            + f"<td>{html.escape(str(src))}／{html.escape(str(conf))}</td>"
            + "</tr>"
        )

    total_area_text = f"{total_area:g} ㎡" if total_area_known else f"{total_area:g} ㎡（部分樓層{MANUAL}，非完整合計）"
    total_reno_text = f"{total_reno:g} ㎡" if has_reno else ""
    rows.append(
        '<tr class="total">'
        f"<td colspan=\"2\">樓地板面積合計</td>"
        f'<td class="num">{html.escape(total_area_text)}</td>'
        f'<td class="num">{html.escape(total_reno_text)}</td>'
        f"<td colspan=\"6\"></td></tr>"
    )

    verdict_items = "\n".join(f"<li>{html.escape(t)}</li>" for t in build_verdict_lines(case))

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{html.escape(case_name)} — 複合用途建築物及樓層屬性檢討</title>
<style>{CSS}</style>
</head>
<body>
<h1>複合用途建築物及樓層屬性檢討 — {html.escape(case_name)}</h1>
<div class="meta">
產出日期：{date.today()}｜法規版本：{html.escape(case.get('regulation_version', '未注明'))}｜
資料來源：case.json（人工確認後之正典資料）
</div>
<table>
<thead><tr>
<th>樓層</th><th>各層用途</th><th>樓地板面積(㎡)</th><th>本次申請範圍<br>樓地板面積(㎡)</th><th>樓層屬性</th>
<th>§12 款目</th><th>法條依據</th><th>主/從角色</th><th>判定依據</th><th>來源／信心度</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table>
<h2>複合用途建築物判定：</h2>
<ol class="verdict">
{verdict_items}
</ol>
<div class="disclaimer">
本表由 AI 審圖輔助系統依 case.json 產生，僅供審查參考，最終判斷歸屬專業消防人員。
「⚪需人工判讀」欄位嚴禁以推測填充；主用途／從屬用途之判定基準依內政部消防署
《複合用途建築物判斷基準》及其附表「建築物主用途及從屬用途關係對照表」
（rules/法規/建築物主用途及從屬用途關係對照表.pdf），經人工確認後回填 case.json 方可定案。
</div>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="複合用途建築物及樓層屬性檢討表 HTML 產生")
    parser.add_argument("--case", required=True, help="case.json 路徑")
    parser.add_argument("--output", help="輸出 HTML 路徑（預設與 case.json 同目錄，檔名 {案件名}-複合用途及樓層屬性檢討.html）")
    args = parser.parse_args()

    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)

    out = args.output or os.path.join(os.path.dirname(args.case),
                                      f"{case.get('case_name', '案件')}-複合用途及樓層屬性檢討.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(case))
    manual_count = render(case).count(MANUAL)
    print(f"✅ 已輸出檢討表：{out}（{len(case.get('floors', []))} 層；{MANUAL} 出現 {manual_count} 處）")


if __name__ == "__main__":
    main()

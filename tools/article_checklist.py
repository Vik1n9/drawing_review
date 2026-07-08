#!/usr/bin/env python3
"""§14~§31 逐條窮舉檢核產生工具 for fire-review.

對《各類場所消防安全設備設置標準》第 14 條至第 31 條逐條產生 check_results.json：
- 條號已入規則庫（equipment_rules.json）→ 依 fire_code_calc.threshold_results 逐層列
  應設/免設/需人工判讀（免設也列，呈現正反兩面供覆核）
- 條號未入規則庫 → 輸出一列「⚪ 需人工判讀（規則未入庫）」，應設要求取自
  rules/regulation_articles/article-0NN.json 條文原文 snippet（可追溯、不憑記憶）

窮舉性由本工具保證：§14~§31 每條至少一列，缺一條即視為錯誤（exit 1）。
既有設備僅做「有/無」初篩；數量足額與配置檢核由 /gap-analysis 以計算工具完成後更新。

Zero external dependencies — Python stdlib only.

Usage:
    python3 tools/article_checklist.py --case output/{案件名}-{日期}/case.json
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fire_code_calc as fcc  # noqa: E402

ARTICLE_FIRST, ARTICLE_LAST = 14, 31

# 設備名稱 → case.json floors[].existing_equipment 鍵（僅做有/無初篩）
EQUIPMENT_KEYS = {
    "滅火器": ["extinguisher"],
    "室內消防栓": ["indoor_hydrant"],
    "自動撒水設備": ["sprinkler_head"],
    "火警自動警報設備": ["smoke_detector", "heat_detector"],
    "出口標示燈・避難方向指示燈": ["exit_light", "direction_light"],
    "緊急照明設備": ["emergency_light"],
    "排煙設備": ["smoke_exhaust"],
}


def article_no(legal_basis):
    """'§14' → 14；解析失敗回傳 None。"""
    try:
        return int(str(legal_basis).lstrip("§").split("-")[0])
    except (ValueError, AttributeError):
        return None


def load_article(articles_dir, n):
    path = os.path.join(articles_dir, f"article-{n:03d}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def existing_count(case, floor_label, equipment):
    """回傳該層該設備既有數量合計；鍵未登載回傳 None（不可推定為 0）。"""
    keys = EQUIPMENT_KEYS.get(equipment)
    if not keys:
        return None
    for fl in case.get("floors", []):
        if fl.get("floor") == floor_label:
            eq = fl.get("existing_equipment", {}) or {}
            vals = [eq.get(k) for k in keys]
            if all(v is None for v in vals):
                return None
            return sum(int(v) for v in vals if v is not None)
    return None


def coded_item(case, tr):
    """threshold_results 單項 → check_results item。"""
    verdict = tr["verdict"]
    base_verdict = verdict.split("（")[0]
    n = article_no(tr["legal_basis"])
    item = {
        "article": tr["legal_basis"],
        "anchor": f"art-{n}" if n else "",
        "equipment": tr["equipment"],
        "floor": tr["floor"],
        "requirement": tr["reason"],
        "rule_status": "coded",
        "source_page": None,
    }
    if base_verdict == "免設":
        item["status"] = "pass"
        item["finding"] = f"免設：{tr['reason']}（計算過程供覆核，原則 8）"
    elif base_verdict == "應設":
        cnt = existing_count(case, tr["floor"], tr["equipment"])
        if cnt is None:
            item["status"] = "manual"
            item["finding"] = "應設；既有設備數量未登載於 case.json，是否設置需人工判讀"
        elif cnt == 0:
            item["status"] = "fail"
            item["finding"] = "法定應設而圖面未見既有設備（重大缺失候選；數量核算由 /gap-analysis 補充）"
        else:
            item["status"] = "manual"
            item["finding"] = f"應設；圖面既有 {cnt} 具，數量足額與配置需 /gap-analysis 計算與逐點檢核"
    else:
        item["status"] = "manual"
        item["finding"] = f"需人工判讀：{tr['reason']}"
    if not tr.get("verified", False):
        item["finding"] += f"｜{fcc.UNVERIFIED_WARNING}"
    return item


def not_coded_item(article_doc, n, quantity_rule_ids=()):
    snippet = (article_doc or {}).get("snippet", "")
    title = (article_doc or {}).get("title", f"第 {n} 條")
    tags = (article_doc or {}).get("equipment_tags", [])
    if quantity_rule_ids:
        status_note = (f"⚪ 需人工判讀：本條已入庫為數量/配置規則（{'、'.join(quantity_rule_ids)}），"
                       "不做門檻判斷；數量計算與逐點配置由 /code-requirements、/gap-analysis 以計算工具執行")
        rule_status = "coded_quantity"
    else:
        status_note = ("⚪ 需人工判讀（規則未入庫）：本條門檻尚未結構化入 equipment_rules.json，"
                       "請點條號對照原文逐項確認")
        rule_status = "not_coded"
    return {
        "article": f"§{n}",
        "anchor": f"art-{n}",
        "equipment": "、".join(tags[:3]) if tags else title,
        "floor": "—",
        "requirement": snippet if snippet else f"（{title} 條文原文未索引，請查 rules/法規/）",
        "status": "manual",
        "finding": status_note,
        "rule_status": rule_status,
        "source_page": None,
    }


def build_results(case_path, rules_path, articles_dir):
    rules_doc = fcc.load_rules(rules_path)
    with open(case_path, encoding="utf-8") as f:
        case = json.load(f)

    _, threshold = fcc.threshold_results(rules_doc, case)

    items_by_article = {}
    for tr in threshold:
        n = article_no(tr["legal_basis"])
        if n is None or not (ARTICLE_FIRST <= n <= ARTICLE_LAST):
            continue
        items_by_article.setdefault(n, []).append(coded_item(case, tr))

    # 已入庫但非門檻類的規則（如 §31 滅火器配置數量計算），列為 coded_quantity 而非未入庫
    quantity_rules_by_article = {}
    for r in rules_doc["rules"]:
        n = article_no(r.get("legal_basis"))
        if n is not None and ARTICLE_FIRST <= n <= ARTICLE_LAST and n not in items_by_article:
            quantity_rules_by_article.setdefault(n, []).append(r["id"])

    not_coded = []
    items = []
    for n in range(ARTICLE_FIRST, ARTICLE_LAST + 1):
        if n in items_by_article:
            items.extend(items_by_article[n])
        else:
            qids = quantity_rules_by_article.get(n, ())
            items.append(not_coded_item(load_article(articles_dir, n), n, qids))
            if not qids:
                not_coded.append(f"§{n}")

    covered = {article_no(i["article"]) for i in items}
    missing = [n for n in range(ARTICLE_FIRST, ARTICLE_LAST + 1) if n not in covered]
    if missing:
        sys.exit(f"窮舉檢查失敗：缺條號 {missing}")

    return {
        "case_name": case.get("case_name", "(未命名案件)"),
        "date": str(date.today()),
        "regulation_version": rules_doc.get("regulation_version", "未注明"),
        "regulation_html": "../../rules/regulation-checklist.html",
        "article_range": f"§{ARTICLE_FIRST}~§{ARTICLE_LAST}（逐條窮舉）",
        "not_coded_articles": not_coded,
        "items": items,
    }


def main():
    parser = argparse.ArgumentParser(description="§14~§31 逐條窮舉檢核產生")
    parser.add_argument("--case", required=True, help="case.json 路徑")
    parser.add_argument("--rules", default="rules/equipment_rules.json")
    parser.add_argument("--articles-dir", default="rules/regulation_articles")
    parser.add_argument("--output", help="輸出 check_results.json 路徑（預設與 case.json 同目錄）")
    args = parser.parse_args()

    results = build_results(args.case, args.rules, args.articles_dir)
    out = args.output or os.path.join(os.path.dirname(args.case), "check_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    counts = {}
    for i in results["items"]:
        counts[i["status"]] = counts.get(i["status"], 0) + 1
    print(f"✅ 已輸出 {out}：§{ARTICLE_FIRST}~§{ARTICLE_LAST} 逐條窮舉共 {len(results['items'])} 項"
          f"（pass {counts.get('pass', 0)} / fail {counts.get('fail', 0)} / manual {counts.get('manual', 0)}）")
    if results["not_coded_articles"]:
        print(f"⚪ 規則未入庫 {len(results['not_coded_articles'])} 條：{'、'.join(results['not_coded_articles'])}"
              "（以需人工判讀列出，後續逐條先紅再綠入庫）")


if __name__ == "__main__":
    main()

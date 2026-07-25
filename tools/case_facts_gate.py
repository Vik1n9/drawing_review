#!/usr/bin/env python3
"""兩階段審查的受控自動化關卡 for fire-review.

在第一／第二階段交付物匯出**之前**，機械式檢查 case.json 的案件事實是否齊備。
關卡不通過（ready: false，結束碼 2）時，不得輸出最終交付物；必須逐項向使用者詢問
`questions` 內容、補齊 case.json 後重新檢查。

**嚴禁以猜測、預設值或未提供的圖說補足資料**（審圖最高原則 5：需人工判讀原則）。
本工具只檢查「事實是否齊備」，不做任何法規判斷、不推算門檻數值。

case.json 是正典資料（最高原則 4）；本工具直接讀 case.json，不另建平行事實檔。
為與外部工作流程互通，另接受扁平事實格式（caseName/permit/application/floors/firstStage）。

Zero external dependencies — Python stdlib only.

Usage:
    python3 tools/case_facts_gate.py --stage first  --case output/{案件名}-{日期}/case.json
    python3 tools/case_facts_gate.py --stage second --case output/{案件名}-{日期}/case.json
    python3 tools/case_facts_gate.py --stage second --case case.json --format json
"""

import argparse
import json
import sys

STAGES = ("first", "second")


def get_value(field):
    """欄位 → 值。支援 {"value": x, ...} 包裝與裸值。"""
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def get_confidence(field):
    return field.get("confidence") if isinstance(field, dict) else None


def is_positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def is_flat_facts(doc):
    """外部工作流程的扁平事實格式（camelCase）。"""
    return "caseName" in doc or ("permit" in doc and "use_permit" not in doc)


def normalize_flat(doc):
    """扁平事實格式 → case.json 欄位結構，讓兩種輸入走同一套檢查。"""
    floors = []
    for fl in doc.get("floors") or []:
        floors.append({
            "floor": fl.get("name"),
            "area": {"value": fl.get("area"), "source": fl.get("source")},
            "use_category": {"value": fl.get("use")},
        })
    first_stage = doc.get("firstStage") or {}
    return {
        "case_name": doc.get("caseName"),
        "use_permit": {"permit_no": {"value": (doc.get("permit") or {}).get("number")}},
        "interior_renovation": {
            "floors": {"value": [(doc.get("application") or {}).get("floor")]
                       if (doc.get("application") or {}).get("floor") else None},
            "area": {"value": (doc.get("application") or {}).get("area")},
        },
        "floors": floors,
        "manual_review_items": list(doc.get("conflicts") or []),
        "building": {
            "mixed_use_assessment": {
                "is_mixed_use": None,
                "category_candidate": first_stage.get("judgment"),
                "source": "manual" if first_stage.get("judgment") else None,
            }
        },
        "_first_stage_classifications": first_stage.get("classifications") or [],
    }


def question(code, field, reason, stage, action):
    return {"code": code, "field": field, "reason": reason, "stage": stage, "action": action}


def check_permit(case, stage):
    permit_no = get_value(((case.get("use_permit") or {}).get("permit_no")))
    if not permit_no:
        return [question(
            "MISSING_PERMIT", "use_permit.permit_no",
            "缺少使用執照字號，無法追溯建築物基本資料與原核准用途。",
            stage, "向使用者索取使用執照；確無使用執照可考時，於 manual_review_items 明確記載「無使用執照可考」後始得放行。")]
    return []


def check_application(case, stage):
    reno = case.get("interior_renovation") or {}
    floors = get_value(reno.get("floors"))
    area = get_value(reno.get("area"))
    problems = []
    if not floors or not any(floors):
        problems.append(question(
            "MISSING_APPLICATION_FLOOR", "interior_renovation.floors",
            "缺少本次申請樓層，無法界定本次申請範圍。",
            stage, "向使用者確認本次申請（裝修／變更用途）涉及哪些樓層。"))
    if not is_positive_number(area):
        problems.append(question(
            "MISSING_APPLICATION_AREA", "interior_renovation.area",
            "缺少本次申請範圍樓地板面積，或面積非正數。",
            stage, "自室內裝修（合格證明）申請書取得申請樓地板面積，不得由圖面推估。"))
    return problems


def check_floors(case, stage):
    floors = case.get("floors")
    if not isinstance(floors, list) or not floors:
        return [question(
            "MISSING_FLOORS", "floors",
            "缺少逐層用途與樓地板面積，第一階段主表無法成立。",
            stage, "回 /plan-intake 補齊逐層資料。")]
    problems = []
    for index, floor in enumerate(floors):
        label = floor.get("floor") or f"floors[{index}]"
        missing = []
        if not floor.get("floor"):
            missing.append("樓層名稱")
        if not is_positive_number(get_value(floor.get("area"))):
            missing.append("樓地板面積")
        if not get_value(floor.get("use_category")):
            missing.append("§12 用途分類")
        if missing:
            problems.append(question(
                "INCOMPLETE_FLOOR", f"floors[{index}]",
                f"{label} 缺少：{'、'.join(missing)}。",
                stage, "逐層向使用者確認後回填 case.json，不得以推測填充。"))
    return problems


def check_conflicts(case, stage):
    items = case.get("manual_review_items") or []
    if items:
        return [question(
            "SOURCE_CONFLICT", "manual_review_items",
            f"尚有 {len(items)} 項需人工判讀／來源矛盾未解決：{'；'.join(str(i) for i in items[:3])}"
            + ("…" if len(items) > 3 else ""),
            stage, "逐項與使用者確認採用哪一份文件與頁次；已確認者自 manual_review_items 移除。")]
    return []


def check_low_confidence(case, stage):
    """第一階段主表用到的欄位若仍為 low confidence，視為未過人工確認關卡。"""
    problems = []
    for index, floor in enumerate(case.get("floors") or []):
        label = floor.get("floor") or f"floors[{index}]"
        low = [name for name, key in (("樓地板面積", "area"), ("§12 用途分類", "use_category"),
                                      ("樓層屬性", "floor_position"))
               if get_confidence(floor.get(key)) == "low"]
        if low:
            problems.append(question(
                "LOW_CONFIDENCE_FIELD", f"floors[{index}]",
                f"{label} 的 {'、'.join(low)} 仍為 confidence: low，未通過人工確認關卡。",
                stage, "向使用者確認後將 source 改 manual、confidence 改 high。"))
    return problems


def check_first_stage_done(case, stage):
    """第二階段前置：§12 分類與複合用途判定必須已由第一階段人工定案。"""
    problems = []
    classifications = [get_value(fl.get("use_category")) for fl in case.get("floors") or []]
    classifications = [c for c in classifications if c]
    if not classifications and not case.get("_first_stage_classifications"):
        problems.append(question(
            "MISSING_FIRST_STAGE_CLASSIFICATION", "floors[].use_category",
            "缺少第一階段結構化的 §12 分類，第二階段不得由原始文件重新推定。",
            stage, "先執行 /first-stage-review 完成第一階段並人工定案 §12 分類。"))
    assessment = ((case.get("building") or {}).get("mixed_use_assessment")) or {}
    if assessment.get("is_mixed_use") is None and not assessment.get("category_candidate"):
        problems.append(question(
            "MISSING_FIRST_STAGE_JUDGMENT", "building.mixed_use_assessment",
            "缺少第一階段的建築物判定（單一用途／戊1／戊2 複合用途建築物）。",
            stage, "先執行 /first-stage-review 完成複合用途判定。"))
    elif assessment.get("source") != "manual":
        problems.append(question(
            "UNCONFIRMED_FIRST_STAGE_JUDGMENT", "building.mixed_use_assessment.source",
            "建築物判定尚未經人工確認（source 非 manual），不得作為第二階段依據。",
            stage, "於 /first-stage-review 人工確認關卡定案後回填 source: manual。"))
    return problems


def validate(case, stage):
    if stage not in STAGES:
        raise ValueError(f"stage 必須是 {STAGES} 之一，得到 {stage!r}")
    questions = []
    questions += check_permit(case, stage)
    questions += check_application(case, stage)
    questions += check_floors(case, stage)
    questions += check_low_confidence(case, stage)
    questions += check_conflicts(case, stage)
    if stage == "second":
        questions += check_first_stage_done(case, stage)
    return {
        "stage": stage,
        "case_name": case.get("case_name"),
        "ready": not questions,
        "questions": questions,
    }


def is_article24_item2_applicable(use):
    """第 24 條第 2 款：§12 第 2 款第 7 目僅限住宿型精神復健機構，一般集合住宅不適用。

    見 rules/stage_two_judgment_rules.md 第 24 條。
    """
    return "住宿型精神復健機構" in str(use or "")


def format_text(result):
    lines = [f"【受控自動化關卡】第{'一' if result['stage'] == 'first' else '二'}階段"
             f"｜案件：{result['case_name'] or '(未命名)'}"]
    if result["ready"]:
        lines.append("✅ ready: true —— 案件事實齊備，可續行交付物匯出。")
        return "\n".join(lines)
    lines.append(f"⛔ ready: false —— {len(result['questions'])} 項阻擋問題，不得輸出最終交付物。")
    for i, q in enumerate(result["questions"], 1):
        lines.append(f"\n{i}. [{q['code']}] {q['field']}\n   問題：{q['reason']}\n   處理：{q['action']}")
    lines.append("\n嚴禁以猜測、預設值或未提供的圖說補足資料；逐項與使用者確認後補齊 case.json 再重跑本關卡。")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="兩階段審查的受控自動化關卡（案件事實齊備性檢查）")
    parser.add_argument("--stage", required=True, choices=STAGES, help="first（第一階段）或 second（第二階段）")
    parser.add_argument("--case", required=True, help="case.json 路徑（或扁平事實 JSON）")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="輸出格式")
    args = parser.parse_args(argv)

    with open(args.case, encoding="utf-8") as f:
        doc = json.load(f)
    case = normalize_flat(doc) if is_flat_facts(doc) else doc

    result = validate(case, args.stage)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else format_text(result))
    return 0 if result["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())

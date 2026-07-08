#!/usr/bin/env python3
"""Fire Code Calculator for fire-review.

消防審圖規則引擎與精確計算工具（類比 ai-berkshire 的 financial_rigor.py）。
所有門檻判斷與數量計算由本工具執行，LLM 禁止心算、禁止憑記憶引用法規數值。

Zero external dependencies — Python stdlib only (decimal, json, math, argparse).
Requires Python >= 3.7.

Usage:
    python3 fire_code_calc.py check-threshold --rules rules/equipment_rules.json --case cases/xxx/case.json
    python3 fire_code_calc.py extinguisher --use-category 甲 --floor-area 450
    python3 fire_code_calc.py hydrant-coverage --area 450 --radius 25
    python3 fire_code_calc.py sprinkler --area 450 --radius 2.3
    python3 fire_code_calc.py detector --area 450 --height 3.5 --fireproof --detector-type smoke-2
    python3 fire_code_calc.py occupancy --components '[{"name":"客席","area":120,"per_sqm":3}]' --fixed-seats 40
    python3 fire_code_calc.py calc --expr '450 / 100'
    python3 fire_code_calc.py self-test
"""

import argparse
import json
import math
import re
import sys
from decimal import Decimal, Context, ROUND_HALF_EVEN

_CTX = Context(prec=28, rounding=ROUND_HALF_EVEN)

UNVERIFIED_WARNING = "⚠️ 本參數未經消防專業人員核定（verified: false），以現行法規為準，不得直接作為審查依據"


def exact(value):
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def ceil_div(numerator, denominator):
    """精確向上取整（避免浮點誤差）。"""
    n, d = exact(numerator), exact(denominator)
    q = _CTX.divide(n, d)
    i = int(q)
    return i if q == i else i + 1


def load_rules(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_rule(rules_doc, rule_id):
    for r in rules_doc["rules"]:
        if r["id"] == rule_id:
            return r
    raise KeyError(f"規則庫中找不到規則: {rule_id}")


def rule_header(rule):
    lines = [f"依據：{rule.get('legal_basis', '（無條號）')}（{rule['equipment']}）"]
    if not rule.get("verified", False):
        lines.append(UNVERIFIED_WARNING)
    return lines


def main_category(use_value):
    """'甲1' → '甲'；未知回傳原值。"""
    if use_value and use_value[0] in "甲乙丙丁戊":
        return use_value[0]
    return use_value


def floor_index(floor_label):
    """'1F' → 1, 'B1' → -1；解析失敗回傳 None。"""
    m = re.fullmatch(r"(B?)(\d+)F?", str(floor_label).strip(), re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(2))
    return -n if m.group(1) else n


def get_value(field):
    """case.json 欄位可能是 {value, confidence, source} 或裸值。"""
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


# ---------------------------------------------------------------------------
# check-threshold — 逐層逐設備門檻判斷
# ---------------------------------------------------------------------------

def cmd_check_threshold(args):
    rules_doc = load_rules(args.rules)
    with open(args.case, encoding="utf-8") as f:
        case = json.load(f)

    building = case.get("building", {})
    floors_above = building.get("floors_above", 0)
    total_area = exact(get_value(building.get("total_floor_area", 0)) or 0)
    floors = case.get("floors", [])

    print(f"# 門檻判斷：{case.get('case_name', '(未命名案件)')}")
    print(f"法規版本：{rules_doc.get('regulation_version', '未注明')}")
    print(f"地上 {floors_above} 層 / 地下 {building.get('floors_below', 0)} 層，"
          f"總樓地板面積 {total_area} ㎡")
    print()

    # 甲類樓層合計面積（撒水、排煙等 total 門檻用）
    total_area_by_cat = {}
    for fl in floors:
        cat = main_category(get_value(fl.get("use_category", "")))
        a = exact(get_value(fl.get("area", 0)) or 0)
        total_area_by_cat[cat] = total_area_by_cat.get(cat, Decimal(0)) + a

    for fl in floors:
        label = fl.get("floor", "?")
        idx = floor_index(label)
        area = exact(get_value(fl.get("area", 0)) or 0)
        cat = main_category(get_value(fl.get("use_category", "")))
        windowless = get_value(fl.get("windowless", None))
        is_basement = idx is not None and idx < 0

        print(f"## {label}（用途 {get_value(fl.get('use_category','?'))}，{area} ㎡）")

        # 滅火器 §14
        r = find_rule(rules_doc, "extinguisher-threshold")
        p = r["params"]
        verdict, why = None, ""
        if cat in p["always_required_uses"]:
            verdict, why = "應設", f"{cat}類場所一律應設"
        elif (is_basement or windowless is True) and area >= exact(p["basement_or_windowless_area_threshold"]["value"]):
            verdict, why = "應設", f"地下層/無開口樓層面積 {area} ≥ {p['basement_or_windowless_area_threshold']['value']} ㎡"
        elif cat in p["total_area_threshold_other_uses"]["applies_to"]:
            th = exact(p["total_area_threshold_other_uses"]["value"])
            if total_area >= th:
                verdict, why = "應設", f"總樓地板面積 {total_area} ≥ {th} ㎡（scope: total）"
            else:
                verdict, why = "免設", f"總樓地板面積 {total_area} < {th} ㎡"
        else:
            verdict, why = "需人工判讀", "用途類別不在示例規則涵蓋範圍"
        _emit("滅火器", r, verdict, why)

        # 室內消防栓 §15
        r = find_rule(rules_doc, "indoor-hydrant-threshold")
        p = r["params"]
        tier = p["low_rise"] if floors_above <= p["low_rise"]["max_floors"] else p["mid_rise"]
        th = exact(tier["per_floor_area_threshold"].get(cat, tier["per_floor_area_threshold"].get("other")))
        if area >= th:
            _emit("室內消防栓", r, "應設", f"本層面積 {area} ≥ {th} ㎡（scope: per_floor，{'五層以下' if tier is p['low_rise'] else '六層以上'}門檻）")
        else:
            _emit("室內消防栓", r, "免設", f"本層面積 {area} < {th} ㎡")

        # 自動撒水 §17
        r = find_rule(rules_doc, "sprinkler-threshold")
        p = r["params"]
        if idx is not None and idx >= p["high_rise_per_floor_threshold"]["min_floor_index"]:
            th = exact(p["high_rise_per_floor_threshold"]["value"])
            v = "應設" if area >= th else "免設"
            _emit("自動撒水設備", r, v, f"十一層以上樓層，本層面積 {area} vs 門檻 {th} ㎡")
        elif cat in p["low_rise_total_area_threshold"]["applies_to"]:
            th = exact(p["low_rise_total_area_threshold"]["value"])
            cat_total = total_area_by_cat.get(cat, Decimal(0))
            v = "應設" if cat_total >= th else "免設"
            _emit("自動撒水設備", r, v, f"{cat}類使用樓層合計 {cat_total} vs 門檻 {th} ㎡（scope: total）")
        else:
            _emit("自動撒水設備", r, "需人工判讀", "非甲類且非高樓層，特別規定（舞台/地下建築物等）未納入示例規則")

        # 火警自動警報 §19
        r = find_rule(rules_doc, "fire-alarm-threshold")
        p = r["params"]
        if floors_above >= p["high_rise"]["min_floors"]:
            _emit("火警自動警報設備", r, "應設", f"建築物達 {p['high_rise']['min_floors']} 層以上，{p['high_rise']['rule']}")
        elif is_basement or windowless is True:
            th = exact(p["basement_windowless_threshold"].get(cat, p["basement_windowless_threshold"]["other"]))
            v = "應設" if area >= th else "免設"
            _emit("火警自動警報設備", r, v, f"地下層/無開口樓層，本層面積 {area} vs 門檻 {th} ㎡")
        else:
            if floors_above <= p["low_rise"]["max_floors"]:
                th = exact(p["low_rise"]["per_floor_area_threshold"].get(cat, p["low_rise"]["per_floor_area_threshold"].get("other")))
            else:
                th = exact(p["mid_rise"]["per_floor_area_threshold"]["any"])
            v = "應設" if area >= th else "免設"
            _emit("火警自動警報設備", r, v, f"本層面積 {area} vs 門檻 {th} ㎡（scope: per_floor）")

        # 標示設備 §23
        r = find_rule(rules_doc, "exit-light-threshold")
        if cat in r["params"]["required_uses"]:
            _emit("出口標示燈・避難方向指示燈", r, "應設",
                  "適用用途；數量與位置依避難動線判定 → 配置需圖面逐點檢核（配置疑義）")
        else:
            _emit("出口標示燈・避難方向指示燈", r, "需人工判讀", "用途不在示例規則涵蓋範圍")

        # 緊急照明 §24
        r = find_rule(rules_doc, "emergency-light-threshold")
        _emit("緊急照明設備", r, "應設（但書免設需人工判讀）", r["params"]["exemption_note"])

        # 排煙設備 §28
        r = find_rule(rules_doc, "smoke-exhaust-threshold")
        p = r["params"]
        if cat in p["total_area_threshold"]["applies_to"]:
            th = exact(p["total_area_threshold"]["value"])
            cat_total = total_area_by_cat.get(cat, Decimal(0))
            if cat_total >= th:
                _emit("排煙設備", r, "應設", f"{cat}類合計 {cat_total} ≥ {th} ㎡；防煙區劃（每 {p['smoke_compartment_max_sqm']} ㎡）劃設需人工判讀")
            else:
                _emit("排煙設備", r, "需人工判讀", f"{cat}類合計 {cat_total} < {th} ㎡，但居室開口有效通風面積條件未檢核")
        else:
            _emit("排煙設備", r, "需人工判讀", "居室開口有效通風面積條件需大樣圖/開口計算書")

        print()

    if case.get("manual_review_items"):
        print("## 案件層級需人工判讀事項")
        for item in case["manual_review_items"]:
            print(f"- ⚪ {item}")


def _emit(name, rule, verdict, why):
    mark = {"應設": "🔴", "免設": "🟢"}.get(verdict.split("（")[0], "⚪")
    print(f"- {mark} **{name}**：{verdict}｜{rule.get('legal_basis')}｜{why}")
    if not rule.get("verified", False):
        print(f"  - {UNVERIFIED_WARNING}")


# ---------------------------------------------------------------------------
# 數量計算子命令
# ---------------------------------------------------------------------------

def cmd_extinguisher(args):
    rules_doc = load_rules(args.rules)
    rule = find_rule(rules_doc, "extinguisher-count")
    per = rule["params"]["effectiveness_area_per_unit"].get(args.use_category)
    if per is None:
        sys.exit(f"用途類別 {args.use_category} 不在規則參數中，需人工判讀")
    units = ceil_div(args.floor_area, per)
    for line in rule_header(rule):
        print(line)
    print(f"計算：ceil({args.floor_area} ㎡ ÷ {per} ㎡/效能值) = 滅火效能值 {units}")
    print(f"另需檢核：任一點至滅火器步行距離 ≤ {rule['params']['max_walking_distance_m']} m（依圖面動線，工具不判定）")


def cmd_hydrant_coverage(args):
    area = exact(args.area)
    r = exact(args.radius)
    coverage = _CTX.multiply(_CTX.multiply(Decimal(str(math.pi)), r), r)
    est = max(1, ceil_div(area, coverage))
    print(f"依據：§34（室內消防栓水平距離 {r} m）")
    print(UNVERIFIED_WARNING)
    print(f"估算：ceil({area} ㎡ ÷ (π×{r}²={coverage:.1f} ㎡)) = 最少約 {est} 支")
    print("⚠️ 此為理想圓形涵蓋的估算下限；實際數量取決於隔間與配置位置，必須依圖面對每一點檢核水平距離")


def cmd_sprinkler(args):
    area = exact(args.area)
    r = exact(args.radius)
    per_head, heads = compute_sprinkler_heads(area, r)  # 正方形配置：每頭 2r²
    print(f"依據：§46（撒水頭水平距離 {r} m，正方形配置每頭涵蓋 2×r² = {per_head} ㎡）")
    print(UNVERIFIED_WARNING)
    print(f"估算：ceil({area} ㎡ ÷ {per_head} ㎡/頭) = 最少約 {heads} 頭")
    print("⚠️ 估算下限；實際數量依隔間、樑位、配置方式而定，需依圖面檢核")


def compute_detector(rules_doc, area, height, fireproof, detector_type):
    """回傳 (band, coverage, count)；不適用時拋 ValueError。"""
    rule = find_rule(rules_doc, "detector-coverage")
    table = rule["params"]["coverage_sqm"].get(detector_type)
    if table is None:
        raise ValueError(f"探測器種類 {detector_type} 不在規則參數中")
    h = exact(height)
    band = None
    for key in table:
        m = re.fullmatch(r"h_lt_(\d+)", key)
        if m and h < exact(m.group(1)):
            band = key
            break
        m = re.fullmatch(r"h_(\d+)_to_(\d+)", key)
        if m and exact(m.group(1)) <= h < exact(m.group(2)):
            band = key
            break
    if band is None:
        raise ValueError(f"裝置高度 {h} m 超出 {detector_type} 適用範圍，需改用其他探測器種類（需人工判讀）")
    sub = table[band]
    coverage = sub.get("any") or (sub.get("fireproof") if fireproof else sub.get("other"))
    return band, coverage, ceil_div(area, coverage)


def compute_sprinkler_heads(area, radius):
    per_head = _CTX.multiply(_CTX.multiply(Decimal(2), exact(radius)), exact(radius))
    return per_head, max(1, ceil_div(area, per_head))


def cmd_detector(args):
    rules_doc = load_rules(args.rules)
    rule = find_rule(rules_doc, "detector-coverage")
    try:
        band, coverage, count = compute_detector(rules_doc, args.area, args.height,
                                                 args.fireproof, args.detector_type)
    except ValueError as e:
        sys.exit(str(e))
    h = exact(args.height)
    for line in rule_header(rule):
        print(line)
    print(f"條件：{args.detector_type}，裝置高度 {h} m（{band}），"
          f"{'耐火構造' if args.fireproof else '非耐火構造/不分構造'} → 每只有效探測面積 {coverage} ㎡")
    print(f"計算：ceil({args.area} ㎡ ÷ {coverage} ㎡/只) = {count} 只")
    print("⚠️ 以單一探測區域計；樑深 ≥ 規定值或有隔間時須分區另計（需人工判讀）")


def cmd_occupancy(args):
    components = json.loads(args.components) if args.components else []
    total = int(args.fixed_seats or 0)
    detail = []
    if args.fixed_seats:
        detail.append(f"固定席位 {args.fixed_seats} 人")
    for c in components:
        n = int(_CTX.divide(exact(c["area"]), exact(c["per_sqm"])))  # 小數捨去
        total += n
        detail.append(f"{c['name']}：{c['area']} ㎡ ÷ {c['per_sqm']} ㎡/人 = {n} 人（小數捨去）")
    print("依據：設置標準收容人員計算規定（比率以現行法規為準）")
    print(UNVERIFIED_WARNING)
    for d in detail:
        print(f"- {d}")
    print(f"收容人數合計：{total} 人")


def cmd_calc(args):
    expr = args.expr
    if not re.fullmatch(r"[0-9eE+\-*/(). %]+", expr):
        sys.exit("運算式含不允許的字元（僅允許數字與 + - * / ( ) . % e）")
    decimal_expr = re.sub(r"(\d+\.?\d*(?:[eE][+-]?\d+)?)", r"Decimal('\1')", expr)
    result = eval(decimal_expr, {"__builtins__": {}}, {"Decimal": Decimal})
    print(f"{expr} = {result}")


# ---------------------------------------------------------------------------
# run-tests — 先紅再綠：規則測試（防幻覺核心關卡）
# ---------------------------------------------------------------------------

def _dig(obj, path):
    """依 'params.effectiveness_area_per_unit.甲' 取值；缺鍵拋 KeyError。"""
    cur = obj
    for key in path.split("."):
        cur = cur[key]
    return cur


def _run_one_test(rules_doc, t):
    """回傳 (passed: bool, detail: str)。"""
    src = t.get("source", {})
    if not str(src.get("quote", "")).strip():
        return False, "測試缺少 source.quote（expected 必須逐字抄錄自法條 PDF）→ 無效測試"
    ttype = t.get("type")
    if ttype == "param-equals":
        rule = find_rule(rules_doc, t["rule_id"])
        try:
            actual = _dig(rule, t["path"])
        except KeyError:
            return False, f"規則 {t['rule_id']} 缺少路徑 {t['path']}（紅：規則尚未編碼）"
        try:
            ok = exact(actual) == exact(t["expected"])
        except Exception:
            ok = actual == t["expected"]
        return ok, f"{t['path']} = {actual}，期望 {t['expected']}（來源 p.{src.get('page','?')}）"
    if ttype == "calc-extinguisher":
        rule = find_rule(rules_doc, t["rule_id"])
        per = rule["params"]["effectiveness_area_per_unit"][t["input"]["use_category"]]
        got = ceil_div(t["input"]["floor_area"], per)
        return got == t["expected"]["effectiveness_value"], \
            f"滅火效能值 {got}，期望 {t['expected']['effectiveness_value']}"
    if ttype == "calc-detector":
        i = t["input"]
        try:
            _, coverage, count = compute_detector(rules_doc, i["area"], i["height"],
                                                  i.get("fireproof", False), i["detector_type"])
        except (ValueError, KeyError) as e:
            return False, f"計算失敗（紅）：{e}"
        return count == t["expected"]["count"], \
            f"探測器 {count} 只（每只 {coverage} ㎡），期望 {t['expected']['count']} 只"
    if ttype == "calc-sprinkler":
        i = t["input"]
        _, heads = compute_sprinkler_heads(i["area"], i["radius"])
        return heads == t["expected"]["heads"], f"撒水頭 {heads} 頭，期望 {t['expected']['heads']} 頭"
    return False, f"未知測試類型: {ttype}"


def cmd_run_tests(args):
    rules_doc = load_rules(args.rules)
    with open(args.tests, encoding="utf-8") as f:
        tests_doc = json.load(f)
    tests = tests_doc["tests"]
    red, green = [], []
    for t in tests:
        try:
            ok, detail = _run_one_test(rules_doc, t)
        except Exception as e:  # 測試本身壞掉也算紅
            ok, detail = False, f"測試執行錯誤：{e}"
        (green if ok else red).append((t["id"], detail))
        print(f"{'🟢 PASS' if ok else '🔴 FAIL'}  {t['id']}  —  {detail}")

    if args.strict:
        covered = {t.get("rule_id") for t in tests}
        for r in rules_doc["rules"]:
            if r["id"] not in covered:
                red.append((r["id"], "strict：規則無任何測試覆蓋"))
                print(f"🔴 FAIL  [coverage] {r['id']}  —  規則無任何測試覆蓋（--strict）")

    print()
    print(f"結果：🟢 {len(green)} PASS / 🔴 {len(red)} FAIL（共 {len(tests)} 個測試）")
    if red:
        print("【紅】規則庫不得交付使用。若為新規則的首次執行，這是預期的紅——"
              "接著編碼規則參數使測試轉綠；若為既有規則，表示規則與法條 PDF 抄錄值不一致，必須查原文。")
        sys.exit(1)
    print("【綠】全部測試通過。提醒：綠 ≠ 已核定，verified: false 的規則仍須專業人員核定。")


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

def cmd_self_test(args):
    rules_doc = load_rules(args.rules)
    # 規則庫結構檢查
    for r in rules_doc["rules"]:
        for field in ("id", "equipment", "category", "legal_basis", "params", "verified"):
            assert field in r, f"規則 {r.get('id','?')} 缺少欄位 {field}"
    # 計算檢查
    assert ceil_div(450, 100) == 5
    assert ceil_div(400, 100) == 4
    assert ceil_div("450", "112.5") == 4
    per_head = Decimal(2) * Decimal("2.3") * Decimal("2.3")
    assert ceil_div(450, per_head) == 43, ceil_div(450, per_head)
    assert floor_index("B1") == -1 and floor_index("12F") == 12
    assert main_category("甲5") == "甲"
    unverified = sum(1 for r in rules_doc["rules"] if not r["verified"])
    print(f"✅ self-test 通過：規則 {len(rules_doc['rules'])} 條（未核定 {unverified} 條），計算引擎正常")
    if unverified:
        print(f"⚠️ 尚有 {unverified} 條規則 verified: false，正式使用前須由消防專業人員核定")


# ---------------------------------------------------------------------------

def build_parser():
    default_rules = "rules/equipment_rules.json"
    p = argparse.ArgumentParser(description="消防審圖規則引擎與精確計算工具")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("check-threshold", help="逐層逐設備門檻判斷")
    s.add_argument("--rules", default=default_rules)
    s.add_argument("--case", required=True)
    s.set_defaults(func=cmd_check_threshold)

    s = sub.add_parser("extinguisher", help="滅火效能值需求")
    s.add_argument("--rules", default=default_rules)
    s.add_argument("--use-category", required=True, choices=["甲", "乙", "丙", "丁"])
    s.add_argument("--floor-area", required=True, type=float)
    s.set_defaults(func=cmd_extinguisher)

    s = sub.add_parser("hydrant-coverage", help="室內消防栓數量估算下限")
    s.add_argument("--area", required=True, type=float)
    s.add_argument("--radius", required=True, type=float, help="水平距離 25(第一種)/15(第二種)")
    s.set_defaults(func=cmd_hydrant_coverage)

    s = sub.add_parser("sprinkler", help="撒水頭數量估算下限")
    s.add_argument("--area", required=True, type=float)
    s.add_argument("--radius", required=True, type=float, help="水平距離 2.1/2.3/2.6")
    s.set_defaults(func=cmd_sprinkler)

    s = sub.add_parser("detector", help="火警探測器數量")
    s.add_argument("--rules", default=default_rules)
    s.add_argument("--area", required=True, type=float)
    s.add_argument("--height", required=True, type=float, help="裝置高度(m)")
    s.add_argument("--fireproof", action="store_true", help="耐火構造")
    s.add_argument("--detector-type", required=True,
                   choices=["heat-diff-1", "heat-diff-2", "smoke-1", "smoke-2"])
    s.set_defaults(func=cmd_detector)

    s = sub.add_parser("occupancy", help="收容人數計算")
    s.add_argument("--components", help='JSON: [{"name","area","per_sqm"}]')
    s.add_argument("--fixed-seats", type=int)
    s.set_defaults(func=cmd_occupancy)

    s = sub.add_parser("calc", help="精確四則運算（取代心算）")
    s.add_argument("--expr", required=True)
    s.set_defaults(func=cmd_calc)

    s = sub.add_parser("run-tests", help="先紅再綠：執行規則測試（防幻覺關卡）")
    s.add_argument("--rules", default=default_rules)
    s.add_argument("--tests", default="rules/rule_tests.json")
    s.add_argument("--strict", action="store_true", help="要求每條規則至少一個測試覆蓋")
    s.set_defaults(func=cmd_run_tests)

    s = sub.add_parser("self-test", help="規則庫與引擎自檢")
    s.add_argument("--rules", default=default_rules)
    s.set_defaults(func=cmd_self_test)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from tools.verification_sheet import cmd_apply, open_findings_by_rule, verifiable_entries


def write(path, doc):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def rules_doc():
    return {"rules": [
        {"id": "extinguisher-threshold", "equipment": "滅火器", "legal_basis": "§14",
         "params": {}, "verified": False},
        {"id": "applicability-article-13", "equipment": "適用標準判斷", "legal_basis": "§13",
         "params": {}, "verified": False},
    ]}


def article18_doc():
    return {
        "legal_basis": "§18",
        "items": [
            {"item": 1, "condition": "屋頂直昇機停機場（坪）。", "options": ["泡沫", "乾粉"], "verified": False},
            {"item": 8, "condition": "引擎試驗室……", "options": [], "verified": False},
        ],
        "table_notes": [{"no": 4, "text": "本表項目三及項目四……", "verified": False}],
        "global_constraints": [{"id": "no-co2-in-occupied-rooms", "rule": "……", "verified": False}],
    }


def sheet_doc(status="pending"):
    return {"sheet_id": "DISC-TEST", "findings": [
        {"id": "D-014-01", "status": status, "rule_id": "extinguisher-threshold",
         "target_file": "rules/equipment_rules.json", "article": "§14", "type": "適用範圍不足",
         "article_quote": "一、甲類場所、地下建築物、幼兒園。", "current_value": "always_required_uses = [\"甲\"]",
         "difference": "缺地下建築物與幼兒園", "impact": "漏判", "suggested_fix": "增列 乙12、戊3"},
    ]}


def results(rule_id, **extra):
    item = {"rule_id": rule_id, "result": "correct"}
    item.update(extra)
    return {"verified_by": "使用者本人（消防專業人員）", "verified_date": "2026-07-25", "results": [item]}


class VerifiableEntriesTest(unittest.TestCase):
    def test_rules_shaped_document_keys_on_rule_id(self):
        self.assertEqual(sorted(verifiable_entries(rules_doc())),
                         ["applicability-article-13", "extinguisher-threshold"])

    def test_table_shaped_document_keys_on_article_and_item(self):
        self.assertEqual(sorted(verifiable_entries(article18_doc())),
                         ["18-1", "18-8", "18-註4", "no-co2-in-occupied-rooms"])


class OpenFindingsTest(unittest.TestCase):
    def test_pending_findings_are_indexed_by_rule_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rule-discrepancies-20260725.json"
            write(path, sheet_doc())
            self.assertEqual(list(open_findings_by_rule(str(path))), ["extinguisher-threshold"])

    def test_resolved_findings_are_not_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rule-discrepancies-20260725.json"
            write(path, sheet_doc(status="resolved"))
            self.assertEqual(open_findings_by_rule(str(path)), {})


class ApplyTest(unittest.TestCase):
    """apply 是唯一能產生 verified: true 的路徑，且不得跳過待確認清單。"""

    def run_apply(self, tmp, doc, rule_id, sheet=None, **extra):
        rules_path = Path(tmp) / "rules.json"
        results_path = Path(tmp) / "results.json"
        write(rules_path, doc)
        write(results_path, results(rule_id, **extra))
        cmd_apply(Namespace(rules=str(rules_path), results=str(results_path), sheet=sheet))
        return json.loads(rules_path.read_text(encoding="utf-8"))

    def test_verifies_rule_without_open_discrepancy(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_apply(tmp, rules_doc(), "applicability-article-13")
            rule = verifiable_entries(out)["applicability-article-13"]
            self.assertTrue(rule["verified"])
            self.assertEqual(rule["verified_by"], "使用者本人（消防專業人員）")
            self.assertEqual(rule["verified_date"], "2026-07-25")
            self.assertTrue(rule["verification_evidence"])

    def test_refuses_rule_with_undecided_discrepancy(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "rule-discrepancies-20260725.json"
            write(sheet, sheet_doc())
            with self.assertRaises(SystemExit) as ctx:
                self.run_apply(tmp, rules_doc(), "extinguisher-threshold", sheet=str(sheet))
            self.assertIn("extinguisher-threshold", str(ctx.exception))

    def test_override_discrepancy_lets_a_reviewed_finding_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet = Path(tmp) / "rule-discrepancies-20260725.json"
            write(sheet, sheet_doc())
            out = self.run_apply(tmp, rules_doc(), "extinguisher-threshold",
                                 sheet=str(sheet), override_discrepancy=True,
                                 note="使用者裁示維持現值")
            self.assertTrue(verifiable_entries(out)["extinguisher-threshold"]["verified"])

    def test_verifies_table_item_by_article_and_item_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_apply(tmp, article18_doc(), "18-註4")
            entries = verifiable_entries(out)
            self.assertTrue(entries["18-註4"]["verified"])
            self.assertFalse(entries["18-8"]["verified"])

    def test_unknown_rule_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                self.run_apply(tmp, rules_doc(), "no-such-rule")


if __name__ == "__main__":
    unittest.main()

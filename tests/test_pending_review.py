import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from tools import pending_review as pr


def write(path, doc):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


RULE_QUOTE = "二、第二種消防栓，依下列規定設置：（一）各層任一點至消防栓接頭之水平距離在二十五公尺以下。"


def rules_doc(distance=15):
    return {"regulation_version": "測試版", "rules": [
        {"id": "indoor-hydrant-coverage", "equipment": "室內消防栓", "category": "滅火設備",
         "legal_basis": "§34",
         "params": {"type1_horizontal_distance_m": 25, "type2_horizontal_distance_m": distance},
         "verified": False},
    ]}


def rule_tests_doc():
    return {"description": "測試用", "tests": [
        {"id": "T-existing", "rule_id": "indoor-hydrant-coverage", "type": "param-equals",
         "path": "params.type1_horizontal_distance_m", "expected": 25,
         "source": {"article": "§34", "page": None, "quote": RULE_QUOTE}},
    ]}


def finding(auto_fix=True, rules_path="rules/equipment_rules.json"):
    fix = {
        "tests": [{"id": "T-hydrant-param-type2", "rule_id": "indoor-hydrant-coverage",
                   "type": "param-equals", "path": "params.type2_horizontal_distance_m",
                   "expected": 25,
                   "source": {"article": "§34", "page": None, "quote": RULE_QUOTE}}],
        "params": [{"file": rules_path, "rule_id": "indoor-hydrant-coverage",
                    "path": "params.type2_horizontal_distance_m", "value": 25}],
    }
    return {
        "id": "D-034-01", "status": "pending", "decision": None,
        "target_file": rules_path, "rule_id": "indoor-hydrant-coverage",
        "equipment": "室內消防栓", "article": "§34", "type": "錯值",
        "article_quote": RULE_QUOTE, "current_value": "type2 = 15",
        "difference": "現行條文為 25 公尺", "impact": "高估支數",
        "suggested_fix": "改為 25", "auto_fix": fix if auto_fix else None,
        "manual_steps": [] if auto_fix else ["人工調整結構"],
    }


def sheet(findings):
    return {"sheet_id": "DISC-TEST", "created_date": "2026-07-25",
            "regulation_version": "測試版", "findings": findings}


class SandboxCase(unittest.TestCase):
    """pending_review 以 repo 相對路徑運作，測試在暫存目錄內重建最小 repo。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)
        (self.root / "rules").mkdir()
        write("rules/equipment_rules.json", rules_doc())
        write(pr.TESTS_PATH, rule_tests_doc())
        self.sheet_path = Path("governance/待確認清單/rule-discrepancies-20260725.json")
        write(self.sheet_path, sheet([finding()]))
        Path("README.md").write_text("# 專案\n\n---\n\n## 一、目標與範圍\n\n內容\n", encoding="utf-8")

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def read(self, path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def decide(self, decision, note=None, fid="D-034-01"):
        pr.cmd_decide(Namespace(sheet=None, id=fid, decision=decision, note=note,
                                by="測試確認人", date="2026-07-26", results=None))

    def apply(self, **kwargs):
        args = dict(sheet=None, id=None, all=True, by="測試確認人", date="2026-07-26")
        args.update(kwargs)
        return pr.cmd_apply(Namespace(**args))


class StatusTest(SandboxCase):
    def test_open_finding_signals_exit_code_two(self):
        self.assertEqual(pr.cmd_status(Namespace(sheet=None)), pr.EXIT_PENDING)

    def test_no_sheet_is_clean(self):
        self.sheet_path.unlink()
        self.assertEqual(pr.cmd_status(Namespace(sheet=None)), pr.EXIT_OK)


class DecideTest(SandboxCase):
    def test_records_decision_with_attribution(self):
        self.decide("採納更正")
        found = self.read(self.sheet_path)["findings"][0]
        self.assertEqual(found["decision"], "採納更正")
        self.assertEqual(found["decided_by"], "測試確認人")
        self.assertEqual(found["decided_date"], "2026-07-26")

    def test_other_correction_requires_a_note(self):
        with self.assertRaises(SystemExit):
            self.decide("另有更正")

    def test_unknown_decision_is_rejected(self):
        with self.assertRaises(SystemExit):
            pr.cmd_decide(Namespace(sheet=None, id="D-034-01", decision="隨便", note=None,
                                    by=None, date=None, results=None))


class ApplyTest(SandboxCase):
    def test_adopting_a_fix_runs_red_green_and_writes_the_parameter(self):
        self.decide("採納更正")
        self.apply()
        rules = self.read("rules/equipment_rules.json")
        self.assertEqual(rules["rules"][0]["params"]["type2_horizontal_distance_m"], 25)
        patched = self.read(pr.TESTS_PATH)["tests"]
        self.assertIn("T-hydrant-param-type2", [t["id"] for t in patched])

    def test_resolved_finding_triggers_verified_writeback(self):
        self.decide("採納更正")
        self.apply()
        rules = self.read("rules/equipment_rules.json")
        self.assertTrue(rules["rules"][0]["verified"])
        self.assertEqual(rules["rules"][0]["verified_by"], "測試確認人")
        self.assertTrue(os.path.exists("governance/核定紀錄/results-20260726-pending-review.json"))

    def test_keeping_current_value_resolves_without_touching_parameters(self):
        self.decide("維持現值", note="現值正確")
        self.apply()
        rules = self.read("rules/equipment_rules.json")
        self.assertEqual(rules["rules"][0]["params"]["type2_horizontal_distance_m"], 15)
        self.assertTrue(rules["rules"][0]["verified"])

    def test_non_discriminating_test_aborts_and_rolls_back(self):
        """參數已經是期望值時測試不會轉紅——這種無鑑別力的修正必須整批回滾。"""
        write("rules/equipment_rules.json", rules_doc(distance=25))
        self.decide("採納更正")
        with self.assertRaises(SystemExit) as ctx:
            self.apply()
        self.assertIn("沒有轉紅", str(ctx.exception))
        self.assertNotIn("T-hydrant-param-type2",
                         [t["id"] for t in self.read(pr.TESTS_PATH)["tests"]])
        self.assertEqual(self.read(self.sheet_path)["findings"][0]["status"], "pending")

    def test_finding_without_auto_fix_is_skipped_not_guessed(self):
        write(self.sheet_path, sheet([finding(auto_fix=False)]))
        self.decide("採納更正")
        self.apply()
        rules = self.read("rules/equipment_rules.json")
        self.assertEqual(rules["rules"][0]["params"]["type2_horizontal_distance_m"], 15)
        self.assertFalse(rules["rules"][0]["verified"])
        self.assertEqual(self.read(self.sheet_path)["findings"][0]["status"], "pending")

    def test_undecided_findings_are_not_applied(self):
        self.assertEqual(self.apply(), pr.EXIT_PENDING)
        self.assertEqual(self.read("rules/equipment_rules.json")["rules"][0]
                         ["params"]["type2_horizontal_distance_m"], 15)


class RenderTest(SandboxCase):
    def test_open_findings_produce_doc_and_readme_block(self):
        pr.cmd_render(Namespace(sheet=None))
        doc = Path(pr.DOC_PATH).read_text(encoding="utf-8")
        self.assertIn("D-034-01", doc)
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn(pr.BEGIN_MARK, readme)
        self.assertIn("1 則待確認事項", readme)

    def test_resolving_everything_removes_doc_and_archives_sheet(self):
        self.decide("採納更正")
        self.apply()
        self.assertFalse(os.path.exists(pr.DOC_PATH))
        self.assertFalse(self.sheet_path.exists())
        self.assertTrue(os.path.exists(
            os.path.join(pr.ARCHIVE_DIR, self.sheet_path.name)))
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("目前沒有待確認事項", readme)

    def test_readme_block_is_replaced_not_duplicated(self):
        pr.cmd_render(Namespace(sheet=None))
        pr.cmd_render(Namespace(sheet=None))
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertEqual(readme.count(pr.BEGIN_MARK), 1)
        self.assertEqual(readme.count(pr.END_MARK), 1)


class DigSetTest(unittest.TestCase):
    def test_creates_nested_keys(self):
        node = {}
        pr.dig_set(node, "params.low_rise.threshold.甲1", 300)
        self.assertEqual(node["params"]["low_rise"]["threshold"]["甲1"], 300)

    def test_removes_keys_and_list_items(self):
        node = {"params": {"a": 1}, "items": [{"item": 1}, {"item": 2}]}
        pr.dig_set(node, "params.a", None, remove=True)
        pr.dig_set(node, "items.0", None, remove=True)
        self.assertEqual(node["params"], {})
        self.assertEqual(node["items"], [{"item": 2}])


if __name__ == "__main__":
    unittest.main()

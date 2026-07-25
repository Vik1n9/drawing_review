import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.case_facts_gate import (
    is_article24_item2_applicable,
    main,
    normalize_flat,
    validate,
)


def ready_case():
    return {
        "case_name": "測試案",
        "use_permit": {"permit_no": {"value": "測使字第001號", "confidence": "high", "source": "manual"}},
        "interior_renovation": {
            "floors": {"value": ["3F"], "confidence": "high", "source": "manual"},
            "area": {"value": 350, "confidence": "high", "source": "manual"},
        },
        "floors": [{
            "floor": "3F",
            "area": {"value": 350, "confidence": "high", "source": "manual"},
            "use_category": {"value": "乙7", "legal_basis": "§12 第2款第7目",
                             "confidence": "high", "source": "manual"},
            "floor_position": {"value": "ordinary", "confidence": "high", "source": "manual"},
        }],
        "building": {"mixed_use_assessment": {"is_mixed_use": False, "category_candidate": None,
                                              "confidence": "high", "source": "manual"}},
        "manual_review_items": [],
    }


class CaseFactsGateTest(unittest.TestCase):
    def codes(self, result):
        return [q["code"] for q in result["questions"]]

    def test_empty_case_reports_every_missing_fact(self):
        result = validate({"floors": []}, "first")
        self.assertFalse(result["ready"])
        self.assertEqual(
            self.codes(result),
            ["MISSING_PERMIT", "MISSING_APPLICATION_FLOOR", "MISSING_APPLICATION_AREA", "MISSING_FLOORS"],
        )

    def test_complete_case_passes_first_stage(self):
        result = validate(ready_case(), "first")
        self.assertTrue(result["ready"], result["questions"])

    def test_second_stage_requires_first_stage_judgment(self):
        case = ready_case()
        case["building"] = {}
        result = validate(case, "second")
        self.assertFalse(result["ready"])
        self.assertIn("MISSING_FIRST_STAGE_JUDGMENT", self.codes(result))

    def test_second_stage_rejects_unconfirmed_judgment(self):
        case = ready_case()
        case["building"]["mixed_use_assessment"]["source"] = "derived"
        result = validate(case, "second")
        self.assertFalse(result["ready"])
        self.assertIn("UNCONFIRMED_FIRST_STAGE_JUDGMENT", self.codes(result))

    def test_low_confidence_field_blocks_export(self):
        case = ready_case()
        case["floors"][0]["area"]["confidence"] = "low"
        result = validate(case, "first")
        self.assertFalse(result["ready"])
        self.assertIn("LOW_CONFIDENCE_FIELD", self.codes(result))

    def test_unresolved_manual_review_items_block_export(self):
        case = ready_case()
        case["manual_review_items"] = ["地下層是否為無開口樓層需依開口計算確認"]
        result = validate(case, "first")
        self.assertFalse(result["ready"])
        self.assertIn("SOURCE_CONFLICT", self.codes(result))

    def test_zero_and_negative_area_are_not_accepted(self):
        for bad in (0, -5, None, "350"):
            case = ready_case()
            case["floors"][0]["area"]["value"] = bad
            result = validate(case, "first")
            self.assertFalse(result["ready"], f"area={bad!r} 不應通過")
            self.assertIn("INCOMPLETE_FLOOR", self.codes(result))

    def test_article24_item2_limited_to_psychiatric_rehab_residence(self):
        self.assertFalse(is_article24_item2_applicable("集合住宅"))
        self.assertTrue(is_article24_item2_applicable("住宿型精神復健機構"))

    def test_flat_facts_format_is_accepted(self):
        flat = {
            "caseName": "範例案件",
            "permit": {"number": "(115)測使字第001號"},
            "application": {"floor": "地上001層", "area": 120},
            "floors": [{"name": "地上001層", "use": "集合住宅", "area": 120, "source": "使用執照第4頁"}],
            "firstStage": {"classifications": ["第12條第2款第7目（乙類第7目）"], "judgment": "單一用途建築物"},
            "conflicts": [],
        }
        result = validate(normalize_flat(flat), "second")
        self.assertTrue(result["ready"], result["questions"])

    def test_cli_exit_code_is_2_when_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            path.write_text(json.dumps({"floors": []}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--stage", "first", "--case", str(path)]), 2)

            path.write_text(json.dumps(ready_case()), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(["--stage", "first", "--case", str(path), "--format", "json"]), 0)
            self.assertTrue(json.loads(out.getvalue())["ready"])


if __name__ == "__main__":
    unittest.main()

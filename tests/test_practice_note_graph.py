import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.practice_note_graph import (
    GRAPH_PATH,
    LAYER,
    check,
    merge,
    node_id_for,
    plan,
    validate_extraction,
)

PREFIX = "rules_core_1各類場所消防安全設備設置標準"

NOTE = {
    "id": "PN-20260725-001",
    "ref_article": "19",
    "ref_rule_ids": ["fire-alarm-threshold"],
    "scenario": {"summary": "挑空區超過 12 公尺且該區無常駐人員",
                 "conditions": {"space_type": "挑空區", "ceiling_height_gt_m": 12}},
    "judgment": {"equipment": "火警自動警報設備", "decision": "exempt_with_alternatives",
                 "detail": "得免設，惟需增設紅外線火焰探測器",
                 "effect": {"remove": ["探測器"], "add": ["紅外線火焰探測器"]}},
    "source_case": "Case_20260725",
    "status": "active",
    "created": "2026-07-25T10:00:00+08:00",
}


def base_graph():
    return {
        "directed": True,
        "graph": {},
        "nodes": [
            {"id": f"{PREFIX}_第19條", "label": "第19條", "file_type": "document"},
            {"id": f"{PREFIX}_火警自動警報設備", "label": "火警自動警報設備", "file_type": "concept"},
        ],
        "links": [],
    }


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def sha_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_repo(tmp, note=NOTE, with_graph=True):
    root = Path(tmp)
    note_path = root / "practice_notes" / "active" / f"{note['id']}.json"
    write(note_path, note)
    if with_graph:
        write(root / GRAPH_PATH, base_graph())
    return root, note_path


def extraction_for(note_path, note_id="PN-20260725-001", **overrides):
    doc = {
        "schema_version": 1,
        "note_id": note_id,
        "note_sha256": sha_of(note_path),
        "extracted_by": "test-llm",
        "extracted_at": "2026-07-25T11:00:00+08:00",
        "summary": "挑空區逾 12 公尺且無常駐人員時得以火焰式探測器替代",
        "concepts": [{"label": "挑空區", "kind": "scenario_condition",
                      "rationale": "scenario.summary 明示挑空區"}],
        "edges": [
            {"target": "第19條", "relation": "supplements", "rationale": "ref_article 為 §19"},
            {"target": "挑空區", "relation": "applies_when", "rationale": "conditions.space_type"},
        ],
    }
    doc.update(overrides)
    return doc


class PlanTest(unittest.TestCase):
    def test_missing_extraction_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            result = plan(root)
            self.assertEqual(result["active"], 1)
            self.assertEqual([p["reason"] for p in result["pending"]], ["missing"])

    def test_ready_when_extraction_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            result = plan(root)
            self.assertEqual(result["pending"], [])
            self.assertEqual(result["ready"], ["PN-20260725-001"])

    def test_note_edit_invalidates_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            edited = dict(NOTE)
            edited["judgment"] = dict(NOTE["judgment"], detail="改過的判讀")
            write(note_path, edited)
            self.assertEqual([p["reason"] for p in plan(root)["pending"]], ["stale"])


class ValidateExtractionTest(unittest.TestCase):
    def test_rejects_unresolvable_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            doc = extraction_for(note_path)
            doc["edges"].append({"target": "第999條", "relation": "supplements", "rationale": "x"})
            problems = validate_extraction(doc, NOTE, sha_of(note_path), {"第19條", "火警自動警報設備"})
            self.assertTrue(any("第999條" in p for p in problems), problems)

    def test_rejects_template_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            doc = extraction_for(note_path, extracted_by="（填語意抽取者：模型或 agent 名稱）")
            problems = validate_extraction(doc, NOTE, sha_of(note_path), {"第19條"})
            self.assertTrue(any("extracted_by" in p for p in problems), problems)

    def test_rejects_empty_semantic_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            doc = extraction_for(note_path, concepts=[], edges=[])
            problems = validate_extraction(doc, NOTE, sha_of(note_path), {"第19條"})
            self.assertTrue(any("語意抽取沒有產出" in p for p in problems), problems)

    def test_rejects_unknown_relation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            doc = extraction_for(note_path)
            doc["edges"][0]["relation"] = "免除"
            problems = validate_extraction(doc, NOTE, sha_of(note_path), {"第19條", "挑空區"})
            self.assertTrue(any("relation" in p for p in problems), problems)


class MergeTest(unittest.TestCase):
    def merged_graph(self, root):
        return json.loads((Path(root) / GRAPH_PATH).read_text(encoding="utf-8"))

    def test_refuses_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            result = merge(root)
            self.assertFalse(result["ok"])
            self.assertEqual(self.merged_graph(root)["nodes"], base_graph()["nodes"])

    def test_merges_note_and_semantic_concept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            self.assertTrue(merge(root)["ok"])
            graph = self.merged_graph(root)
            note_node = next(n for n in graph["nodes"] if n.get("note_id") == "PN-20260725-001")
            self.assertEqual(note_node["layer"], LAYER)
            self.assertEqual(note_node["ref_article"], "第19條")
            self.assertEqual(note_node["note_sha256"], sha_of(note_path))
            self.assertIn("挑空區", [n["label"] for n in graph["nodes"]])

            edges = [l for l in graph["links"] if l["source"] == node_id_for("PN-20260725-001")]
            by_relation = {l["relation"]: l for l in edges}
            # 錨點邊來自結構化欄位，語意邊來自 LLM 抽取
            self.assertEqual(by_relation["supplements"]["target"], f"{PREFIX}_第19條")
            self.assertEqual(by_relation["concerns_equipment"]["confidence"], "MECHANICAL")
            self.assertEqual(by_relation["applies_when"]["confidence"], "EXTRACTED")

    def test_reuses_existing_node_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            doc = extraction_for(note_path)
            doc["concepts"] = [{"label": "火警自動警報設備", "kind": "equipment",
                                "rationale": "judgment.equipment"}]
            doc["edges"] = [{"target": "火警自動警報設備", "relation": "concerns_equipment",
                             "rationale": "judgment.equipment"}]
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json", doc)
            merge(root)
            labels = [n["label"] for n in self.merged_graph(root)["nodes"]]
            self.assertEqual(labels.count("火警自動警報設備"), 1)

    def test_merge_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            merge(root)
            first = self.merged_graph(root)
            merge(root)
            self.assertEqual(self.merged_graph(root), first)

    def test_deactivated_note_is_removed_from_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            merge(root)
            write(note_path, dict(NOTE, status="superseded"))
            self.assertTrue(merge(root)["ok"])
            self.assertEqual([n for n in self.merged_graph(root)["nodes"]
                              if n.get("layer") == LAYER], [])


class CheckTest(unittest.TestCase):
    def test_uncovered_when_note_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            result = check(root)
            self.assertEqual(result["state"], "uncovered")
            self.assertEqual(result["missing"], ["PN-20260725-001"])

    def test_covered_after_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            merge(root)
            self.assertEqual(check(root)["state"], "covered")

    def test_stale_when_note_edited_after_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            merge(root)
            write(note_path, dict(NOTE, source_case="Case_other"))
            result = check(root)
            self.assertEqual(result["state"], "uncovered")
            self.assertEqual(result["stale"], ["PN-20260725-001"])

    def test_graph_rebuild_wipes_layer_and_is_detected(self):
        """/graphify rules 重建會覆寫 graph.json——必須偵測得到註解層被沖掉。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / "PN-20260725-001.json",
                  extraction_for(note_path))
            merge(root)
            write(root / GRAPH_PATH, base_graph())  # 模擬重建
            self.assertEqual(check(root)["missing"], ["PN-20260725-001"])

    def test_no_notes_is_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / GRAPH_PATH, base_graph())
            self.assertEqual(check(root)["state"], "covered")


if __name__ == "__main__":
    unittest.main()

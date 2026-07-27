import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.graph_labels import LabelIndex
from tools.practice_note_graph import (
    DIGEST_LEGACY,
    DIGEST_OK,
    DIGEST_STALE,
    EXTRACTION_SCHEMA_VERSION,
    LAYER,
    active_notes,
    build_layer,
    digest_state,
    migrate,
    node_id_for,
    plan,
    semantic_digest,
    unknown_fields,
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


def regulation_nodes():
    return [
        {"id": f"{PREFIX}_第19條", "label": "第19條", "file_type": "document"},
        {"id": f"{PREFIX}_火警自動警報設備", "label": "火警自動警報設備", "file_type": "concept"},
    ]


def reg_index():
    return LabelIndex(regulation_nodes())


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def make_repo(tmp, note=NOTE):
    root = Path(tmp)
    note_path = root / "practice_notes" / "active" / f"{note['id']}.json"
    write(note_path, note)
    return root, note_path


def extraction_for(note, **overrides):
    doc = {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "note_id": note["id"],
        "note_semantic_sha256": semantic_digest(note),
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


def write_extraction(root, note, **overrides):
    write(root / "practice_notes" / "graph_extractions" / f"{note['id']}.json",
          extraction_for(note, **overrides))


class SemanticDigestTest(unittest.TestCase):
    """卡點 2 的正回歸：治理欄位變動不得讓訓練成果進不了圖譜。"""

    def test_governance_fields_do_not_change_the_digest(self):
        before = semantic_digest(NOTE)
        for field, value in (("approved", "2026-07-26 使用者確認"),
                             ("governance_log", "GOV-2026-001"),
                             ("created", "2099-01-01T00:00:00+08:00"),
                             ("notice", "任何警語")):
            self.assertEqual(before, semantic_digest({**NOTE, field: value}), field)

    def test_semantic_fields_change_the_digest(self):
        before = semantic_digest(NOTE)
        changed = {**NOTE, "judgment": {**NOTE["judgment"], "detail": "改過的判讀"}}
        self.assertNotEqual(before, semantic_digest(changed))

    def test_article_writing_style_does_not_change_the_digest(self):
        """ref_article 寫 19／§19／第19條 是同一件事，不該逼人重抽。"""
        digests = {semantic_digest({**NOTE, "ref_article": form})
                   for form in ("19", "§19", "第19條", "第 19 條")}
        self.assertEqual(1, len(digests))

    def test_rule_id_order_does_not_change_the_digest(self):
        a = semantic_digest({**NOTE, "ref_rule_ids": ["a", "b"]})
        b = semantic_digest({**NOTE, "ref_rule_ids": ["b", "a"]})
        self.assertEqual(a, b)

    def test_unknown_field_is_conservatively_included(self):
        """白名單制的破口：新欄位若預設被排除，語意變了也不會判過期。"""
        note = {**NOTE, "新增的判讀依據": "某個會影響結論的東西"}
        self.assertEqual(["新增的判讀依據"], unknown_fields(note))
        self.assertNotEqual(semantic_digest(NOTE), semantic_digest(note))
        self.assertNotEqual(semantic_digest(note),
                            semantic_digest({**note, "新增的判讀依據": "換了內容"}))


class DigestStateTest(unittest.TestCase):
    def test_v2_matches_semantic_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            ref = active_notes(root)[0]
            self.assertEqual(DIGEST_OK, digest_state(extraction_for(NOTE), ref))

    def test_v1_with_matching_byte_sha_is_still_usable(self):
        """位元組都沒變，語意當然沒變——不該為了升版而重跑語意抽取。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            ref = active_notes(root)[0]
            legacy = {"schema_version": 1, "note_id": NOTE["id"],
                      "note_sha256": hashlib.sha256(note_path.read_bytes()).hexdigest()}
            self.assertEqual(DIGEST_LEGACY, digest_state(legacy, ref))

    def test_v1_with_stale_byte_sha_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            ref = active_notes(root)[0]
            legacy = {"schema_version": 1, "note_id": NOTE["id"], "note_sha256": "0" * 64}
            self.assertEqual(DIGEST_STALE, digest_state(legacy, ref))


class PlanTest(unittest.TestCase):
    def test_missing_extraction_is_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            result = plan(root, reg_index())
            self.assertEqual(1, result["active"])
            self.assertEqual(["missing"], [p["reason"] for p in result["pending"]])

    def test_ready_when_extraction_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write_extraction(root, NOTE)
            result = plan(root, reg_index())
            self.assertEqual([], result["pending"])
            self.assertEqual(["PN-20260725-001"], result["ready"])

    def test_governance_edit_keeps_the_note_ready(self):
        """卡點 2：抽取完成後補填 approved，訓練成果必須照樣進得了圖譜。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write_extraction(root, NOTE)
            write(note_path, {**NOTE, "approved": "2026-07-26 使用者確認",
                              "governance_log": "GOV-1"})
            self.assertEqual([], plan(root, reg_index())["pending"])

    def test_semantic_edit_invalidates_extraction(self):
        """底線 3 不得因為修卡點 2 而放鬆：真正的語意變更仍須重抽。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write_extraction(root, NOTE)
            write(note_path, {**NOTE, "judgment": {**NOTE["judgment"], "detail": "改過的判讀"}})
            self.assertEqual(["stale"], [p["reason"] for p in plan(root, reg_index())["pending"]])

    def test_unknown_fields_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp, {**NOTE, "來路不明的欄位": "x"})
            write_extraction(root, {**NOTE, "來路不明的欄位": "x"})
            self.assertEqual([{"note_id": NOTE["id"], "fields": ["來路不明的欄位"]}],
                             plan(root, reg_index())["unknown_fields"])


class ValidateExtractionTest(unittest.TestCase):
    def ref(self, root):
        return active_notes(root)[0]

    def test_rejects_unresolvable_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            doc = extraction_for(NOTE)
            doc["edges"].append({"target": "第999條", "relation": "supplements", "rationale": "x"})
            problems = validate_extraction(doc, self.ref(root), reg_index())
            self.assertTrue(any("第999條" in p for p in problems), problems)

    def test_accepts_alternative_article_writings(self):
        """卡點 3(a)：寫 §19 而非 第19條 不該讓整批建層卡住。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            for form in ("§19", "第 19 條", "19", "第十九條"):
                doc = extraction_for(NOTE)
                doc["edges"][0]["target"] = form
                self.assertEqual([], validate_extraction(doc, self.ref(root), reg_index()), form)

    def test_skips_target_checks_when_regulation_graph_is_absent(self):
        """法規圖譜不在時無從分辨打錯字與圖譜沒建，不該擋住訓練圖譜。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            doc = extraction_for(NOTE)
            doc["edges"].append({"target": "第999條", "relation": "supplements", "rationale": "x"})
            self.assertEqual([], validate_extraction(doc, self.ref(root), LabelIndex()))

    def test_rejects_template_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            doc = extraction_for(NOTE, extracted_by="（填語意抽取者：模型或 agent 名稱）")
            problems = validate_extraction(doc, self.ref(root), reg_index())
            self.assertTrue(any("extracted_by" in p for p in problems), problems)

    def test_rejects_empty_semantic_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            doc = extraction_for(NOTE, concepts=[], edges=[])
            problems = validate_extraction(doc, self.ref(root), reg_index())
            self.assertTrue(any("語意抽取沒有產出" in p for p in problems), problems)

    def test_rejects_unknown_relation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            doc = extraction_for(NOTE)
            doc["edges"][0]["relation"] = "免除"
            problems = validate_extraction(doc, self.ref(root), reg_index())
            self.assertTrue(any("relation" in p for p in problems), problems)


class BuildLayerTest(unittest.TestCase):
    def build(self, root, index=None):
        index = index if index is not None else reg_index()
        return build_layer(root, active_notes(root), index)

    def test_builds_note_and_semantic_concept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write_extraction(root, NOTE)
            nodes, links, unresolved = self.build(root)
            self.assertEqual([], unresolved)
            note_node = next(n for n in nodes if n.get("note_id") == NOTE["id"])
            self.assertEqual(LAYER, note_node["layer"])
            self.assertEqual("第19條", note_node["ref_article"])
            self.assertEqual(semantic_digest(NOTE), note_node["note_semantic_sha256"])
            self.assertIn("挑空區", [n["label"] for n in nodes])

            by_relation = {l["relation"]: l for l in links
                           if l["source"] == node_id_for(NOTE["id"])}
            self.assertEqual(f"{PREFIX}_第19條", by_relation["supplements"]["target"])
            self.assertEqual("MECHANICAL", by_relation["concerns_equipment"]["confidence"])
            self.assertEqual("EXTRACTED", by_relation["applies_when"]["confidence"])

    def test_cross_graph_edges_carry_the_label_as_the_durable_key(self):
        """法規圖譜重建後 id 會變，label 不會——訓練成果靠 label 活下來。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write_extraction(root, NOTE)
            _, links, _ = self.build(root)
            edge = next(l for l in links if l["relation"] == "supplements")
            self.assertEqual("第19條", edge["target_label"])
            self.assertEqual("regulation", edge["target_graph"])
            self.assertFalse(edge["dangling"])

    def test_unresolvable_target_is_kept_as_dangling_not_dropped(self):
        """卡點 3(c)：靜默丟邊不得復活——訓練成果一律保留，只標記待修。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write_extraction(root, NOTE)
            nodes, links, unresolved = self.build(root, LabelIndex())
            self.assertTrue(unresolved)
            supplements = next(l for l in links if l["relation"] == "supplements")
            self.assertTrue(supplements["dangling"])
            self.assertIsNone(supplements["target"])
            self.assertEqual("第19條", supplements["target_label"])
            # 節點本身照樣建出來，訓練成果沒有消失
            self.assertTrue(any(n.get("note_id") == NOTE["id"] for n in nodes))

    def test_reuses_existing_node_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write_extraction(root, NOTE, concepts=[
                {"label": "火警自動警報設備", "kind": "equipment", "rationale": "judgment.equipment"}])
            nodes, _, _ = self.build(root)
            self.assertNotIn("火警自動警報設備", [n["label"] for n in nodes])

    def test_validate_and_build_agree_on_every_writing(self):
        """驗證判過的 target，建層一定建得出邊——兩邊必須用同一個解析器。"""
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            for form in ("第19條", "§19", "第 19 條", "19", "第十九條"):
                doc = extraction_for(NOTE)
                doc["edges"][0]["target"] = form
                write(root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json", doc)
                validated = not validate_extraction(doc, active_notes(root)[0], reg_index())
                _, links, unresolved = self.build(root)
                built = not unresolved
                self.assertEqual(validated, built, form)


class MigrateTest(unittest.TestCase):
    def test_v1_with_matching_bytes_upgrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json",
                  {"schema_version": 1, "note_id": NOTE["id"],
                   "note_sha256": hashlib.sha256(note_path.read_bytes()).hexdigest()})
            result = migrate(root, dry_run=False)
            self.assertEqual([{"note_id": NOTE["id"], "action": "upgraded", "evidence": "bytes"}],
                             result)
            doc = json.loads((root / "practice_notes" / "graph_extractions"
                              / f"{NOTE['id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(2, doc["schema_version"])
            self.assertEqual(semantic_digest(NOTE), doc["note_semantic_sha256"])

    def test_git_history_proves_a_governance_only_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            for args in (["init", "-q"], ["config", "user.email", "t@t"],
                         ["config", "user.name", "t"], ["add", "-A"],
                         ["commit", "-qm", "first"]):
                subprocess.run(["git", "-C", str(root)] + args, check=True,
                               capture_output=True)
            original_sha = hashlib.sha256(note_path.read_bytes()).hexdigest()
            write(root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json",
                  {"schema_version": 1, "note_id": NOTE["id"], "note_sha256": original_sha})
            # 只改治理欄位——位元組變了，語意沒變
            write(note_path, {**NOTE, "approved": "2026-07-26 使用者確認"})
            self.assertEqual([{"note_id": NOTE["id"], "action": "upgraded", "evidence": "git"}],
                             migrate(root, dry_run=True))

    def test_without_evidence_it_refuses_to_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = make_repo(tmp)
            write(root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json",
                  {"schema_version": 1, "note_id": NOTE["id"], "note_sha256": "0" * 64})
            result = migrate(root, dry_run=True)
            self.assertEqual("needs_reextraction", result[0]["action"])

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, note_path = make_repo(tmp)
            path = root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json"
            write(path, {"schema_version": 1, "note_id": NOTE["id"],
                         "note_sha256": hashlib.sha256(note_path.read_bytes()).hexdigest()})
            migrate(root, dry_run=True)
            self.assertEqual(1, json.loads(path.read_text(encoding="utf-8"))["schema_version"])


if __name__ == "__main__":
    unittest.main()

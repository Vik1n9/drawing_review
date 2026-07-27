import json
import tempfile
import unittest
from pathlib import Path

from tools.graph_labels import LabelIndex
from tools.practice_note_graph import semantic_digest
from tools.training_graph_build import (CORRECTIONS_PATH, JUDGMENT_PATH, LAYER_CORRECTION,
                                        LAYER_JUDGMENT, TRAINING_GRAPH_PATH, build, check,
                                        correction_entries, judgment_entries, migrate_from_legacy,
                                        parse_corrections, parse_judgment_rules,
                                        regulation_index)

REPO = Path(__file__).resolve().parent.parent

CORRECTIONS_MD = """# 審圖修正筆記

## 已確認的修正（新→舊）

### 2026-07-25 — 第21條冠首不構成額外要件

- Status: Active
- Last confirmed: 2026-07-25
- Error: 將第 21 條冠首讀成額外前提要件。
- Correction: 符合第 21 條所列各款其中一款即應設置。第 22 條連動。
- Scope: 所有第二階段之第 21 條判斷。
- Evidence: 使用者於 2026-07-25 明確確認。
- Notes: 取代先前的暫定狀態。

### 2026-07-12 — 舊的認定

- Status: **Superseded**
- Last confirmed: 2026-07-12
- Error: 舊寫法。
- Correction: 已由新條目取代。
- Scope: 無。
- Evidence: 使用者確認。
"""

JUDGMENT_MD = """# 第二階段判斷規則

## 通案認定

- **地下建築物**：如地下街。一般地上建築物附設地下層者不是地下建築物。
- **§24 第 4 款（採光）**：未來案件預設逕行勾選。

## 逐條判斷差異

### §15 室內消防栓設備

- **第 2 款**：判斷六層以上看的是建築物總層數。

### §28 排煙設備

- 屬樓層層級。
"""

NOTE = {
    "id": "PN-20260725-001", "ref_article": "19", "ref_rule_ids": ["r1"],
    "scenario": {"summary": "挑空區", "conditions": {"space_type": "挑空區"}},
    "judgment": {"equipment": "火警自動警報設備", "decision": "exempt", "detail": "得免設"},
    "source_case": "Case", "status": "active", "created": "2026-07-25T10:00:00+08:00",
}


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def make_repo(tmp, with_notes=False, with_regulation=True):
    root = Path(tmp)
    (root / "rules").mkdir(parents=True)
    (root / CORRECTIONS_PATH).write_text(CORRECTIONS_MD, encoding="utf-8")
    (root / JUDGMENT_PATH).write_text(JUDGMENT_MD, encoding="utf-8")
    if with_regulation:
        write(root / "graphify-out" / "graph.json", {
            "nodes": [{"id": "a19", "label": "第19條", "file_type": "document"},
                      {"id": "a21", "label": "第21條", "file_type": "document"},
                      {"id": "a22", "label": "第22條", "file_type": "document"},
                      {"id": "a24", "label": "第24條", "file_type": "document"},
                      {"id": "a15", "label": "第15條", "file_type": "document"},
                      {"id": "a28", "label": "第28條", "file_type": "document"},
                      {"id": "e1", "label": "火警自動警報設備", "file_type": "concept"}],
            "links": []})
    if with_notes:
        write(root / "practice_notes" / "active" / f"{NOTE['id']}.json", NOTE)
        write(root / "practice_notes" / "graph_extractions" / f"{NOTE['id']}.json", {
            "schema_version": 2, "note_id": NOTE["id"],
            "note_semantic_sha256": semantic_digest(NOTE),
            "extracted_by": "test", "extracted_at": "2026-07-25T11:00:00+08:00",
            "summary": "挑空區情境",
            "concepts": [{"label": "挑空區", "kind": "scenario_condition", "rationale": "x"}],
            "edges": [{"target": "§19", "relation": "supplements", "rationale": "ref_article"}]})
    return root


class CorrectionParseTest(unittest.TestCase):
    def test_parses_heading_and_all_fields(self):
        entries = parse_corrections(CORRECTIONS_MD)
        self.assertEqual(2, len(entries))
        first = entries[0]
        self.assertEqual("2026-07-25", first["date"])
        self.assertEqual("第21條冠首不構成額外要件", first["title"])
        self.assertEqual("Active", first["status"])
        self.assertIn("符合第 21 條", first["fields"]["Correction"])

    def test_superseded_status_is_recognised_through_bold_markup(self):
        """既有筆記永遠不刪，只改 Status——圖譜要能表達這件事。"""
        self.assertEqual("Superseded", parse_corrections(CORRECTIONS_MD)[1]["status"])

    def test_multiline_field_values_are_joined(self):
        md = CORRECTIONS_MD.replace("- Scope: 所有第二階段之第 21 條判斷。",
                                    "- Scope: 所有第二階段\n  之第 21 條判斷。")
        self.assertEqual("所有第二階段 之第 21 條判斷。",
                         parse_corrections(md)[0]["fields"]["Scope"])

    def test_governance_only_edit_does_not_change_the_digest(self):
        """改 Last confirmed 不是語意變更，不該讓圖譜判過期。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            before = correction_entries(root)[0]["semantic_sha256"]
            (root / CORRECTIONS_PATH).write_text(
                CORRECTIONS_MD.replace("- Last confirmed: 2026-07-25",
                                       "- Last confirmed: 2026-08-01"), encoding="utf-8")
            self.assertEqual(before, correction_entries(root)[0]["semantic_sha256"])

    def test_correction_edit_does_change_the_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            before = correction_entries(root)[0]["semantic_sha256"]
            (root / CORRECTIONS_PATH).write_text(
                CORRECTIONS_MD.replace("即應設置。", "即應設置（修正）。"), encoding="utf-8")
            self.assertNotEqual(before, correction_entries(root)[0]["semantic_sha256"])


class JudgmentParseTest(unittest.TestCase):
    def test_splits_general_and_per_article_entries(self):
        entries = parse_judgment_rules(JUDGMENT_MD)
        kinds = [e["kind"] for e in entries]
        self.assertEqual(2, kinds.count("general"))
        self.assertEqual(2, kinds.count("article"))

    def test_article_number_comes_from_the_heading(self):
        by_label = {e["label"]: e for e in parse_judgment_rules(JUDGMENT_MD)}
        self.assertEqual("15", by_label["§15 室內消防栓設備"]["article"])
        self.assertEqual("28", by_label["§28 排煙設備"]["article"])

    def test_general_entry_label_comes_from_the_bold_term(self):
        labels = [e["label"] for e in parse_judgment_rules(JUDGMENT_MD) if e["kind"] == "general"]
        self.assertIn("地下建築物", labels)


class BuildTest(unittest.TestCase):
    def test_builds_markdown_layers_without_any_practice_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = build(root)
            self.assertTrue(result["ok"])
            self.assertEqual(6, result["markdown_entries"])
            graph = json.loads((root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8"))
            layers = {n["layer"] for n in graph["nodes"]}
            self.assertEqual({LAYER_CORRECTION, LAYER_JUDGMENT}, layers)

    def test_article_references_become_cross_graph_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            build(root)
            graph = json.loads((root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8"))
            entry = next(n for n in graph["nodes"] if n["layer"] == LAYER_CORRECTION)
            targets = {l["target_label"] for l in graph["links"] if l["source"] == entry["id"]}
            self.assertEqual({"第21條", "第22條"}, targets)
            for link in graph["links"]:
                self.assertEqual("regulation", link["target_graph"])
                self.assertFalse(link["dangling"])

    def test_builds_without_the_regulation_graph_and_marks_edges_dangling(self):
        """卡點 3(d)：訓練圖譜不該因為法規圖譜缺席就建不起來。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True, with_regulation=False)
            result = build(root)
            self.assertTrue(result["ok"])
            self.assertGreater(result["dangling"], 0)
            graph = json.loads((root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8"))
            # 訓練成果本身完整保留，只有跨圖譜的關聯待解析
            self.assertTrue(any(n.get("note_id") == NOTE["id"] for n in graph["nodes"]))
            self.assertTrue(all(l["target_label"] for l in graph["links"] if l["dangling"]))

    def test_dangling_edges_recover_once_the_regulation_graph_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True, with_regulation=False)
            build(root)
            write(root / "graphify-out" / "graph.json", {      # 法規圖譜補回來
                "nodes": [{"id": "a19", "label": "第19條", "file_type": "document"},
                          {"id": "a21", "label": "第21條", "file_type": "document"},
                          {"id": "a22", "label": "第22條", "file_type": "document"},
                          {"id": "a24", "label": "第24條", "file_type": "document"},
                          {"id": "a15", "label": "第15條", "file_type": "document"},
                          {"id": "a28", "label": "第28條", "file_type": "document"},
                          {"id": "e1", "label": "火警自動警報設備", "file_type": "concept"}],
                "links": []})
            self.assertEqual(0, build(root)["dangling"])
            self.assertEqual("covered", check(root)["state"])

    def test_refuses_by_default_when_a_note_lacks_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True)
            write(root / "practice_notes" / "active" / "PN-20260725-002.json",
                  {**NOTE, "id": "PN-20260725-002"})
            self.assertFalse(build(root)["ok"])

    def test_skip_pending_builds_the_rest_and_reports_what_was_skipped(self):
        """卡點 3(b)：一則壞掉不該讓其他訓練成果也進不了圖譜——但不得靜默。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True)
            write(root / "practice_notes" / "active" / "PN-20260725-002.json",
                  {**NOTE, "id": "PN-20260725-002"})
            result = build(root, skip_pending=True)
            self.assertTrue(result["ok"])
            self.assertEqual(["PN-20260725-002"], [s["note_id"] for s in result["skipped"]])
            self.assertEqual("uncovered", check(root)["state"])
            self.assertEqual(["PN-20260725-002"],
                             [s["note_id"] for s in check(root)["skipped"]])

    def test_only_rebuilds_the_named_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True)
            write(root / "practice_notes" / "active" / "PN-20260725-002.json",
                  {**NOTE, "id": "PN-20260725-002"})
            result = build(root, only={NOTE["id"]})
            self.assertTrue(result["ok"])
            self.assertEqual(1, result["notes"])

    def test_build_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_notes=True)
            build(root)
            first = (root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8")
            build(root)
            second = (root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8")
            self.assertEqual(json.loads(first)["nodes"], json.loads(second)["nodes"])


class CheckTest(unittest.TestCase):
    def test_not_built_is_informational_on_a_clean_install(self):
        """全新安裝只有上游帶的 markdown 筆記，沒建圖譜不是紅燈。"""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("not_built", check(make_repo(tmp))["state"])

    def test_absent_is_red_once_the_user_has_practice_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("absent", check(make_repo(tmp, with_notes=True))["state"])

    def test_edited_markdown_note_makes_the_graph_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            build(root)
            self.assertEqual("covered", check(root)["state"])
            (root / CORRECTIONS_PATH).write_text(
                CORRECTIONS_MD.replace("即應設置。", "即應設置（修正）。"), encoding="utf-8")
            result = check(root)
            self.assertEqual("uncovered", result["state"])
            self.assertEqual(1, len(result["stale"]))

    def test_removed_material_is_reported_as_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            build(root)
            (root / JUDGMENT_PATH).write_text("# 空", encoding="utf-8")
            self.assertEqual(4, len(check(root)["orphan"]))


class LegacyMigrationTest(unittest.TestCase):
    """分家前實務註解併在 graphify-out/graph.json 裡，本機升級的人要清得掉。"""

    def legacy_graph(self, root):
        write(root / "graphify-out" / "graph.json", {
            "nodes": [{"id": "a19", "label": "第19條", "file_type": "document"},
                      {"id": "practice_note_PN-1", "label": "PN-1", "layer": "practice_note",
                       "note_id": "PN-1", "file_type": "practice_note"},
                      {"id": "practice_note_concept_挑空區", "label": "挑空區",
                       "layer": "practice_note", "file_type": "concept"}],
            "links": [{"source": "practice_note_PN-1", "target": "a19",
                       "relation": "supplements"}]})

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_regulation=False)
            self.legacy_graph(root)
            before = (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
            result = migrate_from_legacy(root, dry_run=True)
            self.assertEqual(["PN-1"], result["note_ids"])
            self.assertEqual(2, len(result["nodes"]))
            self.assertEqual(before,
                             (root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))

    def test_apply_removes_the_legacy_layer_and_its_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, with_regulation=False)
            self.legacy_graph(root)
            migrate_from_legacy(root, dry_run=False)
            graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
            self.assertEqual(["a19"], [n["id"] for n in graph["nodes"]])
            self.assertEqual([], graph["links"])

    def test_nothing_to_do_on_a_clean_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual([], migrate_from_legacy(root, dry_run=True)["nodes"])


class RealRepoTest(unittest.TestCase):
    """對倉庫內真實的兩份 markdown 筆記行使——假資料驗不出真實格式的變化。"""

    def test_parses_the_shipped_notes(self):
        corrections = correction_entries(REPO)
        judgments = judgment_entries(REPO)
        self.assertGreaterEqual(len(corrections), 10)
        self.assertGreaterEqual(len(judgments), 10)
        self.assertTrue(all(e["id"] and e["semantic_sha256"] for e in corrections + judgments))

    def test_every_article_entry_resolves_into_the_real_regulation_graph(self):
        """判斷慣例的條號若解析不到，整層都會變成懸空。"""
        index = regulation_index(REPO)
        if not index.labels():
            self.skipTest("倉庫內沒有法規圖譜")
        for entry in judgment_entries(REPO):
            if entry["article"]:
                self.assertIsNotNone(
                    index.resolve(f"第{entry['article']}條").node_id, entry["label"])


if __name__ == "__main__":
    unittest.main()

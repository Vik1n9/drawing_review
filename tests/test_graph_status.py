import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.graph_status import (EXIT_CODES, collect_sources, diff_sources, evaluate, main,
                               untracked_graph_sources)
from tools.practice_note_graph import GRAPH_PATH, LAYER, merge

NOTE_ID = "PN-20260725-001"


def write_active_note(root):
    """一則最小可用的 active 註解（status 為 active 才會進納入度檢查）。"""
    note = {
        "id": NOTE_ID, "ref_article": "19", "ref_rule_ids": ["r1"],
        "scenario": {"summary": "挑空區", "conditions": {"space_type": "挑空區"}},
        "judgment": {"equipment": "火警自動警報設備", "decision": "exempt", "detail": "得免設"},
        "source_case": "Case", "status": "active", "created": "2026-07-25T10:00:00+08:00",
    }
    path = root / "practice_notes" / "active" / f"{NOTE_ID}.json"
    path.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def merge_note_into_graph(root, note_path):
    """建最小圖譜與語意抽取檔，走真正的 merge 流程把註解併進去。"""
    graph = {"directed": True, "graph": {}, "links": [],
             "nodes": [{"id": "a19", "label": "第19條", "file_type": "document"}]}
    (root / GRAPH_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / GRAPH_PATH).write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    extraction = {
        "schema_version": 1, "note_id": NOTE_ID,
        "note_sha256": hashlib.sha256(note_path.read_bytes()).hexdigest(),
        "extracted_by": "test-llm", "extracted_at": "2026-07-25T11:00:00+08:00",
        "summary": "挑空區情境",
        "concepts": [{"label": "挑空區", "kind": "scenario_condition", "rationale": "summary"}],
        "edges": [{"target": "第19條", "relation": "supplements", "rationale": "ref_article"}],
    }
    path = root / "practice_notes" / "graph_extractions" / f"{NOTE_ID}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(extraction, ensure_ascii=False), encoding="utf-8")
    result = merge(root)
    assert result["ok"], result
    assert any(n.get("layer") == LAYER
               for n in json.loads((root / GRAPH_PATH).read_text(encoding="utf-8"))["nodes"])


def make_repo(tmp):
    """建立最小圖譜來源結構：法規全文 ＋ rules/README.md ＋ 兩條逐條 JSON。

    equipment_rules.json／mixed_use_rules.json 刻意也建出來——它們在 rules/ 底下但
    不是圖譜來源，用來驗證追蹤清單不會把它們算進去。
    """
    root = Path(tmp)
    (root / "rules" / "regulation_articles").mkdir(parents=True)
    (root / "rules" / "core").mkdir(parents=True)
    (root / "practice_notes" / "active").mkdir(parents=True)
    (root / "rules" / "core" / "設置標準.md").write_text("# 全文", encoding="utf-8")
    (root / "rules" / "README.md").write_text("# 法規資料取用格式", encoding="utf-8")
    (root / "rules" / "equipment_rules.json").write_text('{"rules": []}', encoding="utf-8")
    (root / "rules" / "mixed_use_rules.json").write_text('{"rules": []}', encoding="utf-8")
    (root / "rules" / "regulation_articles" / "article-001.json").write_text('{"a": 1}', encoding="utf-8")
    (root / "rules" / "regulation_articles" / "article-002.json").write_text('{"a": 2}', encoding="utf-8")
    return root


class CollectSourcesTest(unittest.TestCase):
    def test_collects_codex_and_practice_note_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "practice_notes" / "active" / "PN-20260725-001.json").write_text(
                '{"id": "PN-20260725-001"}', encoding="utf-8")
            sources = collect_sources(root)
            self.assertEqual(sorted(sources), [
                "practice_notes/active/PN-20260725-001.json",
                "rules/README.md",
                "rules/core/設置標準.md",
                "rules/regulation_articles/article-001.json",
                "rules/regulation_articles/article-002.json",
            ])

    def test_rule_parameter_files_are_not_graph_sources(self):
        """圖譜不從規則參數檔抽節點——追蹤它們會讓每次先紅再綠都誤報過期。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            sources = collect_sources(root)
            self.assertNotIn("rules/equipment_rules.json", sources)
            self.assertNotIn("rules/mixed_use_rules.json", sources)

    def test_ignores_files_outside_the_graph_source_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "rules" / "review_corrections.md").write_text("# 筆記", encoding="utf-8")
            (root / "practice_notes" / "staging").mkdir()
            (root / "practice_notes" / "staging" / "PN-20260725-009.json").write_text("{}", encoding="utf-8")
            sources = collect_sources(root)
            self.assertNotIn("rules/review_corrections.md", sources)
            self.assertNotIn("practice_notes/staging/PN-20260725-009.json", sources)


class UntrackedSourceTest(unittest.TestCase):
    """追蹤清單刻意不含「掃描得到但不產生節點」的檔案；這個前提必須被持續驗證。"""

    def write_graph(self, root, source_file):
        path = root / "graphify-out" / "graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "nodes": [{"id": "n1", "label": "節點", "source_file": source_file}],
            "links": [],
        }, ensure_ascii=False), encoding="utf-8")

    def test_tracked_source_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.write_graph(root, "core/設置標準.md")
            self.assertEqual(untracked_graph_sources(root), [])

    def test_rules_relative_readme_resolves_inside_rules(self):
        """node.source_file 是相對 rules/ 的路徑，README.md 指的是 rules/README.md。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "README.md").write_text("# repo 根目錄", encoding="utf-8")
            self.write_graph(root, "README.md")
            self.assertEqual(untracked_graph_sources(root), [])

    def test_node_from_untracked_file_turns_the_gate_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.write_graph(root, "equipment_rules.json")
            self.assertEqual(untracked_graph_sources(root), ["rules/equipment_rules.json"])
            main(["--root", str(root), "stamp"])
            result = evaluate(root)
            self.assertEqual(result["state"], "untracked_sources")
            self.assertEqual(main(["--root", str(root), "check"]),
                             EXIT_CODES["untracked_sources"])


class DiffTest(unittest.TestCase):
    def test_reports_added_removed_and_changed(self):
        changes = diff_sources({"a": "1", "b": "2"}, {"b": "9", "c": "3"})
        self.assertEqual(changes, {"added": ["c"], "removed": ["a"], "changed": ["b"]})


class EvaluateTest(unittest.TestCase):
    def test_no_baseline_before_first_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual(evaluate(root)["state"], "no_baseline")
            self.assertEqual(main(["--root", str(root), "check"]), EXIT_CODES["no_baseline"])

    def test_fresh_right_after_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual(main(["--root", str(root), "stamp"]), 0)
            self.assertEqual(evaluate(root)["state"], "fresh")
            self.assertEqual(main(["--root", str(root), "check"]), 0)

    def test_stale_after_a_source_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            (root / "rules" / "core" / "設置標準.md").write_text("# 全文（修正）", encoding="utf-8")
            result = evaluate(root)
            self.assertEqual(result["state"], "stale")
            self.assertEqual(result["diff"]["changed"], ["rules/core/設置標準.md"])
            self.assertEqual(main(["--root", str(root), "check"]), EXIT_CODES["stale"])

    def test_stale_when_a_practice_note_is_added(self):
        """新增實務註解也代表圖譜該重建——註解層是後續案件要查到的知識節點。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            (root / "practice_notes" / "active" / "PN-20260725-001.json").write_text(
                '{"id": "PN-20260725-001"}', encoding="utf-8")
            result = evaluate(root)
            self.assertEqual(result["state"], "stale")
            self.assertEqual(result["diff"]["added"], ["practice_notes/active/PN-20260725-001.json"])

    def test_notes_missing_when_active_note_not_in_graph(self):
        """假綠燈防線：來源指紋一致，但註解沒併進圖譜時仍須紅燈。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            main(["--root", str(root), "stamp", "--allow-missing-notes"])
            result = evaluate(root)
            self.assertEqual(result["state"], "notes_missing")
            self.assertEqual(result["diff"], {"added": [], "removed": [], "changed": []})
            self.assertEqual(result["notes"]["missing"], ["PN-20260725-001"])
            self.assertEqual(main(["--root", str(root), "check"]), EXIT_CODES["notes_missing"])

    def test_stamp_refuses_while_notes_are_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            self.assertEqual(main(["--root", str(root), "stamp"]), 2)
            self.assertFalse((root / "graphify-out" / "source_fingerprint.json").is_file())

    def test_fresh_once_note_is_merged_into_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            note_path = write_active_note(root)
            merge_note_into_graph(root, note_path)
            self.assertEqual(main(["--root", str(root), "stamp"]), 0)
            self.assertEqual(evaluate(root)["state"], "fresh")

    def test_restamp_clears_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            (root / "rules" / "regulation_articles" / "article-003.json").write_text("{}", encoding="utf-8")
            self.assertEqual(evaluate(root)["state"], "stale")
            main(["--root", str(root), "stamp"])
            self.assertEqual(evaluate(root)["state"], "fresh")

    def test_stamp_records_date_and_source_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp", "--date", "2026-07-25"])
            doc = json.loads((root / "graphify-out" / "source_fingerprint.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["stamped_at"], "2026-07-25")
            self.assertEqual(doc["source_count"], 4)  # core md、README、兩條逐條 JSON


if __name__ == "__main__":
    unittest.main()

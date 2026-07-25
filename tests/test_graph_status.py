import json
import tempfile
import unittest
from pathlib import Path

from tools.graph_status import EXIT_CODES, collect_sources, diff_sources, evaluate, main


def make_repo(tmp):
    """建立最小圖譜來源結構：兩個規則檔 ＋ 兩條逐條 JSON ＋ 一則實務註解。"""
    root = Path(tmp)
    (root / "rules" / "regulation_articles").mkdir(parents=True)
    (root / "practice_notes" / "active").mkdir(parents=True)
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
                "rules/equipment_rules.json",
                "rules/mixed_use_rules.json",
                "rules/regulation_articles/article-001.json",
                "rules/regulation_articles/article-002.json",
            ])

    def test_ignores_files_outside_the_graph_source_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "rules" / "review_corrections.md").write_text("# 筆記", encoding="utf-8")
            (root / "practice_notes" / "staging").mkdir()
            (root / "practice_notes" / "staging" / "PN-20260725-009.json").write_text("{}", encoding="utf-8")
            sources = collect_sources(root)
            self.assertNotIn("rules/review_corrections.md", sources)
            self.assertNotIn("practice_notes/staging/PN-20260725-009.json", sources)


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
            (root / "rules" / "equipment_rules.json").write_text(
                '{"rules": [{"id": "new"}]}', encoding="utf-8")
            result = evaluate(root)
            self.assertEqual(result["state"], "stale")
            self.assertEqual(result["diff"]["changed"], ["rules/equipment_rules.json"])
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
            self.assertEqual(doc["source_count"], 4)


if __name__ == "__main__":
    unittest.main()

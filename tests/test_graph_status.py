import json
import tempfile
import unittest
from pathlib import Path

from tools.graph_status import (REGULATION_EXIT, collect_sources, diff_sources, evaluate, main,
                                untracked_graph_sources)
from tools.practice_note_graph import semantic_digest
from tools.training_graph_build import TRAINING_GRAPH_PATH, build

NOTE_ID = "PN-20260725-001"
NOTE = {
    "id": NOTE_ID, "ref_article": "19", "ref_rule_ids": ["r1"],
    "scenario": {"summary": "挑空區", "conditions": {"space_type": "挑空區"}},
    "judgment": {"equipment": "火警自動警報設備", "decision": "exempt", "detail": "得免設"},
    "source_case": "Case", "status": "active", "created": "2026-07-25T10:00:00+08:00",
}


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def write_active_note(root):
    path = root / "practice_notes" / "active" / f"{NOTE_ID}.json"
    write(path, NOTE)
    return path


def write_regulation_graph(root):
    write(root / "graphify-out" / "graph.json", {
        "directed": True, "graph": {}, "links": [],
        "nodes": [{"id": "a19", "label": "第19條", "file_type": "document"},
                  {"id": "e1", "label": "火警自動警報設備", "file_type": "concept"}]})


def write_extraction(root):
    write(root / "practice_notes" / "graph_extractions" / f"{NOTE_ID}.json", {
        "schema_version": 2, "note_id": NOTE_ID, "note_semantic_sha256": semantic_digest(NOTE),
        "extracted_by": "test-llm", "extracted_at": "2026-07-25T11:00:00+08:00",
        "summary": "挑空區情境",
        "concepts": [{"label": "挑空區", "kind": "scenario_condition", "rationale": "summary"}],
        "edges": [{"target": "第19條", "relation": "supplements", "rationale": "ref_article"}]})


def make_repo(tmp):
    """最小法規圖譜來源結構：法規全文 ＋ rules/README.md ＋ 兩條逐條 JSON。

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
    for name in ("article-001.json", "article-002.json"):
        (root / "rules" / "regulation_articles" / name).write_text('{"a": 1}', encoding="utf-8")
    return root


class CollectSourcesTest(unittest.TestCase):
    def test_collects_only_regulation_graph_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual(sorted(collect_sources(root)), [
                "rules/README.md",
                "rules/core/設置標準.md",
                "rules/regulation_articles/article-001.json",
                "rules/regulation_articles/article-002.json",
            ])

    def test_practice_notes_are_not_regulation_sources(self):
        """分家的正回歸：改一則實務註解不該害法規圖譜判過期。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            self.assertNotIn(f"practice_notes/active/{NOTE_ID}.json", collect_sources(root))

    def test_rule_parameter_files_are_not_graph_sources(self):
        """圖譜不從規則參數檔抽節點——追蹤它們會讓每次先紅再綠都誤報過期。"""
        with tempfile.TemporaryDirectory() as tmp:
            sources = collect_sources(make_repo(tmp))
            self.assertNotIn("rules/equipment_rules.json", sources)
            self.assertNotIn("rules/mixed_use_rules.json", sources)

    def test_ignores_files_outside_the_graph_source_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "practice_notes" / "staging").mkdir()
            (root / "practice_notes" / "staging" / "PN-9.json").write_text("{}", encoding="utf-8")
            self.assertNotIn("practice_notes/staging/PN-9.json", collect_sources(root))


class UntrackedSourceTest(unittest.TestCase):
    """追蹤清單刻意不含「掃描得到但不產生節點」的檔案；這個前提必須被持續驗證。"""

    def write_graph(self, root, source_file):
        write(root / "graphify-out" / "graph.json",
              {"nodes": [{"id": "n1", "label": "節點", "source_file": source_file}], "links": []})

    def test_tracked_source_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.write_graph(root, "core/設置標準.md")
            self.assertEqual([], untracked_graph_sources(root))

    def test_rules_relative_readme_resolves_inside_rules(self):
        """node.source_file 是相對 rules/ 的路徑，README.md 指的是 rules/README.md。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "README.md").write_text("# repo 根目錄", encoding="utf-8")
            self.write_graph(root, "README.md")
            self.assertEqual([], untracked_graph_sources(root))

    def test_node_from_untracked_file_turns_the_gate_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.write_graph(root, "equipment_rules.json")
            self.assertEqual(["rules/equipment_rules.json"], untracked_graph_sources(root))
            main(["--root", str(root), "stamp"])
            self.assertEqual("untracked_sources", evaluate(root)["regulation"]["state"])
            self.assertEqual(REGULATION_EXIT["untracked_sources"],
                             main(["--root", str(root), "check"]))


class DiffTest(unittest.TestCase):
    def test_reports_added_removed_and_changed(self):
        self.assertEqual({"added": ["c"], "removed": ["a"], "changed": ["b"]},
                         diff_sources({"a": "1", "b": "2"}, {"b": "9", "c": "3"}))


class RegulationGraphTest(unittest.TestCase):
    def state(self, root):
        return evaluate(root)["regulation"]["state"]

    def test_no_baseline_before_first_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual("no_baseline", self.state(root))
            self.assertEqual(REGULATION_EXIT["no_baseline"],
                             main(["--root", str(root), "check"]))

    def test_fresh_right_after_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual(0, main(["--root", str(root), "stamp"]))
            self.assertEqual("fresh", self.state(root))
            self.assertEqual(0, main(["--root", str(root), "check"]))

    def test_stale_after_a_source_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            (root / "rules" / "core" / "設置標準.md").write_text("# 全文（修正）", encoding="utf-8")
            result = evaluate(root)
            self.assertEqual("stale", result["regulation"]["state"])
            self.assertEqual(["rules/core/設置標準.md"], result["regulation"]["diff"]["changed"])
            self.assertEqual(REGULATION_EXIT["stale"], main(["--root", str(root), "check"]))

    def test_adding_a_practice_note_does_not_stale_the_regulation_graph(self):
        """分家的核心回歸：訓練成果的變動只影響訓練圖譜。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_regulation_graph(root)
            main(["--root", str(root), "stamp", "--allow-missing-notes", "--reason", "測試"])
            write_active_note(root)
            self.assertEqual("fresh", self.state(root))

    def test_restamp_clears_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            (root / "rules" / "regulation_articles" / "article-003.json").write_text(
                "{}", encoding="utf-8")
            self.assertEqual("stale", self.state(root))
            main(["--root", str(root), "stamp"])
            self.assertEqual("fresh", self.state(root))

    def test_stamp_records_date_and_source_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp", "--date", "2026-07-25"])
            doc = json.loads((root / "graphify-out" / "source_fingerprint.json")
                             .read_text(encoding="utf-8"))
            self.assertEqual("2026-07-25", doc["stamped_at"])
            self.assertEqual(4, doc["source_count"])  # core md、README、兩條逐條 JSON


class TrainingGateTest(unittest.TestCase):
    def test_stamp_refuses_while_training_graph_lags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            self.assertEqual(2, main(["--root", str(root), "stamp"]))
            self.assertFalse((root / "graphify-out" / "source_fingerprint.json").is_file())

    def test_allow_missing_notes_requires_a_reason(self):
        """會蓋出「只有法規、查不到訓練成果」的綠燈，必須留下理由供追溯。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            self.assertEqual(1, main(["--root", str(root), "stamp", "--allow-missing-notes"]))
            self.assertFalse((root / "graphify-out" / "source_fingerprint.json").is_file())

    def test_excluded_notes_are_recorded_and_keep_check_red(self):
        """卡點 3(e)：強制蓋章不得變成靜默的假綠燈。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_active_note(root)
            self.assertEqual(0, main(["--root", str(root), "stamp",
                                      "--allow-missing-notes", "--reason", "離線批次"]))
            doc = json.loads((root / "graphify-out" / "source_fingerprint.json")
                             .read_text(encoding="utf-8"))
            self.assertEqual([NOTE_ID], doc["practice_notes_excluded"])
            self.assertEqual("離線批次", doc["excluded_reason"])
            # 法規圖譜自己是新鮮的，但整體仍紅——訓練成果還沒進圖譜
            self.assertEqual("fresh", evaluate(root)["regulation"]["state"])
            self.assertEqual(2, main(["--root", str(root), "check"]))

    def test_green_once_the_training_graph_is_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_regulation_graph(root)
            write_active_note(root)
            write_extraction(root)
            self.assertTrue(build(root)["ok"])
            self.assertEqual(0, main(["--root", str(root), "stamp"]))
            self.assertEqual(0, main(["--root", str(root), "check"]))

    def test_clean_repo_without_training_material_is_green(self):
        """全新安裝不得亮紅燈——訓練圖譜是衍生產物，沒建不是錯。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            self.assertEqual(0, main(["--root", str(root), "check"]))

    def test_graph_pending_flag_turns_check_red(self):
        """文件一直宣稱 CI 會因為這個旗標紅燈——現在真的會。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            main(["--root", str(root), "stamp"])
            write(root / "training" / "graph_pending.json", {"reason": "離線，圖譜未重建"})
            self.assertEqual("rebuild_pending", evaluate(root)["training"]["state"])
            self.assertEqual(2, main(["--root", str(root), "check"]))

    def test_stale_training_material_turns_check_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_regulation_graph(root)
            write_active_note(root)
            write_extraction(root)
            build(root)
            main(["--root", str(root), "stamp"])
            # 改語意欄位——訓練圖譜過期，但法規圖譜不受影響
            write(root / "practice_notes" / "active" / f"{NOTE_ID}.json",
                  {**NOTE, "judgment": {**NOTE["judgment"], "detail": "改過"}})
            result = evaluate(root)
            self.assertEqual("fresh", result["regulation"]["state"])
            self.assertEqual([NOTE_ID], result["training"]["coverage"]["stale"])
            self.assertEqual(2, main(["--root", str(root), "check"]))


class TrainingGraphIsolationTest(unittest.TestCase):
    def test_rebuilding_the_regulation_graph_leaves_training_graph_untouched(self):
        """分家要保證的事：法規圖譜重建碰不到使用者的訓練成果。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_regulation_graph(root)
            write_active_note(root)
            write_extraction(root)
            build(root)
            before = (root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8")
            write_regulation_graph(root)      # 模擬重建覆寫法規圖譜
            after = (root / TRAINING_GRAPH_PATH).read_text(encoding="utf-8")
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

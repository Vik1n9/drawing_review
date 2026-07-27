import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.regulation_graph import (
    DEFAULT_GRAPH,
    article_label,
    article_numbers,
    load_graph,
    load_graphs,
    main,
    sibling_training_graph,
)

PREFIX = "rules_core_1各類場所消防安全設備設置標準"


def fake_graph():
    def article(no):
        return {"id": f"{PREFIX}_第{no}條", "label": f"第{no}條", "file_type": "document"}
    return {
        "nodes": [
            article(12), article(19), article(21), article(22), article(28),
            {"id": f"{PREFIX}_排煙設備", "label": "排煙設備", "file_type": "concept"},
            {"id": f"{PREFIX}_無開口樓層", "label": "無開口樓層", "file_type": "concept"},
            {"id": f"{PREFIX}_assets_article_18_page_1",
             "label": "第 18 條官方完整條文附件，第 1 頁", "file_type": "image"},
        ],
        "links": [
            {"source": f"{PREFIX}_第22條", "target": f"{PREFIX}_第19條", "relation": "cites"},
            {"source": f"{PREFIX}_第22條", "target": f"{PREFIX}_第21條", "relation": "cites"},
            {"source": f"{PREFIX}_第28條", "target": f"{PREFIX}_第12條", "relation": "cites"},
            {"source": f"{PREFIX}_第28條", "target": f"{PREFIX}_排煙設備", "relation": "references"},
            {"source": f"{PREFIX}_第28條", "target": f"{PREFIX}_無開口樓層", "relation": "references"},
            {"source": f"{PREFIX}_第28條", "target": f"{PREFIX}_assets_article_18_page_1",
             "relation": "references"},
        ],
    }


class HelpersTest(unittest.TestCase):
    def test_article_label_accepts_common_forms(self):
        for value in ("§24", "24", "第24條", "§24條"):
            self.assertEqual(article_label(value), "第24條")
        self.assertEqual(article_label("§22-1"), "第22-1條")
        self.assertIsNone(article_label("排煙設備"))

    def test_article_numbers_sorts_numerically_not_lexically(self):
        nodes = {n["id"]: n for n in fake_graph()["nodes"]}
        ids = [f"{PREFIX}_第{n}條" for n in (28, 12, 19)]
        self.assertEqual(article_numbers(ids, nodes), ["§12", "§19", "§28"])

    def test_article_numbers_ignores_non_article_nodes(self):
        nodes = {n["id"]: n for n in fake_graph()["nodes"]}
        self.assertEqual(article_numbers([f"{PREFIX}_排煙設備"], nodes), [])


class GraphQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "graph.json"
        self.path.write_text(json.dumps(fake_graph(), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, args):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--graph", str(self.path), "--format", "json"] + args)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_neighbors_splits_outgoing_incoming_and_images(self):
        payload = self.run_cli(["neighbors", "--article", "§28"])
        outgoing = [e["label"] for e in payload["groups"]["引用（本條 → 他條/概念）"]]
        self.assertIn("第12條", outgoing)
        self.assertIn("排煙設備", outgoing)
        self.assertEqual(len(payload["groups"]["附表圖檔"]), 1)
        self.assertEqual(payload["related_articles"], ["§12"])

    def test_neighbors_reports_incoming_references(self):
        payload = self.run_cli(["neighbors", "--article", "§19"])
        incoming = [e["label"] for e in payload["groups"]["被引用（他條 → 本條）"]]
        self.assertEqual(incoming, ["第22條"])

    def test_lookup_hint_is_a_runnable_comma_list(self):
        payload = self.run_cli(["neighbors", "--article", "§28"])
        self.assertIn("lookup --article '§28,§12'", payload["lookup_hint"])

    def test_articles_by_equipment_lists_regulating_articles(self):
        payload = self.run_cli(["articles", "--equipment", "排煙設備"])
        self.assertEqual(payload["articles"], ["§28"])

    def test_path_between_concepts(self):
        payload = self.run_cli(["path", "--from", "無開口樓層", "--to", "排煙設備"])
        self.assertEqual(payload["path"], ["無開口樓層", "第28條", "排煙設備"])
        self.assertEqual(payload["related_articles"], ["§28"])

    def test_every_output_carries_the_boundary_warning(self):
        for args in (["neighbors", "--article", "§28"],
                     ["articles", "--equipment", "排煙設備"],
                     ["path", "--from", "無開口樓層", "--to", "排煙設備"]):
            self.assertIn("不是門檻數值來源", self.run_cli(args)["lookup_hint"])

    def test_unknown_article_exits_with_guidance(self):
        with self.assertRaises(SystemExit) as ctx, contextlib.redirect_stdout(io.StringIO()):
            main(["--graph", str(self.path), "neighbors", "--article", "§999"])
        self.assertIn("找不到", str(ctx.exception))

    def test_missing_graph_file_exits_with_rebuild_hint(self):
        with self.assertRaises(SystemExit) as ctx:
            main(["--graph", "/nonexistent/graph.json", "neighbors", "--article", "§28"])
        # 重建已收回第一方——訊息不得再把使用者指向裝不起來的 graphify
        self.assertIn("regulation_graph_build.py", str(ctx.exception))
        self.assertNotIn("graphify", str(ctx.exception))


def graph_with_practice_note():
    """圖譜 ＋ 一則已併入的實務註解（practice_note_graph.py merge 的產物形狀）。"""
    graph = fake_graph()
    graph["nodes"].append({
        "id": "practice_note_PN-20260725-001", "label": "PN-20260725-001",
        "file_type": "practice_note", "layer": "practice_note",
        "note_id": "PN-20260725-001", "note_sha256": "deadbeef",
        "ref_article": "第19條", "equipment": "排煙設備", "decision": "exempt_with_alternatives",
        "graph_summary": "挑空區逾 12 公尺得以火焰式探測器替代",
        "source_case": "Case_20260725",
        "source_file": "practice_notes/active/PN-20260725-001.json",
    })
    graph["links"].append({"source": "practice_note_PN-20260725-001",
                           "target": f"{PREFIX}_第19條", "relation": "supplements",
                           "layer": "practice_note"})
    graph["links"].append({"source": "practice_note_PN-20260725-001",
                           "target": f"{PREFIX}_排煙設備", "relation": "concerns_equipment",
                           "layer": "practice_note"})
    return graph


class PracticeNoteQueryTest(unittest.TestCase):
    """訓練成果（實務註解）必須查得到——審圖時查圖譜就要看見它。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "graph.json"
        self.path.write_text(json.dumps(graph_with_practice_note(), ensure_ascii=False),
                             encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, args, fmt="json"):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main(["--graph", str(self.path), "--format", fmt] + args)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue()) if fmt == "json" else out.getvalue()

    def test_neighbors_surfaces_the_note_for_its_article(self):
        payload = self.run_cli(["neighbors", "--article", "§19"])
        self.assertEqual([n["note_id"] for n in payload["practice_notes"]], ["PN-20260725-001"])
        self.assertIn("非法規條文", payload["practice_notes"][0]["notice"])

    def test_note_is_not_mixed_into_article_citation_groups(self):
        payload = self.run_cli(["neighbors", "--article", "§19"])
        labels = [e["label"] for group in payload["groups"].values() for e in group]
        self.assertNotIn("PN-20260725-001", labels)

    def test_articles_by_equipment_surfaces_related_notes(self):
        payload = self.run_cli(["articles", "--equipment", "排煙設備"])
        self.assertEqual([n["note_id"] for n in payload["practice_notes"]], ["PN-20260725-001"])

    def test_notes_subcommand_filters_by_article_and_equipment(self):
        self.assertEqual([n["note_id"] for n in
                          self.run_cli(["notes", "--article", "§19"])["practice_notes"]],
                         ["PN-20260725-001"])
        self.assertEqual([n["note_id"] for n in
                          self.run_cli(["notes", "--equipment", "排煙設備"])["practice_notes"]],
                         ["PN-20260725-001"])
        self.assertEqual([n["note_id"] for n in
                          self.run_cli(["notes", "--article", "§28"])["practice_notes"]], [])

    def test_notes_subcommand_lists_all_by_default(self):
        payload = self.run_cli(["notes"])
        self.assertEqual([n["note_id"] for n in payload["practice_notes"]], ["PN-20260725-001"])

    def test_markdown_output_carries_the_note_warning(self):
        text = self.run_cli(["neighbors", "--article", "§19"], fmt="markdown")
        self.assertIn("PN-20260725-001", text)
        self.assertIn("非法規條文", text)

    def test_graph_without_notes_still_answers_cleanly(self):
        path = Path(self.tmp.name) / "plain.json"
        path.write_text(json.dumps(fake_graph(), ensure_ascii=False), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            main(["--graph", str(path), "--format", "json", "notes"])
        self.assertEqual(json.loads(out.getvalue())["practice_notes"], [])


class RealGraphTest(unittest.TestCase):
    def test_repo_graph_answers_the_documented_queries(self):
        nodes, out, into = load_graphs(DEFAULT_GRAPH)
        self.assertGreater(len(nodes), 100)
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            main(["--format", "json", "articles", "--equipment", "排煙設備"])
        self.assertIn("§28", json.loads(buffer.getvalue())["articles"])


class TwoGraphLoadTest(unittest.TestCase):
    """查詢時把兩個圖譜合併在記憶體裡——它們在磁碟上始終是分開的兩個檔。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.regulation = root / "graphify-out" / "graph.json"
        self.regulation.parent.mkdir(parents=True)
        self.regulation.write_text(json.dumps(fake_graph(), ensure_ascii=False), encoding="utf-8")
        self.training = root / "training" / "graph.json"
        self.training.parent.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_training(self, target_id, target_label="第28條"):
        self.training.write_text(json.dumps({
            "nodes": [{"id": "correction_x", "label": "某修正筆記",
                       "layer": "review_correction", "entry_id": "correction_x",
                       "summary": "摘要", "notice": "實務慣例，非法規條文"}],
            "links": [{"source": "correction_x", "target": target_id,
                       "target_label": target_label, "target_graph": "regulation",
                       "relation": "supplements", "dangling": target_id is None}],
        }, ensure_ascii=False), encoding="utf-8")

    def test_training_graph_is_absent_without_error(self):
        nodes, _, _ = load_graphs(str(self.regulation))
        self.assertNotIn("correction_x", nodes)

    def test_training_nodes_join_the_query(self):
        self.write_training(f"{PREFIX}_第28條")
        nodes, _, into = load_graphs(str(self.regulation))
        self.assertIn("correction_x", nodes)
        self.assertTrue(any(e["source"] == "correction_x"
                            for e in into[f"{PREFIX}_第28條"]))

    def test_stale_target_id_is_recovered_through_the_label(self):
        """法規圖譜重建後 id 變了，訓練成果仍靠 target_label 掛回去。"""
        self.write_training("id_from_a_previous_rebuild")
        _, _, into = load_graphs(str(self.regulation))
        self.assertTrue(any(e["source"] == "correction_x"
                            for e in into[f"{PREFIX}_第28條"]))

    def test_dangling_edge_is_skipped_but_the_node_survives(self):
        self.write_training(None, target_label="第999條")
        nodes, out, _ = load_graphs(str(self.regulation))
        self.assertIn("correction_x", nodes)
        self.assertEqual([], out.get("correction_x", []))

    def test_only_regulation_excludes_training_nodes(self):
        self.write_training(f"{PREFIX}_第28條")
        nodes, _, _ = load_graphs(str(self.regulation), only="regulation")
        self.assertNotIn("correction_x", nodes)

    def test_training_graph_follows_the_regulation_graph_repo(self):
        """--graph 指到別的倉庫時，訓練圖譜必須跟著走，不能混入當前目錄的成果。"""
        self.assertEqual(str(self.training),
                         sibling_training_graph(str(self.regulation)))



if __name__ == "__main__":
    unittest.main()

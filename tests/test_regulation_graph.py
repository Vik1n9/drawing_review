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
    main,
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
        self.assertIn("graphify rules", str(ctx.exception))


class RealGraphTest(unittest.TestCase):
    def test_repo_graph_answers_the_documented_queries(self):
        nodes, out, into = load_graph(DEFAULT_GRAPH)
        self.assertGreater(len(nodes), 100)
        with contextlib.redirect_stdout(io.StringIO()) as buffer:
            main(["--format", "json", "articles", "--equipment", "排煙設備"])
        self.assertIn("§28", json.loads(buffer.getvalue())["articles"])


if __name__ == "__main__":
    unittest.main()

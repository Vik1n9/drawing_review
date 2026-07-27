import json
import tempfile
import unittest
from pathlib import Path

from tools.graph_labels import LabelIndex
from tools.regulation_graph_build import (GRAPH_PATH, LEDGER_PATH, Ledger, chunks, citations,
                                          load_articles, load_assets, main, mint_id, plan,
                                          rebuild, validate_extraction, verify, verify_is_green)

REPO = Path(__file__).resolve().parent.parent
REAL_GRAPH = REPO / GRAPH_PATH

MD_SOURCE = "core/設置標準.md"


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def article(number, markdown, hierarchy=("第一編　總則",)):
    return {"id": f"article-{number}", "article_no": number, "legal_basis": f"§{number}",
            "title": f"第 {number} 條", "source_file": f"rules/{MD_SOURCE}",
            "hierarchy": list(hierarchy), "markdown": markdown, "equipment_tags": []}


def make_repo(tmp, articles=None, graph=None):
    root = Path(tmp)
    articles = articles or [
        article("1", "本標準依消防法第六條第一項規定訂定之。"),
        article("2", "（刪除）"),
        article("7", "各類場所消防安全設備如下：滅火設備、警報設備。"),
        article("8", "滅火設備種類如下。"),
        article("19", "下列場所應設置火警自動警報設備，依第十二條規定辦理。"),
        article("20", "前條所定場所，依第七條規定。"),
    ]
    for doc in articles:
        write(root / "rules" / "regulation_articles" / f"article-{doc['article_no']}.json", doc)
    (root / "rules" / "core").mkdir(parents=True, exist_ok=True)
    (root / "rules" / "core" / "設置標準.md").write_text("# 全文", encoding="utf-8")
    if graph is not None:
        write(root / GRAPH_PATH, graph)
    return root


def graph_with(nodes, links=(), hyperedges=()):
    return {"directed": False, "multigraph": False, "graph": {}, "nodes": list(nodes),
            "links": list(links), "hyperedges": list(hyperedges)}


class MintIdTest(unittest.TestCase):
    def test_reproduces_the_existing_naming_scheme(self):
        self.assertEqual("rules_core_1各類場所消防安全設備設置標準_第19條",
                         mint_id("core/1各類場所消防安全設備設置標準.md", "第19條"))
        self.assertEqual("rules_readme", mint_id("README.md"))
        self.assertEqual("rules_core_1各類場所消防安全設備設置標準_assets_article_18_page_1",
                         mint_id("core/1各類場所消防安全設備設置標準_assets/article-18-page-1.png"))


class LedgerTest(unittest.TestCase):
    def test_existing_ids_are_carried_over_not_recomputed(self):
        """PDF 概念的 id 是縮寫過的，從 label 反推不出來——只能沿用。"""
        ledger = Ledger()
        ledger.learn_from_graph(graph_with([
            {"id": "concept_甲類一_電影片映演場所", "label": "甲類（一）電影片映演場所（戲院、電影院）",
             "source_file": "core/對照表.pdf"}]))
        self.assertEqual("concept_甲類一_電影片映演場所",
                         ledger.id_for("core/對照表.pdf", "甲類（一）電影片映演場所（戲院、電影院）"))
        self.assertEqual([], ledger.minted)

    def test_new_label_mints_and_is_reported(self):
        ledger = Ledger()
        ledger.id_for(MD_SOURCE, "第99條")
        self.assertEqual(["第99條"], [m["label"] for m in ledger.minted])


class CitationTest(unittest.TestCase):
    def order_of(self, articles):
        order = {a["number"]: i for i, a in enumerate(articles)}
        order["_sequence"] = [a["number"] for a in articles]
        return order

    def cite(self, markdown, others=("7", "8", "12", "19", "20")):
        articles = load_articles(make_repo(tempfile.mkdtemp()))
        target = {"number": "999", "markdown": markdown}
        return citations(target, set(others), self.order_of(articles))

    def test_external_law_reference_is_excluded(self):
        """本標準依消防法第六條…不是對本標準第 6 條的引用。"""
        self.assertEqual([], self.cite("本標準依消防法第六條第一項規定訂定之。", {"6"}))

    def test_external_law_with_a_long_gap_is_still_excluded(self):
        self.assertEqual([], self.cite("符合建築技術規則建築設計施工篇第八十八條規定者。", {"88"}))

    def test_literal_reference_is_captured(self):
        self.assertEqual(["12"], self.cite("依第十二條規定辦理。"))

    def test_range_is_expanded_to_existing_articles_only(self):
        got = self.cite("依第七條至第十九條之規定。", {"7", "8", "12", "19"})
        self.assertEqual({"7", "8", "12", "19"}, set(got))

    def test_previous_article_resolves_by_article_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            articles = load_articles(root)
            target = next(a for a in articles if a["number"] == "20")
            self.assertIn("19", citations(target, {a["number"] for a in articles},
                                          self.order_of(articles)))

    def test_self_reference_is_not_an_edge(self):
        articles = load_articles(make_repo(tempfile.mkdtemp()))
        target = {"number": "19", "markdown": "第十九條之規定。"}
        self.assertEqual([], citations(target, {"19"}, self.order_of(articles)))


class ChunkTest(unittest.TestCase):
    def test_groups_by_hierarchy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, articles=[
                article("1", "甲", hierarchy=("第一編",)),
                article("2", "乙", hierarchy=("第一編",)),
                article("3", "丙", hierarchy=("第二編", "第一章")),
            ])
            found = chunks(load_articles(root))
            self.assertEqual(2, len(found))
            self.assertEqual([["1", "2"], ["3"]], [c["articles"] for c in found])

    def test_whitespace_only_edit_does_not_change_the_chunk_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            before = {c["id"]: c["sha256"] for c in chunks(load_articles(root))}
            path = root / "rules" / "regulation_articles" / "article-19.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["markdown"] = doc["markdown"].replace("，", "，  ")
            write(path, doc)
            self.assertEqual(before, {c["id"]: c["sha256"] for c in chunks(load_articles(root))})

    def test_content_edit_changes_the_chunk_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            before = {c["id"]: c["sha256"] for c in chunks(load_articles(root))}
            path = root / "rules" / "regulation_articles" / "article-19.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["markdown"] += "（新增但書）"
            write(path, doc)
            self.assertNotEqual(before, {c["id"]: c["sha256"] for c in chunks(load_articles(root))})


class RebuildTest(unittest.TestCase):
    def test_preserves_concept_nodes_and_semantic_edges(self):
        """重建只增不減——概念層與語意邊必須原樣活下來。"""
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with(
                [{"id": "rules_core_設置標準_第19條", "label": "第19條", "file_type": "document",
                  "source_file": MD_SOURCE},
                 {"id": "concept_無開口樓層", "label": "無開口樓層", "file_type": "concept",
                  "source_file": MD_SOURCE, "community": 3}],
                [{"source": "rules_core_設置標準_第19條", "target": "concept_無開口樓層",
                  "relation": "references", "confidence": "EXTRACTED"}])
            root = make_repo(tmp, graph=existing)
            graph, report = rebuild(root)
            ids = {n["id"] for n in graph["nodes"]}
            self.assertIn("concept_無開口樓層", ids)
            concept = next(n for n in graph["nodes"] if n["id"] == "concept_無開口樓層")
            self.assertEqual(3, concept["community"])   # 外來欄位原樣帶回
            self.assertTrue(any(l["target"] == "concept_無開口樓層" for l in graph["links"]))
            self.assertEqual([], report["dropped_edges"])

    def test_does_not_reclassify_an_existing_edge(self):
        """既有邊的關聯類型不動——那種歸位會產生無法人工覆核的大量 diff。"""
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with(
                [{"id": "a19", "label": "第19條", "file_type": "document", "source_file": MD_SOURCE},
                 {"id": "a12", "label": "第12條", "file_type": "document", "source_file": MD_SOURCE}],
                [{"source": "a19", "target": "a12", "relation": "references",
                  "confidence": "EXTRACTED"}])
            root = make_repo(tmp, articles=[
                article("12", "用途分類如下。"),
                article("19", "下列場所應設置火警自動警報設備，依第十二條規定辦理。")],
                graph=existing)
            graph, _ = rebuild(root)
            pair = [l for l in graph["links"] if l["source"] == "a19" and l["target"] == "a12"]
            self.assertEqual(1, len(pair))
            self.assertEqual("references", pair[0]["relation"])

    def test_hyperedges_survive_with_valid_node_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with(
                [{"id": "a7", "label": "第7條", "file_type": "document", "source_file": MD_SOURCE}],
                hyperedges=[{"id": "h1", "nodes": ["a7"]}])
            root = make_repo(tmp, articles=[article("7", "分類如下。")], graph=existing)
            graph, report = rebuild(root)
            self.assertEqual([], report["hyperedge_problems"])
            self.assertEqual(1, len(graph["hyperedges"]))

    def test_hyperedge_pointing_at_a_vanished_node_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with([], hyperedges=[{"id": "h1", "nodes": ["gone"]}])
            root = make_repo(tmp, articles=[article("7", "分類如下。")], graph=existing)
            _, report = rebuild(root)
            self.assertEqual(["h1"], [p["id"] for p in report["hyperedge_problems"]])

    def test_deleted_article_still_becomes_a_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, graph=graph_with([]))
            graph, _ = rebuild(root)
            self.assertIn("第2條", [n["label"] for n in graph["nodes"]])

    def test_ledger_is_written_on_rebuild(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, graph=graph_with([]))
            main(["--root", str(root), "rebuild"])
            doc = json.loads((root / LEDGER_PATH).read_text(encoding="utf-8"))
            self.assertTrue(doc["nodes"])
            self.assertIn("19", doc["articles"])


class IncrementalPlanTest(unittest.TestCase):
    def test_only_the_edited_chunk_is_flagged_for_re_extraction(self):
        """改一條條文只該讓它所屬的那一塊待重抽，其餘 24 塊不動。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, articles=[
                article("1", "甲", hierarchy=("第一編",)),
                article("2", "乙", hierarchy=("第一編",)),
                article("3", "丙", hierarchy=("第二編",)),
            ], graph=graph_with([]))
            main(["--root", str(root), "rebuild"])       # 寫入台帳，建立基準
            self.assertEqual([], plan(root)["pending"])

            path = root / "rules" / "regulation_articles" / "article-3.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["markdown"] = "丙（修正）"
            write(path, doc)

            pending = plan(root)["pending"]
            self.assertEqual(1, len(pending))
            self.assertEqual(["3"], pending[0]["articles"])
            self.assertEqual("changed", pending[0]["reason"])

    def test_rebuild_never_loses_semantics_even_without_re_extraction(self):
        """條文改了但還沒重抽——圖譜不該因此掉語意邊（只增不減）。"""
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with(
                [{"id": "rules_core_設置標準_第3條", "label": "第3條", "file_type": "document",
                  "source_file": MD_SOURCE},
                 {"id": "concept_x", "label": "某概念", "file_type": "concept",
                  "source_file": MD_SOURCE}],
                [{"source": "rules_core_設置標準_第3條", "target": "concept_x",
                  "relation": "references", "confidence": "EXTRACTED"}])
            root = make_repo(tmp, articles=[article("3", "丙（修正）", hierarchy=("第二編",))],
                             graph=existing)
            graph, _ = rebuild(root)
            self.assertTrue(any(l["target"] == "concept_x" for l in graph["links"]))


class VerifyTest(unittest.TestCase):
    def test_lost_edge_between_surviving_nodes_is_red(self):
        """使用者察覺不到的劣化：查詢只會少回幾筆，不會報錯。"""
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with(
                [{"id": "a7", "label": "第7條", "file_type": "document", "source_file": MD_SOURCE},
                 {"id": "x", "label": "某概念", "file_type": "concept", "source_file": MD_SOURCE}],
                [{"source": "a7", "target": "x", "relation": "references"}])
            root = make_repo(tmp, articles=[article("7", "分類如下。")], graph=existing)
            result = verify(root)
            self.assertEqual([], result["edges_lost"])
            self.assertTrue(verify_is_green(result))

    def test_commit_refuses_while_verify_is_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            existing = graph_with([{"id": "gone", "label": "不存在的來源",
                                    "file_type": "document", "source_file": "core/沒了.md"}])
            root = make_repo(tmp, graph=existing)
            before = (root / GRAPH_PATH).read_text(encoding="utf-8")
            self.assertEqual(2, main(["--root", str(root), "rebuild", "--commit"]))
            self.assertEqual(before, (root / GRAPH_PATH).read_text(encoding="utf-8"))

    def test_rebuild_without_commit_does_not_touch_the_live_graph(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp, graph=graph_with([]))
            before = (root / GRAPH_PATH).read_text(encoding="utf-8")
            self.assertEqual(0, main(["--root", str(root), "rebuild"]))
            self.assertEqual(before, (root / GRAPH_PATH).read_text(encoding="utf-8"))
            self.assertTrue((root / "graphify-out" / "graph.rebuilt.json").is_file())


class ExtractionTest(unittest.TestCase):
    def validate(self, extraction, nodes=()):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            chunk = chunks(load_articles(root))[0]
            extraction = dict(extraction)
            extraction.setdefault("chunk_id", chunk["id"])
            extraction.setdefault("chunk_sha256", chunk["sha256"])
            return validate_extraction(extraction, chunk, LabelIndex(nodes))

    def test_accepts_a_complete_extraction(self):
        problems = self.validate(
            {"extracted_by": "claude", "extracted_at": "2026-07-27T00:00:00Z",
             "concepts": [{"label": "無開口樓層", "rationale": "§4 定義"}],
             "edges": [{"source": "第7條", "target": "無開口樓層",
                        "relation": "references", "rationale": "§7 列舉"}]},
            nodes=[{"id": "a7", "label": "第7條"}])
        self.assertEqual([], problems)

    def test_rejects_stale_chunk_sha(self):
        problems = self.validate({"chunk_sha256": "0" * 64, "extracted_by": "c",
                                  "extracted_at": "t", "concepts": [], "edges": []})
        self.assertTrue(any("chunk_sha256" in p for p in problems), problems)

    def test_rejects_unresolvable_endpoint(self):
        problems = self.validate(
            {"extracted_by": "c", "extracted_at": "t", "concepts": [],
             "edges": [{"source": "第999條", "target": "第7條",
                        "relation": "references", "rationale": "x"}]},
            nodes=[{"id": "a7", "label": "第7條"}])
        self.assertTrue(any("第999條" in p for p in problems), problems)

    def test_rejects_unknown_relation(self):
        problems = self.validate(
            {"extracted_by": "c", "extracted_at": "t", "concepts": [],
             "edges": [{"source": "第7條", "target": "第7條",
                        "relation": "免除", "rationale": "x"}]},
            nodes=[{"id": "a7", "label": "第7條"}])
        self.assertTrue(any("relation" in p for p in problems), problems)


class RealRepoTest(unittest.TestCase):
    """對倉庫內真實圖譜行使——id 相容性只有在真資料上才驗得出來。"""

    @classmethod
    def setUpClass(cls):
        if not REAL_GRAPH.is_file():
            raise unittest.SkipTest("倉庫內沒有法規圖譜")
        cls.result = verify(REPO)

    def test_no_node_disappears_and_no_label_changes(self):
        self.assertEqual([], self.result["nodes_removed"])
        self.assertEqual([], self.result["labels_changed"])

    def test_no_edge_is_silently_lost(self):
        self.assertEqual([], self.result["edges_lost"])

    def test_only_the_known_missing_article_is_added(self):
        """現有圖譜漏了第2條（內容為「（刪除）」）——這是預期中的唯一新增。"""
        self.assertEqual(["rules_core_1各類場所消防安全設備設置標準_第2條"],
                         self.result["nodes_added"])

    def test_hyperedges_stay_valid(self):
        self.assertEqual([], self.result["hyperedge_problems"])

    def test_verify_is_green_on_the_shipped_graph(self):
        self.assertTrue(verify_is_green(self.result), self.result)

    def test_every_added_citation_is_backed_by_the_article_text(self):
        """新增的引用必須全部可解釋：字面引用、條號範圍展開、或前條。"""
        import tools.graph_labels as gl
        from tools.regulation_graph_build import _RANGE
        articles = {a["number"]: a for a in load_articles(REPO)}
        _, report = rebuild(REPO)
        self.assertTrue(report["added_citations"])
        for source, target in report["added_citations"]:
            text = gl.normalize_text(articles[source]["markdown"])
            if target in gl.find_article_refs(text) or "前條" in text:
                continue
            expanded = False
            for span in _RANGE.finditer(text):
                ends = gl.find_article_refs(span.group(0), exclude_external=False)
                if len(ends) == 2 and (gl.article_sort_key(ends[0])
                                       <= gl.article_sort_key(target)
                                       <= gl.article_sort_key(ends[1])):
                    expanded = True
                    break
            self.assertTrue(expanded, f"§{source} → §{target} 找不到依據")

    def test_assets_are_all_discovered(self):
        self.assertEqual(38, len(load_assets(REPO)))


if __name__ == "__main__":
    unittest.main()

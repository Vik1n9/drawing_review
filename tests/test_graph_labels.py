import json
import unittest
from pathlib import Path

from tools.graph_labels import (AMBIGUOUS, ARTICLE, CONCEPT_DECLARED, EXACT, MISSING,
                                NORMALIZED, LabelIndex, article_label, article_sort_key,
                                label_key, norm_id, normalize_text, parse_article_ref,
                                parse_cn_number)

REAL_GRAPH = Path(__file__).resolve().parent.parent / "graphify-out" / "graph.json"


def index_with(*labels):
    return LabelIndex({"label": label, "id": f"id_{i}"} for i, label in enumerate(labels))


class ParseArticleRefTests(unittest.TestCase):
    def test_all_writings_of_the_same_article_collapse(self):
        """§19／19／第19條／第 19 條／全形／中文數字都是同一條——寫法差異不該讓邊掉。"""
        for text in ("§19", "19", "第19條", "第 19 條", "第１９條", "第十九條", "  §19  "):
            self.assertEqual("19", parse_article_ref(text), text)
            self.assertEqual("第19條", article_label(text), text)

    def test_sub_article_forms(self):
        for text in ("第146-5條", "第146條之5", "第一百四十六條之五", "146-5"):
            self.assertEqual("146-5", parse_article_ref(text), text)
        self.assertEqual("97-10", parse_article_ref("第九十七條之十"))
        self.assertEqual("22-1", parse_article_ref("§22-1"))

    def test_sub_article_is_not_the_parent_article(self):
        """第19條之1 是另一條——收斂寫法可以，改變指涉不行。"""
        self.assertNotEqual(parse_article_ref("第19條"), parse_article_ref("第19條之1"))

    def test_unparseable_returns_none_rather_than_guessing(self):
        for text in (None, "", "排煙設備", "第X條", "本標準"):
            self.assertIsNone(parse_article_ref(text), text)
            self.assertIsNone(article_label(text), text)

    def test_bare_chinese_numeral_is_not_an_article_ref(self):
        """裸中文數字太容易把內文數字誤讀成條號，寧可解析不到。"""
        self.assertIsNone(parse_article_ref("十九"))

    def test_sort_key_orders_sub_articles_after_parent(self):
        got = sorted(["第146-5條", "第19條", "第146條", "第2條"], key=article_sort_key)
        self.assertEqual(["第2條", "第19條", "第146條", "第146-5條"], got)


class ChineseNumeralTests(unittest.TestCase):
    def test_common_article_numbers(self):
        for text, want in (("十", 10), ("十九", 19), ("九十七", 97),
                           ("一百四十六", 146), ("二百三十九", 239), ("五", 5)):
            self.assertEqual(want, parse_cn_number(text), text)

    def test_digit_by_digit_reading_is_rejected(self):
        """`二三` 不是法條寫法——解析成 23 就是猜。"""
        self.assertIsNone(parse_cn_number("二三"))


class NormalizeTests(unittest.TestCase):
    def test_invisible_characters_do_not_break_matching(self):
        """從 PDF／網頁複製條文常混進零寬字元與 NBSP，肉眼看不出來卻會讓 label 對不上。"""
        self.assertEqual(label_key("第19條"), label_key("第​19 條"))
        self.assertEqual(label_key("第19條"), label_key("第　19　條"))

    def test_halfwidth_parens_normalize_to_fullwidth(self):
        self.assertEqual(label_key("甲類（一）"), label_key("甲類(一)"))

    def test_ascii_case_folds(self):
        self.assertEqual(label_key("README"), label_key("readme"))

    def test_normalize_text_keeps_word_spacing(self):
        self.assertEqual("第 18 條附件", normalize_text("第  18　條附件"))

    def test_norm_id_keeps_cjk_and_collapses_the_rest(self):
        self.assertEqual("甲類一_電影片映演場所", norm_id("甲類一（電影片映演場所）"))
        self.assertEqual("unnamed", norm_id("（）"))


class ResolveTests(unittest.TestCase):
    def test_exact_then_normalized_then_article(self):
        idx = index_with("第19條", "自動撒水設備")
        self.assertEqual(EXACT, idx.resolve("第19條").how)
        self.assertEqual(NORMALIZED, idx.resolve("第 19 條").how)
        self.assertEqual(ARTICLE, idx.resolve("§19").how)
        self.assertEqual(ARTICLE, idx.resolve("第十九條").how)
        # 四條路徑必須指到同一個節點，否則就是「驗證過了但建到別的邊」
        ids = {idx.resolve(t).node_id for t in ("第19條", "第 19 條", "§19", "第十九條")}
        self.assertEqual(1, len(ids))

    def test_no_substring_matching(self):
        """`排煙` 不得解析到 `排煙設備`——模糊比對等於把猜偷渡進圖譜（底線 3）。"""
        idx = index_with("排煙設備")
        self.assertEqual(MISSING, idx.resolve("排煙").how)
        self.assertIsNone(idx.resolve("排煙").node_id)

    def test_sub_article_does_not_resolve_to_parent(self):
        idx = index_with("第19條")
        self.assertEqual(MISSING, idx.resolve("第19條之1").how)

    def test_ambiguous_is_reported_not_silently_picked(self):
        """多候選時不得代選——目前單一法典不會觸發，但行為先定死。"""
        idx = LabelIndex([{"label": "第19條", "id": "a"}, {"label": "第19條", "id": "b"}])
        got = idx.resolve("第19條")
        self.assertEqual(AMBIGUOUS, got.how)
        self.assertIsNone(got.node_id)
        self.assertEqual(["a", "b"], got.candidates)

    def test_declared_concept_resolves_only_after_binding(self):
        idx = index_with("第19條")
        idx.declare("挑空區")
        self.assertEqual(CONCEPT_DECLARED, idx.resolve("挑空區").how)
        self.assertIsNone(idx.resolve("挑空區").node_id)
        idx.bind_declared("挑空區", "concept_挑空區")
        self.assertEqual("concept_挑空區", idx.resolve("挑空區").node_id)

    def test_attachment_label_is_not_indexed_as_an_article(self):
        """附表圖 label 內含條號，但 §18 必須解析到條文而不是圖檔。"""
        idx = LabelIndex([
            {"label": "第 18 條官方完整條文附件，第 1 頁", "id": "img18"},
            {"label": "第18條", "id": "art18"},
        ])
        self.assertEqual("art18", idx.resolve("§18").node_id)

    def test_missing_target_returns_missing(self):
        self.assertEqual(MISSING, index_with("第19條").resolve("第999條").how)
        self.assertEqual(MISSING, index_with("第19條").resolve(None).how)


class RealGraphTests(unittest.TestCase):
    """對倉庫內真實圖譜行使——單元測試的假資料驗不出 label 慣例的真實樣貌。"""

    @classmethod
    def setUpClass(cls):
        if not REAL_GRAPH.is_file():
            raise unittest.SkipTest(f"找不到 {REAL_GRAPH}")
        cls.index = LabelIndex(json.loads(REAL_GRAPH.read_text(encoding="utf-8"))["nodes"])

    def test_every_article_node_is_reachable_by_all_writings(self):
        labels = [l for l in self.index.labels() if article_label(l) == l]
        self.assertGreater(len(labels), 200)
        for label in labels:
            number = parse_article_ref(label)
            for form in (label, f"§{number}", number, f"第 {number} 條"):
                got = self.index.resolve(form)
                self.assertIn(got.how, (EXACT, NORMALIZED, ARTICLE), f"{label} / {form}")
                self.assertEqual(self.index.resolve(label).node_id, got.node_id, form)

    def test_no_ambiguity_in_the_real_graph(self):
        """真實圖譜若已有同名節點，AMBIGUOUS 會讓寫入全面卡住——先確認沒有。"""
        ambiguous = [l for l in self.index.labels() if self.index.resolve(l).how == AMBIGUOUS]
        self.assertEqual([], ambiguous)


if __name__ == "__main__":
    unittest.main()

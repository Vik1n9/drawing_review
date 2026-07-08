import json
import tempfile
import unittest
from pathlib import Path

from tools.regulation_index import build_regulation_index, lookup_related_articles


class RegulationIndexTest(unittest.TestCase):
    def test_builds_article_files_and_keeps_index_lightweight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rules" / "法規"
            source.mkdir(parents=True)
            (source / "第2編-消防設計.md").write_text(
                "\n".join(
                    [
                        "# 各類場所消防安全設備設置標準",
                        "",
                        "> 修正日期：民國 113 年 04 月 24 日",
                        "",
                        "## 第二編 消防設計",
                        "",
                        "### 第 14 條",
                        "",
                        "下列場所應設置滅火器：",
                        "- 一、甲類場所、地下建築物、幼兒園。",
                        "- 二、總樓地板面積在一百五十平方公尺以上之乙、丙、丁類場所。",
                    ]
                ),
                encoding="utf-8",
            )

            index_path = root / "rules" / "regulation_index.json"
            article_dir = root / "rules" / "regulation_articles"
            manifest = build_regulation_index(source, index_path, article_dir)

            self.assertEqual(manifest["regulation_name"], "各類場所消防安全設備設置標準")
            self.assertEqual(manifest["regulation_version"], "民國 113 年 04 月 24 日")
            self.assertEqual(manifest["article_count"], 1)
            self.assertEqual(manifest["by_article"]["14"], ["article-014"])

            article_file = article_dir / "article-014.json"
            self.assertTrue(article_file.exists())
            article = json.loads(article_file.read_text(encoding="utf-8"))
            self.assertEqual(article["legal_basis"], "§14")
            self.assertEqual(article["hierarchy"], ["第二編 消防設計"])
            self.assertIn("滅火器", article["equipment_tags"])
            self.assertIn("下列場所應設置滅火器", article["markdown"])

            saved_index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertNotIn("markdown", saved_index["articles"][0])
            self.assertEqual(saved_index["articles"][0]["path"], "regulation_articles/article-014.json")

    def test_lookup_loads_only_related_article_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rules" / "法規"
            source.mkdir(parents=True)
            (source / "第2編-消防設計.md").write_text(
                "\n".join(
                    [
                        "# 各類場所消防安全設備設置標準",
                        "> 修正日期：民國 113 年 04 月 24 日",
                        "## 第二編 消防設計",
                        "### 第 14 條",
                        "下列場所應設置滅火器：",
                        "### 第 19 條",
                        "下列場所應設置火警自動警報設備：",
                    ]
                ),
                encoding="utf-8",
            )
            index_path = root / "rules" / "regulation_index.json"
            article_dir = root / "rules" / "regulation_articles"
            build_regulation_index(source, index_path, article_dir)

            by_article = lookup_related_articles(index_path, article="§19")
            self.assertEqual([a["id"] for a in by_article], ["article-019"])
            self.assertIn("火警自動警報設備", by_article[0]["markdown"])

            by_equipment = lookup_related_articles(index_path, equipment="滅火器")
            self.assertEqual([a["id"] for a in by_equipment], ["article-014"])
            self.assertIn("滅火器", by_equipment[0]["equipment_tags"])

    def test_lookup_expands_legal_basis_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rules" / "法規"
            source.mkdir(parents=True)
            (source / "第3編-警報設備.md").write_text(
                "\n".join(
                    [
                        "# 各類場所消防安全設備設置標準",
                        "## 第三編 消防安全設計",
                        "### 第二章 警報設備",
                        "##### 第 115 條",
                        "探測器之裝置位置，依下列規定：",
                        "##### 第 116 條",
                        "下列處所免設探測器：",
                        "##### 第 117 條",
                        "偵煙式探測器或火焰式探測器，不得設於下列處所：",
                    ]
                ),
                encoding="utf-8",
            )
            index_path = root / "rules" / "regulation_index.json"
            article_dir = root / "rules" / "regulation_articles"
            build_regulation_index(source, index_path, article_dir)

            articles = lookup_related_articles(index_path, article="§115-§117")
            self.assertEqual([a["id"] for a in articles], ["article-115", "article-116", "article-117"])


if __name__ == "__main__":
    unittest.main()

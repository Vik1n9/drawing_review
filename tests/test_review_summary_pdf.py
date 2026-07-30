import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.review_summary_pdf import (
    extract_case_info,
    extract_mixed_use,
    extract_annotation_stats,
    render_report,
    main,
)


def sample_case():
    return {
        "case_name": "測試案",
        "regulation_version": "測試版 v1",
        "use_permit": {
            "permit_no": {"value": "測使字第001號", "confidence": "high", "source": "manual"},
            "total_floor_area": {"value": 900, "confidence": "high", "source": "manual"},
        },
        "interior_renovation": {
            "floors": {"value": ["3F"], "confidence": "high", "source": "manual"},
            "area": {"value": 350, "confidence": "high", "source": "manual"},
            "post_renovation_use": {"value": "乙7", "confidence": "high", "source": "manual"},
        },
        "floors": [
            {"floor": "B1", "area": {"value": 300, "confidence": "high"},
             "floor_position": {"value": "basement", "confidence": "high"},
             "use_category": {"value": "丙1", "label": "停車空間", "legal_basis": "§12 第3款第1目",
                              "confidence": "high"}},
            {"floor": "3F", "area": {"value": 350, "confidence": "high"},
             "floor_position": {"value": "ordinary", "confidence": "high"},
             "use_category": {"value": "乙7", "label": "集合住宅", "legal_basis": "§12 第2款第7目",
                              "confidence": "high"}},
        ],
        "building": {
            "mixed_use_assessment": {
                "is_mixed_use": True,
                "category_candidate": "戊1",
                "confidence": "high",
                "source": "manual",
            }
        },
    }


def sample_results():
    return {
        "case_name": "測試案",
        "date": "2026-07-31",
        "regulation_version": "測試版 v1",
        "article_range": "§14~§31（逐條窮舉）",
        "not_coded_articles": ["§26"],
        "items": [
            {"article": "§14", "equipment": "滅火器", "floor": "1F",
             "requirement": "甲類場所應設", "status": "pass",
             "finding": "符合", "rule_status": "coded"},
            {"article": "§15", "equipment": "室內消防栓", "floor": "B1",
             "requirement": "地下層應設", "status": "fail",
             "finding": "法定應設而圖面未見", "rule_status": "coded"},
            {"article": "§19", "equipment": "火警自動警報設備", "floor": "3F",
             "requirement": "應設", "status": "manual",
             "finding": "需人工判讀：樓層屬性未確認｜本參數尚未逐條確認", "rule_status": "coded"},
            {"article": "§26", "equipment": "連結送水管", "floor": "—",
             "requirement": "未索引", "status": "manual",
             "finding": "⚪ 需人工判讀（規則未入庫）", "rule_status": "not_coded"},
        ],
    }


def sample_annotations():
    return {
        "case_name": "測試案",
        "annotations": [
            {"issue_id": 1, "severity": "重大缺失", "label": "缺室內消防栓",
             "note": "B1 應設室內消防栓，圖面未見（§15）", "position_confidence": "high"},
            {"issue_id": 2, "severity": "一般缺失", "label": "探測器不足",
             "note": "3F 探測器應設 6 只，圖面僅 4 只", "position_confidence": "low"},
            {"issue_id": 3, "severity": "配置疑義", "label": "滅火器步行距離",
             "note": "需量測步行距離是否 ≤20m", "position_confidence": "high"},
        ],
    }


class ExtractCaseInfoTest(unittest.TestCase):
    def test_basic_fields(self):
        info = extract_case_info(sample_case())
        self.assertEqual(info["case_name"], "測試案")
        self.assertEqual(info["permit_no"], "測使字第001號")
        self.assertEqual(info["renovation_floors"], "3F")
        self.assertEqual(info["renovation_area"], "350 m²")
        self.assertEqual(info["floor_count"], 2)
        self.assertEqual(info["total_area"], "650 m²")

    def test_missing_permit_shows_manual(self):
        case = {"floors": []}
        info = extract_case_info(case)
        self.assertIn("⚪", info["permit_no"])
        self.assertEqual(info["floor_count"], 0)


class ExtractMixedUseTest(unittest.TestCase):
    def test_mixed_use_detected(self):
        mu = extract_mixed_use(sample_case())
        self.assertEqual(mu["verdict"], "戊1 複合用途建築物")
        self.assertEqual(len(mu["floor_uses"]), 2)
        self.assertEqual(mu["floor_uses"][0]["floor"], "B1")

    def test_single_use(self):
        case = sample_case()
        case["building"]["mixed_use_assessment"]["is_mixed_use"] = False
        mu = extract_mixed_use(case)
        self.assertEqual(mu["verdict"], "單一用途建築物")

    def test_unconfirmed_shows_manual(self):
        case = sample_case()
        case["building"]["mixed_use_assessment"]["is_mixed_use"] = None
        mu = extract_mixed_use(case)
        self.assertIn("⚪", mu["verdict"])


class ExtractAnnotationStatsTest(unittest.TestCase):
    def test_counts_by_severity(self):
        stats = extract_annotation_stats(sample_annotations())
        self.assertEqual(stats["重大缺失"], 1)
        self.assertEqual(stats["一般缺失"], 1)
        self.assertEqual(stats["配置疑義"], 1)

    def test_empty_annotations(self):
        self.assertEqual(extract_annotation_stats(None), {})
        self.assertEqual(extract_annotation_stats({"annotations": []}), {})


class RenderReportTest(unittest.TestCase):
    def test_report_contains_all_sections(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("一、案件基本資料", html)
        self.assertIn("二、複合用途判定摘要", html)
        self.assertIn("三、應設設備檢核統計", html)
        self.assertIn("四、檢核結果明細", html)
        self.assertIn("六、免責聲明", html)
        # 五、缺失摘要 absent when no annotations
        self.assertNotIn("五、缺失摘要", html)

    def test_report_with_annotations_includes_section_five(self):
        html = render_report(sample_case(), sample_results(), sample_annotations())
        self.assertIn("五、缺失摘要", html)
        self.assertIn("缺室內消防栓", html)
        self.assertIn("position_confidence: low", html)

    def test_report_shows_case_info(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("測試案", html)
        self.assertIn("測使字第001號", html)
        self.assertIn("650 m²", html)

    def test_report_shows_check_results(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("§14", html)
        self.assertIn("§15", html)
        self.assertIn("不符合", html)

    def test_disclaimer_present(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("AI 輔助審查聲明", html)
        self.assertIn("最終判斷與法律責任歸屬專業消防人員", html)
        self.assertIn("判斷慣例警語", html)

    def test_not_coded_articles_in_disclaimer(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("規則未入庫條號", html)
        self.assertIn("§26", html)

    def test_print_css_included(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertIn("@media print", html)
        self.assertIn("@page", html)

    def test_valid_html_structure(self):
        html = render_report(sample_case(), sample_results(), None)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("</html>", html)
        self.assertIn('lang="zh-Hant"', html)


class CliTest(unittest.TestCase):
    def test_main_writes_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_path = Path(tmp) / "case.json"
            case_path.write_text(json.dumps(sample_case(), ensure_ascii=False), encoding="utf-8")
            results_path = Path(tmp) / "check_results.json"
            results_path.write_text(json.dumps(sample_results(), ensure_ascii=False), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "--case", str(case_path),
                    "--results", str(results_path),
                ]), 0)

            output_path = Path(tmp) / "測試案-審查摘要報告.html"
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("測試案", content)
            self.assertIn("審查摘要報告", content)

    def test_main_with_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_path = Path(tmp) / "case.json"
            case_path.write_text(json.dumps(sample_case(), ensure_ascii=False), encoding="utf-8")
            results_path = Path(tmp) / "check_results.json"
            results_path.write_text(json.dumps(sample_results(), ensure_ascii=False), encoding="utf-8")
            ann_path = Path(tmp) / "annotations.json"
            ann_path.write_text(json.dumps(sample_annotations(), ensure_ascii=False), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main([
                    "--case", str(case_path),
                    "--results", str(results_path),
                    "--annotations", str(ann_path),
                ]), 0)

            output_path = Path(tmp) / "測試案-審查摘要報告.html"
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("缺失摘要", content)
            self.assertIn("3 處", out.getvalue())

    def test_custom_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_path = Path(tmp) / "case.json"
            case_path.write_text(json.dumps(sample_case(), ensure_ascii=False), encoding="utf-8")
            results_path = Path(tmp) / "check_results.json"
            results_path.write_text(json.dumps(sample_results(), ensure_ascii=False), encoding="utf-8")
            custom_out = Path(tmp) / "custom-report.html"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([
                    "--case", str(case_path),
                    "--results", str(results_path),
                    "--output", str(custom_out),
                ]), 0)

            self.assertTrue(custom_out.exists())


if __name__ == "__main__":
    unittest.main()

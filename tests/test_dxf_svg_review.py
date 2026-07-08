import contextlib
import io
import json
import tempfile
import unittest
import warnings
from pathlib import Path

from tools.dxf_svg_review import ReviewInputError, default_output_path, main


class DxfSvgReviewTest(unittest.TestCase):
    def run_main_quietly(self, args):
        with contextlib.redirect_stdout(io.StringIO()):
            main(args)

    def write_case_files(self, root, *, low_confidence=False):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"ezdxf\..*")
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pyparsing\..*")
            import ezdxf

        dxf_path = root / "1f.dxf"
        doc = ezdxf.new()
        modelspace = doc.modelspace()
        modelspace.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALL"})
        modelspace.add_lwpolyline(
            [(0, 0), (100, 0), (100, 80), (0, 80)],
            close=True,
            dxfattribs={"layer": "ROOM"},
        )
        modelspace.add_text("1F", dxfattribs={"layer": "NOTE", "height": 5}).set_placement((10, 20))
        doc.saveas(dxf_path)
        output_html = root / "示範案件-圖面審查.html"
        annotations_path = root / "annotations.json"
        annotations_path.write_text(
            json.dumps(
                {
                    "case_name": "示範案件",
                    "output_html": str(output_html),
                    "source_drawings": [
                        {
                            "drawing_id": "1F",
                            "path": str(dxf_path),
                            "floor": "1F",
                            "unit": "mm",
                        }
                    ],
                    "annotations": [
                        {
                            "issue_id": 1,
                            "drawing_id": "1F",
                            "bbox": [5, 5, 60, 40],
                            "label": "滅火器數量不足",
                            "note": "1F 應設滅火效能值 5，圖面僅 2 具（§14、§31）",
                            "severity": "一般缺失",
                            "position_confidence": "low" if low_confidence else "medium",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return annotations_path, output_html

    def test_generates_svg_review_html_with_issue_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            annotations_path, output_html = self.write_case_files(Path(tmp))

            self.run_main_quietly(["--annotations", str(annotations_path)])

            html = output_html.read_text(encoding="utf-8")
            self.assertIn("<svg", html)
            self.assertIn('data-drawing-id="1F"', html)
            self.assertIn('data-issue-id="1"', html)
            self.assertIn('id="svg-issue-1"', html)
            self.assertIn('id="review-list"', html)
            self.assertIn("滅火器數量不足", html)
            self.assertIn("一般缺失", html)
            self.assertIn("1F 應設滅火效能值 5", html)
            self.assertIn("selectIssue", html)
            self.assertIn("viewBox=", html)

    def test_low_confidence_annotations_show_position_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            annotations_path, output_html = self.write_case_files(Path(tmp), low_confidence=True)

            self.run_main_quietly(["--annotations", str(annotations_path)])

            html = output_html.read_text(encoding="utf-8")
            self.assertIn("部分圈選位置為 AI 推定", html)
            self.assertIn("以問題清單文字說明為準", html)

    def test_missing_dxf_path_raises_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            annotations_path = root / "annotations.json"
            annotations_path.write_text(
                json.dumps(
                    {
                        "case_name": "示範案件",
                        "output_html": str(root / "out.html"),
                        "source_drawings": [
                            {"drawing_id": "MISSING", "path": str(root / "missing.dxf")}
                        ],
                        "annotations": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ReviewInputError, "找不到 DXF 圖面"):
                main(["--annotations", str(annotations_path)])

    def test_output_html_under_output_directory_resolves_from_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            annotations_path = Path(tmp) / "output" / "示範案件-20260708" / "annotations.json"
            annotations_path.parent.mkdir(parents=True)
            spec = {"case_name": "示範案件", "output_html": "output/示範案件-20260708/示範案件-圖面審查.html"}

            out = default_output_path(spec, annotations_path)

            self.assertEqual(out, Path.cwd() / "output/示範案件-20260708/示範案件-圖面審查.html")


if __name__ == "__main__":
    unittest.main()

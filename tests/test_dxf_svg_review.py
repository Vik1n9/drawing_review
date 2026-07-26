import contextlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
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

    def test_produces_deliverable_without_ezdxf(self):
        """本倉庫對目標使用者的核心承諾：什麼都沒裝也產得出交付物1。

        使用者多半只裝了一個 AI 桌面版就開始用，沙盒讓 pip 裝不起來。
        DXF 是純文字格式，交付物1 不該卡在第三方套件上。
        """
        with tempfile.TemporaryDirectory() as tmp:
            # fixture 仍用 ezdxf 產生（測試環境有），但解析時要當作它不存在
            annotations_path, output_html = self.write_case_files(Path(tmp))

            with unittest.mock.patch.dict(sys.modules, {"ezdxf": None}):
                with self.assertRaises(ImportError):
                    import ezdxf  # noqa: F401  確認封鎖真的生效
                self.run_main_quietly(["--annotations", str(annotations_path)])

            html = output_html.read_text(encoding="utf-8")
            self.assertIn("<svg", html)
            self.assertIn('data-drawing-id="1F"', html)
            self.assertIn("滅火器數量不足", html)

    def test_stdlib_and_ezdxf_backends_agree(self):
        """兩條解析路徑必須產出同一份 HTML，否則零安裝環境會拿到不同結果。"""
        from tools.dxf_svg_review import collect_dxf_entities, collect_dxf_entities_ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            self.write_case_files(Path(tmp))
            dxf_path = str(Path(tmp) / "1f.dxf")

            self.assertEqual(collect_dxf_entities_ezdxf(dxf_path),
                             collect_dxf_entities(dxf_path))

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
            annotations_path = Path(tmp) / "output" / "annotations.json"
            annotations_path.parent.mkdir(parents=True)
            spec = {"case_name": "示範案件", "output_html": "output/示範案件-圖面審查.html"}

            out = default_output_path(spec, annotations_path)

            self.assertEqual(out, Path.cwd() / "output/示範案件-圖面審查.html")


if __name__ == "__main__":
    unittest.main()

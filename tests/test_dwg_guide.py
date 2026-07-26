"""tools/dwg_guide.py 的測試。

DWG 是二進位專有格式，沒有任何 AI 讀得了，而轉檔器在目標使用者的
環境幾乎必然裝不起來。所以本工具的主要交付物是**明確的操作引導**，
不是轉檔——「印出怎麼做」就是成功，不是失敗。
"""

import contextlib
import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tools import dwg_guide
from tools.dwg_guide import EXIT_NEEDS_ACTION, EXIT_OK, main

DWG_BYTES = b"AC1032" + b"\x00" * 128
PDF_BYTES = b"%PDF-1.5\n" + b"\x00" * 64


def run(args):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(args)
    return code, buffer.getvalue()


def no_converters():
    """假裝機器上什麼轉檔器都沒有——目標使用者的常態。"""
    return unittest.mock.patch.object(dwg_guide, "detect_backends", return_value=[])


class DwgGuideFormatTest(unittest.TestCase):
    """副檔名會說謊，一律以 magic bytes 認定。"""

    def test_detects_dwg_by_magic_even_when_named_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "圖面.pdf"
            path.write_bytes(DWG_BYTES)

            with no_converters():
                code, out = run(["check", "--path", tmp, "--format", "json"])

            payload = json.loads(out)
            found = payload["files"][0]
            self.assertEqual("dwg", found["format"])
            self.assertTrue(found["extension_mismatch"])
            self.assertEqual(EXIT_NEEDS_ACTION, code)

    def test_pdf_named_dwg_is_not_treated_as_drawing(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "平面圖.dwg").write_bytes(PDF_BYTES)

            with no_converters():
                code, out = run(["check", "--path", tmp, "--format", "json"])

            payload = json.loads(out)
            self.assertEqual("pdf", payload["files"][0]["format"])
            self.assertEqual([], payload["dwg_files"])
            self.assertEqual(EXIT_OK, code)

    def test_reports_dwg_version_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.dwg").write_bytes(b"AC1015" + b"\x00" * 32)

            with no_converters():
                _, out = run(["check", "--path", tmp, "--format", "json"])

            self.assertIn("2000", json.loads(out)["files"][0]["version"])


class DwgGuideGuidanceTest(unittest.TestCase):
    """沒有轉檔器時，引導本身就是交付物。"""

    def test_prints_save_as_dxf_steps_when_no_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "平面圖.dwg").write_bytes(DWG_BYTES)

            with no_converters():
                code, out = run(["check", "--path", tmp])

            self.assertEqual(EXIT_NEEDS_ACTION, code)
            self.assertIn("DXFOUT", out)
            self.assertIn("另存", out)
            # 版本與編碼是實務上最常踩的兩個雷，必須講到
            self.assertIn("2013", out)
            self.assertIn("二進位", out)
            # 各家 CAD 都要點到，使用者未必用 AutoCAD
            for cad in ("AutoCAD", "ZWCAD", "BricsCAD", "GstarCAD"):
                self.assertIn(cad, out)

    def test_no_dwg_found_is_plain_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "平面圖.dxf").write_text("  0\nSECTION\n", encoding="utf-8")

            with no_converters():
                code, out = run(["check", "--path", tmp])

            self.assertEqual(EXIT_OK, code)
            self.assertNotIn("DXFOUT", out)

    def test_missing_path_raises_domain_error(self):
        with self.assertRaises(dwg_guide.DwgGuideError):
            main(["check", "--path", "/nonexistent/nope"])


class DwgGuideBackendTest(unittest.TestCase):
    """已安裝的轉檔器不浪費，但絕不主動安裝。"""

    def test_uses_existing_converter_when_present(self):
        backend = dwg_guide.Backend(
            name="dwg2dxf", executable="/usr/bin/dwg2dxf", licence_note=None)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "平面圖.dwg").write_bytes(DWG_BYTES)

            with unittest.mock.patch.object(dwg_guide, "detect_backends", return_value=[backend]):
                code, out = run(["check", "--path", tmp, "--format", "json"])

            payload = json.loads(out)
            self.assertEqual("dwg2dxf", payload["backends"][0]["name"])
            # 有轉檔器就不是待處理狀態
            self.assertEqual(EXIT_OK, code)

    def test_oda_backend_carries_licence_warning(self):
        backend = dwg_guide.Backend(
            name="ODAFileConverter", executable="/opt/oda/ODAFileConverter",
            licence_note="非 ODA 會員僅限非商業用途")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "平面圖.dwg").write_bytes(DWG_BYTES)

            with unittest.mock.patch.object(dwg_guide, "detect_backends", return_value=[backend]):
                _, out = run(["check", "--path", tmp])

            self.assertIn("非商業", out)

    def test_libredwg_preferred_over_oda(self):
        """LibreDWG 是 GPLv3 可商用，ODA 有非商用限制——順序不能反。"""
        oda = dwg_guide.Backend("ODAFileConverter", "/opt/oda", "非 ODA 會員僅限非商業用途")
        libre = dwg_guide.Backend("dwg2dxf", "/usr/bin/dwg2dxf", None)

        self.assertEqual("dwg2dxf", dwg_guide.preferred([oda, libre]).name)


class DwgGuideConvertTest(unittest.TestCase):
    def test_convert_refuses_to_write_into_input(self):
        """底線 4：input/ 只讀，產出一律寫 output/。"""
        with self.assertRaises(dwg_guide.DwgGuideError) as ctx:
            main(["convert", "--input", "input/案.dwg", "--output", "input/案.dxf"])
        self.assertIn("input/", str(ctx.exception))

    def test_convert_without_backend_gives_guidance_not_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "平面圖.dwg"
            source.write_bytes(DWG_BYTES)

            with no_converters():
                with self.assertRaises(dwg_guide.DwgGuideError) as ctx:
                    main(["convert", "--input", str(source),
                          "--output", str(Path(tmp) / "out.dxf")])

            self.assertIn("DXFOUT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

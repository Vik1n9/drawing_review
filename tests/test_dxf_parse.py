"""tools/dxf_parse.py 的測試：零相依 DXF 解析必須與 ezdxf 產出一致。

差分測試是本檔的核心把關手段——ezdxf 當作參考實作（測試預言），
但執行環境不需要它。CI 裝得起 ezdxf，目標使用者的機器裝不起來，
兩邊都必須得到同一份結果。
"""

import contextlib
import io
import tempfile
import unittest
import warnings
from pathlib import Path

from tools.dxf_parse import DxfParseError, main, parse


def build_dxf(entities_body, *, acadver="AC1027", codepage=None, encoding="utf-8"):
    """手工組一份最小 ASCII DXF，供編碼與邊界案例測試使用。

    group code 的縮排刻意不一致（有的補空白、有的不補），
    真實 CAD 匯出就長這樣，解析器必須容忍。
    """
    header = ["  0", "SECTION", "  2", "HEADER", "  9", "$ACADVER", "  1", acadver]
    if codepage:
        header += ["9", "$DWGCODEPAGE", "3", codepage]
    header += ["  0", "ENDSEC"]
    body = ["  0", "SECTION", "  2", "ENTITIES"] + entities_body + ["  0", "ENDSEC"]
    text = "\r\n".join(header + body + ["  0", "EOF"]) + "\r\n"
    return text.encode(encoding)


LINE_BODY = ["0", "LINE", "8", "WALL", "10", "0.0", "20", "0.0", "11", "100.0", "21", "0.0"]


class DxfParseDifferentialTest(unittest.TestCase):
    """stdlib 解析結果必須與 ezdxf 逐欄相同。"""

    def build_reference_dxf(self, path):
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"ezdxf\..*")
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"pyparsing\..*")
            import ezdxf

        doc = ezdxf.new()
        msp = doc.modelspace()
        msp.add_line((0, 0), (100, 0), dxfattribs={"layer": "WALL"})
        msp.add_lwpolyline(
            [(0, 0), (100, 0), (100, 80), (0, 80)], close=True, dxfattribs={"layer": "ROOM"}
        )
        msp.add_circle((50, 40), 5, dxfattribs={"layer": "EQUIP"})
        msp.add_arc((20, 20), 10, 0, 90, dxfattribs={"layer": "DOOR"})
        msp.add_text("1F", dxfattribs={"layer": "NOTE", "height": 5}).set_placement((10, 20))
        msp.add_mtext("包廂區", dxfattribs={"layer": "NOTE", "char_height": 3}).set_location((30, 60))
        polyline = msp.add_polyline2d(
            [(0, 0), (10, 0), (10, 10)], close=False, dxfattribs={"layer": "OLDPOLY"}
        )
        self.assertTrue(polyline)  # 確保 POLYLINE/VERTEX/SEQEND 這條路徑有被涵蓋
        doc.saveas(path)

    def test_matches_ezdxf_entity_for_entity(self):
        from tools.dxf_svg_review import collect_dxf_entities_ezdxf

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ref.dxf"
            self.build_reference_dxf(path)

            mine = parse(path)
            theirs = collect_dxf_entities_ezdxf(path)

            self.assertEqual(theirs["layers"], mine["layers"])
            self.assertEqual(theirs["bbox"], mine["bbox"])
            self.assertEqual(len(theirs["entities"]), len(mine["entities"]))
            # 實體順序也必須一致——SVG 疊圖順序依賴它
            for expected, actual in zip(theirs["entities"], mine["entities"]):
                self.assertEqual(expected, actual)


class DxfParseEncodingTest(unittest.TestCase):
    """台灣案件的圖層名與文字標註幾乎必然是中文，編碼判錯就整份亂碼。"""

    def test_reads_cp950_when_dwgcodepage_says_ansi_950(self):
        body = ["0", "TEXT", "8", "牆線", "10", "1.0", "20", "2.0", "40", "2.5", "1", "包廂區"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "big5.dxf"
            path.write_bytes(build_dxf(body, acadver="AC1015", codepage="ANSI_950", encoding="cp950"))

            result = parse(path)

            self.assertEqual(["牆線"], result["layers"])
            self.assertEqual("包廂區", result["entities"][0]["text"])

    def test_reads_utf8_for_r2007_and_newer(self):
        body = ["0", "TEXT", "8", "牆線", "10", "1.0", "20", "2.0", "40", "2.5", "1", "包廂區"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "utf8.dxf"
            path.write_bytes(build_dxf(body, acadver="AC1021", encoding="utf-8"))

            result = parse(path)

            self.assertEqual(["牆線"], result["layers"])
            self.assertEqual("包廂區", result["entities"][0]["text"])

    def test_unescapes_unicode_escape_sequences(self):
        r"""R2004 以前的非 ASCII 可能寫成 \U+XXXX。"""
        body = ["0", "TEXT", "8", "0", "10", "1.0", "20", "2.0", "40", "2.5",
                "1", r"\U+5305\U+5EC2\U+5340"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "escaped.dxf"
            path.write_bytes(build_dxf(body, acadver="AC1015", encoding="ascii"))

            result = parse(path)

            self.assertEqual("包廂區", result["entities"][0]["text"])


class DxfParseDegradationTest(unittest.TestCase):
    """壞掉的輸入必須明確報錯，不得靜默產出空圖。"""

    def test_binary_dxf_raises_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary.dxf"
            path.write_bytes(b"AutoCAD Binary DXF\r\n\x1a\x00" + b"\x00" * 64)

            with self.assertRaises(DxfParseError) as ctx:
                parse(path)

            message = str(ctx.exception)
            self.assertIn("二進位", message)
            # 必須告訴使用者怎麼脫困，而不是只說失敗
            self.assertIn("DXF", message)

    def test_unsupported_entities_go_to_warnings_not_silently_dropped(self):
        body = LINE_BODY + ["0", "HATCH", "8", "FILL", "0", "INSERT", "8", "BLK"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            self.assertEqual(1, len(result["entities"]))
            joined = "\n".join(result["warnings"])
            self.assertIn("HATCH", joined)
            self.assertIn("INSERT", joined)

    def test_empty_entities_section_uses_blank_viewbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.dxf"
            path.write_bytes(build_dxf([]))

            result = parse(path)

            self.assertEqual([], result["entities"])
            self.assertEqual([0.0, 0.0, 100.0, 100.0], result["bbox"])
            self.assertTrue(any("空白檢視框" in w for w in result["warnings"]))

    def test_paperspace_entities_are_excluded(self):
        """ezdxf 的 modelspace() 不含圖紙空間實體，stdlib 版必須一致。"""
        body = LINE_BODY + [
            "0", "LINE", "8", "PAPER", "67", "1",
            "10", "0.0", "20", "0.0", "11", "5.0", "21", "5.0",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            self.assertEqual(1, len(result["entities"]))
            self.assertEqual(["WALL"], result["layers"])

    def test_missing_file_raises_domain_error(self):
        with self.assertRaises(DxfParseError):
            parse(Path("/nonexistent/nope.dxf"))


class DxfParseCliTest(unittest.TestCase):
    def test_cli_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cli.dxf"
            path.write_bytes(build_dxf(LINE_BODY))

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(["--input", str(path), "--format", "json"])

            self.assertEqual(0, code)
            self.assertIn("WALL", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

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


def build_dxf_bytes(entities_body, *, acadver="AC1009", encoding="cp950", extra_header_bytes=b""):
    """組一份可夾雜壞位元組的 DXF。

    真實案件的 R12 圖面常在 LTYPE 說明字串裡夾帶造字區位元組，
    Python 的 cp950 codec 不收——必須確認那不會毀掉整份圖層名。
    """
    header = ["  0", "SECTION", "  2", "HEADER", "  9", "$ACADVER", "  1", acadver, "  0", "ENDSEC"]
    body = ["  0", "SECTION", "  2", "ENTITIES"] + entities_body + ["  0", "ENDSEC"]
    head_text = "\r\n".join(header) + "\r\n"
    tail_text = "\r\n".join(body + ["  0", "EOF"]) + "\r\n"
    # extra_header_bytes 必須自成完整的 group code 對，否則後續全部錯位
    return head_text.encode(encoding) + extra_header_bytes + tail_text.encode(encoding)


# LTYPE 說明字串裡的造字區位元組：cp950 codec 會拒收，但與審圖無關
BIG5_UDA_TAG = b"  3\r\n2SASEN29 ______\x81\x40__  __\r\n"


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

        # 消防設備符號都是圖塊——差分測試必須涵蓋 INSERT，否則兩條路徑的
        # 不一致（如圖層漏收）永遠測不出來
        block = doc.blocks.new(name="SD-1")
        block.add_circle((0, 0), 2)
        msp.add_blockref("SD-1", (70, 30), dxfattribs={"layer": "1_偵煙探測器"})

        # 不支援的實體：其圖層仍必須出現在兩邊的 layers 清單裡
        msp.add_solid([(0, 0), (1, 0), (1, 1), (0, 1)], dxfattribs={"layer": "FILL"})
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

    def test_r12_big5_survives_a_single_undecodable_byte_pair(self):
        """真實案件回歸：R12＋無 $DWGCODEPAGE＋造字區位元組。

        input/範例/楷得立消防設備圖說.dxf 就是這個形態。全檔只有 2 個位元組
        cp950 解不了，卻讓整份正確解碼被丟棄、20 個中文圖層名全變亂碼。
        """
        body = ["0", "TEXT", "8", "1_偵煙探測器", "10", "1.0", "20", "2.0", "40", "2.5", "1", "包廂區"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r12.dxf"
            path.write_bytes(build_dxf_bytes(body, extra_header_bytes=BIG5_UDA_TAG))

            result = parse(path)

            self.assertEqual(["1_偵煙探測器"], result["layers"])
            self.assertEqual("包廂區", result["entities"][0]["text"])
            self.assertNotIn("�", "".join(result["layers"]))

    def test_pre_r2007_without_codepage_prefers_cp950(self):
        """無 $DWGCODEPAGE 的舊版圖面，繁中案件實務上就是 cp950。"""
        body = ["0", "TEXT", "8", "牆線", "10", "1.0", "20", "2.0", "40", "2.5", "1", "包廂區"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nocodepage.dxf"
            path.write_bytes(build_dxf_bytes(body, acadver="AC1015"))

            result = parse(path)

            self.assertEqual(["牆線"], result["layers"])

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
        body = LINE_BODY + ["0", "HATCH", "8", "FILL", "0", "SOLID", "8", "BLK"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mixed.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            self.assertEqual(1, len(result["entities"]))
            joined = "\n".join(result["warnings"])
            self.assertIn("HATCH", joined)
            self.assertIn("SOLID", joined)

    def test_unsupported_entity_layers_still_reach_the_layer_list(self):
        """圖層清單是判讀設備圖層的依據，不能因為實體型別不支援就漏掉。

        ezdxf 參考實作（dxf_svg_review.collect_dxf_entities_ezdxf）本來就先收圖層
        再分派型別，stdlib 版必須一致。
        """
        body = LINE_BODY + ["0", "HATCH", "8", "FILL"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layers.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            self.assertEqual(["FILL", "WALL"], result["layers"])

    def test_repeated_unsupported_entities_are_summarised_not_repeated(self):
        """227 個 INSERT 曾灌出 227 條一模一樣的警告，整批塞進交付物1。"""
        body = list(LINE_BODY)
        for _ in range(30):
            body += ["0", "HATCH", "8", "FILL"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spam.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            hatch = [w for w in result["warnings"] if "HATCH" in w]
            self.assertEqual(1, len(hatch))
            self.assertIn("30", hatch[0])

    def test_insert_is_parsed_so_equipment_symbols_can_be_counted(self):
        """消防設備符號在真實圖面上都是圖塊；丟掉 INSERT 就數不出實設數量。"""
        body = LINE_BODY + [
            "0", "INSERT", "8", "1_偵煙探測器", "2", "SD-1",
            "10", "50.0", "20", "60.0", "50", "90.0",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "insert.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            inserts = [e for e in result["entities"] if e["type"] == "insert"]
            self.assertEqual(1, len(inserts))
            self.assertEqual("SD-1", inserts[0]["block"])
            self.assertEqual((50.0, 60.0), inserts[0]["insert"])
            self.assertIn("1_偵煙探測器", result["layers"])

    def test_arc_bbox_follows_the_sweep_not_the_full_circle(self):
        """真實案件回歸：極扁弧用 center±radius 會把 bbox 撐大數百倍。

        input/範例 的圖面有 r=68563 的弧，害 SVG viewBox 面積放大 843 倍，
        平面圖縮成一個點。
        """
        body = [
            "0", "ARC", "8", "DOOR", "10", "0.0", "20", "0.0", "40", "100.0",
            "50", "0.0", "51", "90.0",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arc.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            # 0°→90° 只掃第一象限：bbox 應為 (0,0)-(100,100)，而非 (-100,-100)-(100,100)
            for expected, actual in zip([0.0, 0.0, 100.0, 100.0], result["bbox"]):
                self.assertAlmostEqual(expected, actual, places=6)

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

    def test_anonymous_blocks_are_skipped_not_counted_as_equipment(self):
        """*U22／*X96 這種匿名圖塊是 CAD 內部產物（R12 的 HATCH 就長這樣）。

        插入點一律在原點，既不是設備符號，還會把 bbox 拉到原點。
        """
        body = LINE_BODY + [
            "0", "INSERT", "8", "0", "2", "*X96", "10", "0.0", "20", "0.0",
            "0", "INSERT", "8", "1_滅火器", "2", "滅火器", "10", "50.0", "20", "10.0",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "anon.dxf"
            path.write_bytes(build_dxf(body))

            result = parse(path)

            inserts = [e for e in result["entities"] if e["type"] == "insert"]
            self.assertEqual(["滅火器"], [e["block"] for e in inserts])
            self.assertTrue(any("匿名圖塊" in w for w in result["warnings"]))

    def test_geometry_far_outside_declared_extents_is_flagged_not_clipped(self):
        """圖框外的殘留圖元會讓 SVG 縮很小，但不得無聲裁掉——可能正是缺失本身。"""
        from tools.dxf_parse import extent_mismatch_warning

        self.assertEqual([], extent_mismatch_warning([0, 0, 100, 100], [0, 0, 90, 90]))
        self.assertEqual([], extent_mismatch_warning([0, 0, 100, 100], None))
        flagged = extent_mismatch_warning([0, 0, 1000, 1000], [0, 0, 100, 100])
        self.assertEqual(1, len(flagged))
        self.assertIn("需人工判讀", flagged[0])

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

#!/usr/bin/env python3
"""零相依 ASCII DXF 解析 for fire-review.

本倉庫的使用者多半是消防設備師，機器上只裝了一個 AI 桌面版就開始用；
受安全限制與沙盒影響，`pip install` 往往裝不起來。DXF 既然是純文字的
group code 格式，就沒有理由讓交付物1（圖面標註）卡在第三方套件上。

Zero external dependencies — Python stdlib only。
`ezdxf` 在本倉庫已降級為選用：只有二進位 DXF 與異常結構才需要它。

Usage:
    python3 tools/dxf_parse.py --input input/範例大樓/平面圖.dxf
    python3 tools/dxf_parse.py --input 平面圖.dxf --format json

回傳結構與 tools/dxf_svg_review.py 的 collect_dxf_entities() 完全相同：
    {"entities": [...], "warnings": [...], "bbox": [...], "layers": [...]}
一致性由 tests/test_dxf_parse.py 的差分測試（對照 ezdxf）把關。
"""

import argparse
import html
import json
import math
import re
import sys
from pathlib import Path

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

BINARY_SENTINEL = b"AutoCAD Binary DXF\r\n\x1a\x00"

# R2007（AC1021）起 DXF 一律 UTF-8；之前的版本看 $DWGCODEPAGE
FIRST_UTF8_VERSION = "AC1021"

# $DWGCODEPAGE 值 → Python codec。繁中案件實務上幾乎都是 ANSI_950。
CODEPAGES = {
    "ANSI_874": "cp874", "ANSI_932": "cp932", "ANSI_936": "gbk",
    "ANSI_949": "cp949", "ANSI_950": "cp950", "ANSI_1250": "cp1250",
    "ANSI_1251": "cp1251", "ANSI_1252": "cp1252", "ANSI_1253": "cp1253",
    "ANSI_1254": "cp1254", "ANSI_1255": "cp1255", "ANSI_1256": "cp1256",
    "ANSI_1257": "cp1257", "ANSI_1258": "cp1258",
}

SUPPORTED = {"LINE", "LWPOLYLINE", "POLYLINE", "CIRCLE", "ARC", "TEXT", "MTEXT",
             "INSERT", "ATTRIB"}

# R2004 以前的非 ASCII 字元逸出寫法
UNICODE_ESCAPE = re.compile(r"\\U\+([0-9A-Fa-f]{4})")

# MTEXT 行內格式碼：\A1; \H2.5x; \fArial|b0; \C1; 之類
MTEXT_INLINE = re.compile(r"\\[AaCcFfHhLlOoPpQqSsTtWw][^;\\]*;")


class DxfParseError(Exception):
    """DXF 讀取或解析失敗。訊息必須告訴使用者怎麼脫困。"""


# ---------------------------------------------------------------------------
# 編碼

def detect_encoding(raw):
    """由 $ACADVER 與 $DWGCODEPAGE 決定解碼方式。

    先用 latin-1 掃描標頭（latin-1 對任何位元組都不會拋例外），
    確定編碼後再整份重新解碼——不能直接猜 utf-8，
    舊版 AutoCAD 匯出的繁中 DXF 是 cp950，猜錯整份圖層名都是亂碼。
    """
    probe = raw[:8192].decode("latin-1", errors="replace")
    lines = [line.strip() for line in probe.splitlines()]

    version = value_after(lines, "$ACADVER")
    codepage = value_after(lines, "$DWGCODEPAGE")

    if version and version >= FIRST_UTF8_VERSION:
        return "utf-8", None
    if codepage:
        codec = CODEPAGES.get(codepage.upper())
        if codec:
            return codec, f"依 $DWGCODEPAGE = {codepage} 以 {codec} 解碼"
        return "utf-8", f"未知的 $DWGCODEPAGE = {codepage}，改以 utf-8 解碼（中文可能有誤）"
    return None, None  # 交給 decode_bytes 比分決定


def header_extents(text):
    """讀 $EXTMIN／$EXTMAX——CAD 自己宣告的圖面範圍。

    只用來對照，不用來裁切：這兩個值是 ZOOM EXTENTS 時才更新的，
    可能過期，而落在宣告範圍外的實體有可能正是該被審出來的東西。
    """
    lines = [line.strip() for line in text[:8192].splitlines()]
    box = []
    for key in ("$EXTMIN", "$EXTMAX"):
        index = next((i for i, line in enumerate(lines) if line == key), None)
        if index is None or index + 4 >= len(lines):
            return None
        try:
            box.append((float(lines[index + 2]), float(lines[index + 4])))
        except ValueError:
            return None
    (min_x, min_y), (max_x, max_y) = box
    return [min_x, min_y, max_x, max_y]


def value_after(lines, key):
    """在 group code 行對中找出 key 之後那個值。"""
    for index, line in enumerate(lines):
        if line == key and index + 2 < len(lines):
            return lines[index + 2].strip()
    return None


# 標頭沒交代編碼時的候選順序。繁中舊圖以 cp950 為主，
# big5hkscs 多收 cp950 拒絕的造字區，utf-8 墊底。
FALLBACK_CANDIDATES = ("cp950", "big5hkscs", "utf-8")

REPLACEMENT = "�"


def decode_bytes(raw):
    """回傳 (文字, 警告清單)。

    候選編碼一律以 errors="replace" 解碼後比分（替代字元最少者勝），
    不採「strict 全有全無」——真實 R12 圖面常在 LTYPE 說明字串裡夾帶
    造字區位元組，全檔兩個壞位元組就足以讓整份正確的 cp950 解碼被丟棄，
    退回 utf-8 容錯後 20 個中文圖層名全變亂碼。壞位元組落在與審圖
    無關的線型定義裡，不該波及圖層名與文字標註。
    """
    notes = []
    encoding, note = detect_encoding(raw)
    if note:
        notes.append(note)

    if encoding:
        text, bad = decode_scored(raw, encoding)
        if bad == 0:
            return text, notes
        # 標頭指定的編碼也解不乾淨：仍以它為準，但要講清楚有多少字失真
        notes.append(
            f"以 {encoding} 解碼有 {bad} 個字元無法還原，非 ASCII 內容請人工核對"
        )
        return text, notes

    # utf-8 的合法性本身就是強訊號：cp950 位元組流幾乎不可能剛好是合法 utf-8。
    # 反過來不成立——utf-8 位元組以 cp950 解碼往往「不報錯但全是亂碼」，
    # 所以不能單靠替代字元數比分，必須先問「是不是合法 utf-8」。
    try:
        return raw.decode("utf-8"), notes
    except UnicodeDecodeError:
        pass

    scored = []
    for codec in FALLBACK_CANDIDATES:
        try:
            text, bad = decode_scored(raw, codec)
        except LookupError:  # pragma: no cover - 直譯器缺該 codec
            continue
        scored.append((bad, FALLBACK_CANDIDATES.index(codec), codec, text))
    if not scored:  # pragma: no cover - 防禦
        notes.append("編碼無法確定，已以 utf-8 容錯解碼，非 ASCII 字元可能失真——需人工判讀")
        return raw.decode("utf-8", errors="replace"), notes

    scored.sort()
    bad, _, codec, text = scored[0]
    if bad:
        notes.append(
            f"標頭未載明編碼，比對後以 {codec} 解碼（{bad} 個字元無法還原）——中文請人工核對"
        )
    else:
        notes.append(f"標頭未載明編碼，比對後以 {codec} 解碼——中文請人工核對")
    return text, notes


def decode_scored(raw, codec):
    """以 errors="replace" 解碼，回傳 (文字, 失真字元數)。"""
    text = raw.decode(codec, errors="replace")
    return text, text.count(REPLACEMENT)


# ---------------------------------------------------------------------------
# group code 讀取

def read_tags(text):
    """把 DXF 文字切成 (code, value) 序列。

    code 行可能有前置空白（CAD 匯出習慣右對齊到 3 字元），value 可能是空字串。
    """
    lines = text.splitlines()
    tags = []
    for index in range(0, len(lines) - 1, 2):
        code = lines[index].strip()
        if not code:
            continue
        try:
            tags.append((int(code), lines[index + 1].strip()))
        except ValueError:
            # 不是合法 group code，多半是檔案結構壞了；略過該行對，不中斷整份解析
            continue
    return tags


def entity_blocks(tags):
    """抽出 ENTITIES section，切成一個個 (型別, tag 清單)。"""
    blocks = []
    in_entities = False
    current = None

    index = 0
    while index < len(tags):
        code, value = tags[index]
        if code == 0:
            if value == "SECTION" and index + 1 < len(tags) and tags[index + 1][0] == 2:
                in_entities = tags[index + 1][1] == "ENTITIES"
                index += 2
                continue
            if value == "ENDSEC":
                if current:
                    blocks.append(current)
                    current = None
                in_entities = False
                index += 1
                continue
            if in_entities:
                if current:
                    blocks.append(current)
                current = (value, [])
        elif in_entities and current:
            current[1].append((code, value))
        index += 1

    if current:
        blocks.append(current)
    return blocks


def first(tags, code, default=None):
    for tag_code, value in tags:
        if tag_code == code:
            return value
    return default


def as_float(tags, code, default=0.0):
    raw = first(tags, code)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def as_int(tags, code, default=0):
    raw = first(tags, code)
    if raw is None:
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def xy_pairs(tags, x_code=10, y_code=20):
    """依出現順序取出 (x, y)。LWPOLYLINE 的頂點之間可能夾雜 bulge(42)。"""
    points = []
    pending_x = None
    for code, value in tags:
        if code == x_code:
            try:
                pending_x = float(value)
            except ValueError:
                pending_x = None
        elif code == y_code and pending_x is not None:
            try:
                points.append((pending_x, float(value)))
            except ValueError:
                pass
            pending_x = None
    return points


def unescape_text(value):
    r"""還原 \U+XXXX 逸出，並解掉 DXF 的反斜線跳脫。"""
    return UNICODE_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), value)


def mtext_plain(tags):
    """組回 MTEXT 全文並去掉行內格式碼，對齊 ezdxf 的 plain_text()。

    code 3 是每 250 字一段的前段，code 1 是最後一段。
    """
    chunks = [value for code, value in tags if code == 3]
    chunks.append(first(tags, 1, ""))
    text = "".join(chunks)

    text = MTEXT_INLINE.sub("", text)
    text = text.replace("\\P", "\n").replace("\\~", " ")
    text = re.sub(r"(?<!\\)[{}]", "", text)
    text = text.replace("\\\\", "\\").replace("\\{", "{").replace("\\}", "}")
    return unescape_text(text)


# ---------------------------------------------------------------------------
# 實體轉換

def arc_extent(center, radius, start, end):
    """弧的實際包絡點：起訖端點，加上掃掠範圍內的象限極值點。

    用 center ± radius 的正方形當包絡是嚴重高估——真實圖面上一段
    r=68563 的極扁弧就足以把整張圖的 bbox 撐大數百倍，SVG 一縮放，
    平面圖就只剩一個點。dxf_svg_review 的 ezdxf 參考實作共用本函式，
    兩條路徑不得各算各的。
    """
    cx, cy = center
    span = (end - start) % 360 or (360.0 if start != end else 0.0)
    angles = [start, end]
    for quadrant in (0.0, 90.0, 180.0, 270.0):
        if (quadrant - start) % 360 <= span:
            angles.append(quadrant)
    return [
        (cx + radius * math.cos(math.radians(a)), cy + radius * math.sin(math.radians(a)))
        for a in angles
    ]


def convert(dxftype, tags, layer_escaped):
    """單一實體 → 繪製用結構；不支援者回 None。"""

    if dxftype == "LINE":
        start = (as_float(tags, 10), as_float(tags, 20))
        end = (as_float(tags, 11), as_float(tags, 21))
        return {"type": "line", "points": [start, end], "layer": layer_escaped}, [start, end]

    if dxftype in ("LWPOLYLINE", "POLYLINE"):
        points = xy_pairs(tags)
        if len(points) < 2:
            return None, []
        return (
            {"type": "polyline", "points": points,
             "closed": bool(as_int(tags, 70) & 1), "layer": layer_escaped},
            points,
        )

    if dxftype == "CIRCLE":
        center = (as_float(tags, 10), as_float(tags, 20))
        radius = as_float(tags, 40)
        return (
            {"type": "circle", "center": center, "radius": radius, "layer": layer_escaped},
            [(center[0] - radius, center[1] - radius),
             (center[0] + radius, center[1] + radius)],
        )

    if dxftype == "ARC":
        center = (as_float(tags, 10), as_float(tags, 20))
        radius = as_float(tags, 40)
        start = as_float(tags, 50)
        end = as_float(tags, 51)
        return (
            {"type": "arc", "center": center, "radius": radius,
             "start": start, "end": end, "layer": layer_escaped},
            arc_extent(center, radius, start, end),
        )

    if dxftype == "INSERT":
        # 圖塊幾何刻意不展開：消防設備符號只要有插入點就能清點數量與定位缺失，
        # 展開 BLOCKS 的工作量與風險大得多，對審圖結論沒有幫助。
        insert = (as_float(tags, 10), as_float(tags, 20))
        return (
            {"type": "insert", "insert": insert, "block": first(tags, 2, ""),
             "rotation": as_float(tags, 50, 0.0), "layer": layer_escaped},
            [insert],
        )

    if dxftype in ("TEXT", "ATTRIB"):
        insert = (as_float(tags, 10), as_float(tags, 20))
        return (
            {"type": "text", "insert": insert, "text": unescape_text(first(tags, 1, "")),
             "height": as_float(tags, 40, 2.5), "layer": layer_escaped},
            [insert],
        )

    if dxftype == "MTEXT":
        insert = (as_float(tags, 10), as_float(tags, 20))
        return (
            {"type": "text", "insert": insert, "text": mtext_plain(tags),
             "height": as_float(tags, 40, 2.5) or 2.5, "layer": layer_escaped},
            [insert],
        )

    return None, []


def merge_polyline_vertices(blocks):
    """POLYLINE 的頂點放在後續的 VERTEX 實體裡，直到 SEQEND。

    POLYLINE 本體自帶一組 10/20/30——那是高程虛擬點（2D 恆為 0,0），
    不是頂點。不濾掉就會在頂點串前面多冒出一個 (0, 0)。
    """
    merged = []
    index = 0
    while index < len(blocks):
        dxftype, tags = blocks[index]
        if dxftype == "POLYLINE":
            header = [(code, value) for code, value in tags if code not in (10, 20, 30)]
            index += 1
            while index < len(blocks) and blocks[index][0] == "VERTEX":
                header = header + blocks[index][1]
                index += 1
            if index < len(blocks) and blocks[index][0] == "SEQEND":
                index += 1
            merged.append(("POLYLINE", header))
            continue
        merged.append((dxftype, tags))
        index += 1
    return merged


# ---------------------------------------------------------------------------
# 對外介面

def summarise_unsupported(items):
    """把「不支援的實體」警告依型別彙總成一條，附數量與圖層。

    逐一列出會失控：真實圖面一張就能產生上百個同型別實體，
    整批灌進交付物1 的警告區，把真正該看的訊息淹掉。
    """
    grouped = {}
    for dxftype, layer in items:
        entry = grouped.setdefault(dxftype, {"count": 0, "layers": []})
        entry["count"] += 1
        if layer not in entry["layers"]:
            entry["layers"].append(layer)

    warnings = []
    for dxftype, entry in sorted(grouped.items()):
        layers = entry["layers"]
        shown = "、".join(layers[:5]) + ("…" if len(layers) > 5 else "")
        warnings.append(
            f"不支援的 DXF 實體：{dxftype} ×{entry['count']}（圖層 {shown}）"
        )
    return warnings


def parse(dxf_path):
    """解析 ASCII DXF，回傳與 collect_dxf_entities() 相同的結構。"""
    path = Path(dxf_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DxfParseError(f"讀不到 DXF 檔：{path}（{exc}）") from exc

    if raw.startswith(BINARY_SENTINEL):
        raise DxfParseError(
            f"{path.name} 是二進位 DXF，內建解析器只支援文字（ASCII）DXF。\n"
            "請在你的 CAD 中重新「另存新檔」，檔案類型選「AutoCAD 2013 DXF」"
            "（不要勾選二進位／Binary）；或在裝得起套件的環境安裝 ezdxf。"
        )

    text, notes = decode_bytes(raw)
    blocks = merge_polyline_vertices(entity_blocks(read_tags(text)))

    entities, warnings, points, layers = [], list(notes), [], set()
    unsupported = []
    anonymous = 0

    for dxftype, tags in blocks:
        if dxftype in ("VERTEX", "SEQEND"):
            continue
        # 圖紙空間實體不進 modelspace，與 ezdxf 的 modelspace() 一致
        if as_int(tags, 67) == 1:
            continue

        layer = first(tags, 8, "0")
        # 圖層先收再看型別支不支援：圖層清單是判讀設備圖層的依據，
        # 不能因為型別不支援就整個圖層消失（ezdxf 參考實作也是先收圖層）
        layers.add(str(layer))

        if dxftype not in SUPPORTED:
            unsupported.append((dxftype, str(layer)))
            continue

        # 匿名圖塊（*U22、*X96…）是 CAD 內部產物：R12 用它來表示 HATCH、
        # 標註等實體。插入點一律在原點，既不是設備符號，又會把 bbox 拉到原點。
        if dxftype == "INSERT" and first(tags, 2, "").startswith("*"):
            anonymous += 1
            continue

        try:
            converted, extent = convert(dxftype, tags, html.escape(str(layer)))
        except Exception as exc:  # pragma: no cover - 防禦畸形 CAD 實體
            warnings.append(f"無法解析 {dxftype}：{exc}")
            continue
        if converted:
            entities.append(converted)
            points.extend(extent)

    warnings.extend(summarise_unsupported(unsupported))
    if anonymous:
        warnings.append(
            f"略過匿名圖塊 ×{anonymous}（CAD 內部產物，非設備符號；"
            "多為舊版 DXF 用來表示填充線或標註）"
        )

    if not points:
        points = [(0.0, 0.0), (100.0, 100.0)]
        warnings.append("DXF 未解析到可繪製實體，已使用空白檢視框。")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    bbox = [min(xs), min(ys), max(xs), max(ys)]

    warnings.extend(extent_mismatch_warning(bbox, header_extents(text)))

    return {
        "entities": entities,
        "warnings": warnings,
        "bbox": bbox,
        "layers": sorted(layers),
    }


def extent_mismatch_warning(bbox, declared, ratio=4.0):
    """實際範圍遠大於 CAD 宣告範圍時提醒——通常是圖框外有殘留圖元。

    不自動裁切：落在圖框外的東西有可能正是缺失本身，
    該由審圖人員判斷，不該由工具無聲丟掉。
    """
    if not declared:
        return []
    area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    declared_area = (declared[2] - declared[0]) * (declared[3] - declared[1])
    if declared_area <= 0 or area <= declared_area * ratio:
        return []
    return [
        f"實際圖元範圍比圖面宣告範圍（$EXTMIN/$EXTMAX）大 {area / declared_area:.0f} 倍，"
        "圖框外可能有殘留圖元；SVG 會因此縮得很小——需人工判讀是否為應審內容"
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="零相依 ASCII DXF 解析（不需要 ezdxf）")
    parser.add_argument("--input", required=True, help="DXF 檔路徑")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="輸出格式（預設 text）")
    args = parser.parse_args(argv)

    result = parse(args.input)

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"實體 {len(result['entities'])} 個｜圖層 {len(result['layers'])} 個")
    print(f"外框 bbox：{result['bbox']}")
    if result["layers"]:
        print("圖層：" + "、".join(result["layers"]))

    blocks = block_counts(result["entities"])
    if blocks:
        total = sum(blocks.values())
        print(f"\n圖塊統計（共 {total} 個插入點）——消防設備符號多半是圖塊，"
              "可據此清點實設數量：")
        for (layer, name), count in sorted(blocks.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {count:5}  {name or '（無名稱）'}　［圖層 {layer}］")
        print("※ 數量為圖面上的圖塊插入點，仍須人工核對是否等同實際設置數量")

    for warning in result["warnings"]:
        print(f"⚠️ {warning}")
    return 0


def block_counts(entities):
    """依 (圖層, 圖塊名) 統計圖塊插入點數量。

    gap-analysis 要比對「應設 vs 實設」，實設數量的來源就是這裡——
    偵煙探測器、緊急照明燈、揚聲器在真實圖面上都是圖塊。圖塊名通常比
    圖層名更精確（例如「偵煙探測器一種」對上圖層「1_偵煙探測器」），
    兩者一起列出才夠人工核對。
    """
    counts = {}
    for entity in entities:
        if entity["type"] == "insert":
            key = (html.unescape(entity["layer"]), entity.get("block", ""))
            counts[key] = counts.get(key, 0) + 1
    return counts


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DxfParseError as exc:
        sys.exit(str(exc))

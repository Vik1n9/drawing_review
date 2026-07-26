#!/usr/bin/env python3
"""DWG 收件引導 for fire-review.

DWG 是二進位專有格式，沒有任何 AI 讀得了，一定要先轉成 DXF。但本倉庫的
使用者多半只裝了一個 AI 桌面版就開始用，轉檔器在那種沙盒裡幾乎必然裝不
起來——所以本工具的主要交付物是**明確的操作引導**，不是轉檔。

判斷依據：使用者是消防設備師／審查人員，機器上幾乎必然已有 AutoCAD 或
其相容軟體。原生「另存 DXF」的品質優於任何第三方轉檔器，而且零安裝、
零授權問題。所以引導另存 DXF 不是降級路徑，是推薦路徑。

機器上剛好已有轉檔器（例如公司 IT 統一部署）就直接用，但本工具
**不主動安裝任何東西，也不提供安裝腳本**。

Zero external dependencies — Python stdlib only.

Usage:
    python3 tools/dwg_guide.py check --path input/範例大樓/
    python3 tools/dwg_guide.py check --path input/ --format json
    python3 tools/dwg_guide.py convert --input input/案/平面圖.dwg \\
                                       --output output/案/converted/平面圖.dxf
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK, EXIT_NEEDS_ACTION = 0, 2

# DWG 檔頭前 6 bytes 就是版本碼
DWG_VERSIONS = {
    "AC1006": "R10", "AC1009": "R11/R12", "AC1012": "R13", "AC1014": "R14",
    "AC1015": "AutoCAD 2000", "AC1018": "AutoCAD 2004", "AC1021": "AutoCAD 2007",
    "AC1024": "AutoCAD 2010", "AC1027": "AutoCAD 2013", "AC1032": "AutoCAD 2018",
}

DRAWING_SUFFIXES = {".dwg", ".dxf"}

Backend = namedtuple("Backend", "name executable licence_note")

# LibreDWG（GPLv3）可商用，排在前面；ODA 對非會員限非商業用途，只能墊底。
BACKEND_PRIORITY = ("dwg2dxf", "ODAFileConverter")

ODA_LICENCE = "非 ODA 會員僅限非商業用途（Open Design Alliance 官方 FAQ）"


class DwgGuideError(Exception):
    """輸入有問題或無法處理。訊息必須告訴使用者下一步怎麼做。"""


# ---------------------------------------------------------------------------
# 引導文字（本工具的主要交付物）

SAVE_AS_DXF_GUIDE = """\
── 怎麼把 DWG 轉成本系統看得懂的 DXF ──

最快的方式是用你自己的 CAD 匯出，不必安裝任何額外軟體，而且原生匯出的
品質比任何第三方轉檔器都好。

  1. 用你的 CAD 打開這張 DWG
  2. 輸入指令 DXFOUT（或走選單「檔案 → 另存新檔／另存為」）
  3. 檔案類型選 DXF，版本選「AutoCAD 2013」或更新
  4. 不要勾選「二進位（Binary）」——本系統只讀文字（ASCII）DXF
  5. 存到同一個案件資料夾，副檔名 .dxf

各家 CAD 的位置：

  · AutoCAD / AutoCAD LT   檔案 → 另存新檔 → 檔案類型「AutoCAD 2013 DXF」
  · ZWCAD（中望）          檔案 → 另存為 → 類型選 DXF
  · BricsCAD               File → Save As → 選 DXF
  · GstarCAD（浩辰）       檔案 → 另存為 → 類型選 DXF

以上四種都支援 DXFOUT 指令，記不住選單位置就直接打指令。

為什麼要選 2013 或更新：舊版 DXF 的中文採 Big5／cp950 編碼，圖層名與
文字標註容易變成亂碼；2013 以後是 UTF-8，不會有這個問題。
"""


def guidance():
    return SAVE_AS_DXF_GUIDE


# ---------------------------------------------------------------------------
# 格式判定（一律看內容，不信副檔名）

def sniff(path):
    """回傳 (格式, 版本說明)。送審資料的副檔名常常說謊。"""
    try:
        with open(path, "rb") as handle:
            head = handle.read(512)
    except OSError as exc:
        raise DwgGuideError(f"讀不到檔案：{path}（{exc}）") from exc

    marker = head[:6].decode("ascii", errors="replace")
    if marker in DWG_VERSIONS:
        return "dwg", DWG_VERSIONS[marker]
    if marker.startswith("AC10"):
        return "dwg", f"未知版本（{marker}）"
    if head.startswith(b"%PDF-"):
        return "pdf", None
    if head.startswith(b"AutoCAD Binary DXF"):
        return "dxf", "二進位 DXF"
    if head.startswith(b"PK\x03\x04"):
        return zip_kind(path), None
    if b"SECTION" in head or b"HEADER" in head:
        return "dxf", "ASCII DXF"
    return "unknown", None


def zip_kind(path):
    """docx 與 xlsx 的 magic 完全相同，只能看壓縮檔內容分辨。"""
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return "unknown"
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsx"
    if "ppt/presentation.xml" in names:
        return "pptx"
    return "unknown"


# ---------------------------------------------------------------------------
# 轉檔後端偵測（只偵測，不安裝）

def detect_backends():
    """找出機器上已經存在的轉檔器。找不到是常態，不是錯誤。"""
    found = []
    if shutil.which("dwg2dxf"):
        found.append(Backend("dwg2dxf", shutil.which("dwg2dxf"), None))

    oda = shutil.which("ODAFileConverter") or find_oda_on_windows()
    if oda:
        found.append(Backend("ODAFileConverter", oda, ODA_LICENCE))
    return found


def find_oda_on_windows():
    """ODA 的 Windows 安裝程式不一定把自己寫進 PATH。"""
    if platform.system() != "Windows":
        return None
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        for candidate in sorted(Path(base).glob("ODA/ODAFileConverter*/ODAFileConverter.exe")):
            return str(candidate)
    return None


def preferred(backends):
    """LibreDWG 優先——GPLv3 可商用；ODA 對非會員限非商業用途。"""
    if not backends:
        return None
    return sorted(backends, key=lambda b: BACKEND_PRIORITY.index(b.name)
                  if b.name in BACKEND_PRIORITY else len(BACKEND_PRIORITY))[0]


# ---------------------------------------------------------------------------
# 掃描

def scan(target):
    path = Path(target)
    if not path.exists():
        raise DwgGuideError(f"路徑不存在：{path}")

    candidates = [path] if path.is_file() else sorted(
        p for p in path.rglob("*") if p.is_file())

    records = []
    for candidate in candidates:
        fmt, version = sniff(candidate)
        suffix = candidate.suffix.lower()
        # 只有圖面相關的副檔名不符才值得提醒，文件類的不囉嗦
        mismatch = fmt in ("dwg", "dxf") and suffix != f".{fmt}"
        records.append({
            "path": candidate.as_posix(),
            "format": fmt,
            "version": version,
            "extension": suffix,
            "extension_mismatch": mismatch,
        })
    return records


# ---------------------------------------------------------------------------
# 轉檔（只在已有後端時）

def guard_output(output):
    """底線 4：input/ 只讀，產出一律寫 output/。"""
    resolved = Path(output).resolve()
    forbidden = (REPO_ROOT / "input").resolve()
    if resolved == forbidden or forbidden in resolved.parents:
        raise DwgGuideError(
            f"不得寫入 input/（該目錄只讀）：{output}\n"
            "轉檔產物請寫到 output/{案件名}/converted/ 之下。"
        )


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert(source, output, backends=None):
    guard_output(output)

    source_path = Path(source)
    fmt, version = sniff(source_path)
    if fmt != "dwg":
        raise DwgGuideError(
            f"{source_path.name} 的實際格式是 {fmt}，不是 DWG，無需轉檔。")

    backend = preferred(backends if backends is not None else detect_backends())
    if backend is None:
        raise DwgGuideError(
            f"這台電腦上沒有 DWG 轉檔器，無法自動轉檔。\n\n{guidance()}")

    if backend.licence_note:
        print(f"⚠️ 使用 {backend.name} 前請注意授權：{backend.licence_note}")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if backend.name == "dwg2dxf":
        command = [backend.executable, "-y", "-o", str(output_path), str(source_path)]
    else:
        # ODA 是「整個資料夾」的介面，不是單檔
        command = [backend.executable, str(source_path.parent), str(output_path.parent),
                   "ACAD2013", "DXF", "0", "1"]
        if platform.system() != "Windows" and shutil.which("xvfb-run"):
            command = ["xvfb-run", "-a"] + command

    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DwgGuideError(f"轉檔失敗（{backend.name}）：{exc}\n\n{guidance()}") from exc

    if not output_path.exists():
        detail = (completed.stderr or completed.stdout or "").strip()[:400]
        raise DwgGuideError(f"轉檔未產出檔案（{backend.name}）：{detail}\n\n{guidance()}")

    write_provenance(source_path, output_path, backend, version)
    return output_path


def write_provenance(source_path, output_path, backend, version):
    """轉檔是有損的。留下出處，下游才知道這份 DXF 不是原始圖面。"""
    record = {
        "source": source_path.as_posix(),
        "source_sha256": sha256_file(source_path),
        "source_format": "dwg",
        "source_version": version,
        "output": output_path.as_posix(),
        "backend": backend.name,
        "converted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "轉檔產物，非原始圖面。下游欄位一律標 source: derived，"
                "圖層與符號請人工複核。",
    }
    sidecar = output_path.with_suffix(output_path.suffix + ".provenance.json")
    sidecar.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI

def render_check(records, backends):
    dwg_files = [r for r in records if r["format"] == "dwg"]

    print("== DWG 收件檢查 ==")
    if not records:
        print("這個路徑下沒有檔案。")
    for record in records:
        mark = "⚠️" if record["extension_mismatch"] else "·"
        version = f"（{record['version']}）" if record["version"] else ""
        print(f"  {mark} {record['path']} → {record['format']}{version}")
        if record["extension_mismatch"]:
            print(f"      副檔名是 {record['extension']}，實際內容是 {record['format']}"
                  "——以實際內容為準")

    if not dwg_files:
        print("\n沒有 DWG 檔，不需要轉檔。")
        return EXIT_OK

    print(f"\n找到 {len(dwg_files)} 個 DWG 檔。DWG 是二進位格式，本系統無法直接判讀。")

    if backends:
        best = preferred(backends)
        print(f"這台電腦上找得到轉檔器：{best.name}（{best.executable}）")
        if best.licence_note:
            print(f"⚠️ 授權注意：{best.licence_note}")
        print("可執行：python3 tools/dwg_guide.py convert "
              "--input {DWG路徑} --output output/{案件名}/converted/{檔名}.dxf")
        return EXIT_OK

    print("這台電腦上沒有 DWG 轉檔器——不建議為此安裝，用你的 CAD 匯出更快也更準。\n")
    print(guidance())
    return EXIT_NEEDS_ACTION


def main(argv=None):
    parser = argparse.ArgumentParser(description="DWG 收件檢查與另存 DXF 引導")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="掃描路徑，回報格式並在需要時給出引導")
    check.add_argument("--path", required=True, help="案件資料夾或單一檔案")
    check.add_argument("--format", choices=("text", "json"), default="text")

    convert_parser = sub.add_parser("convert", help="已有轉檔器時才可用")
    convert_parser.add_argument("--input", required=True, help="來源 DWG")
    convert_parser.add_argument("--output", required=True,
                                help="輸出 DXF（必須在 output/ 之下）")

    args = parser.parse_args(argv)

    if args.command == "convert":
        result = convert(args.input, args.output)
        print(f"✅ 已轉出：{result}")
        print("⚠️ 轉檔有損：圖層命名、字型與圖塊可能與原圖不同，請人工複核。")
        return EXIT_OK

    records = scan(args.path)
    backends = detect_backends()

    if args.format == "json":
        print(json.dumps({
            "files": records,
            "dwg_files": [r["path"] for r in records if r["format"] == "dwg"],
            "backends": [b._asdict() for b in backends],
            "guidance": guidance(),
        }, ensure_ascii=False, indent=2))
        return EXIT_OK if not [r for r in records if r["format"] == "dwg"] or backends \
            else EXIT_NEEDS_ACTION

    return render_check(records, backends)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DwgGuideError as exc:
        sys.exit(str(exc))

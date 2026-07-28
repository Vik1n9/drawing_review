#!/usr/bin/env python3
"""把安裝包組成 Windows 自解壓縮檔（7-Zip SFX）。

只用 Python 標準庫（外部只呼叫 `7z`）。

    python3 tools/make_sfx.py --version v1.2.0 \\
        --stage dist/FireReview-v1.2.0 --sfx-module vendor/7zS2.sfx --out dist/

## 為什麼是自解壓縮檔而不是 Inno Setup

前一版用 Inno Setup，代價是 220 行的 `.iss`（其中 136 行 Pascal Script 沒有任何
測試涵蓋）＋ CI 要一台 `windows-latest` 跑 `choco install innosetup`。
換成 SFX 之後，那 136 行變成 20 行以內的批次檔，整條發版流程都在 Linux 上跑得完。

**而且結構上更安全。** `7zS2.sfx` 把酬載解到 `%TEMP%`，執行 `RunProgram`，
結束後清掉暫存——在 `tools/installer.py` 跑起來之前，**使用者的安裝資料夾一個
位元組都沒被碰過**。Inno Setup 是在安裝過程中逐檔複製到 `{app}`，靠 Pascal 判斷
該落在暫存還是本體，判斷錯就是部分覆蓋；SFX 讓這種錯誤不可能發生。

## 為什麼 SFX 模組是輸入而不是本工具去下載

本工具維持 stdlib-only、離線、可測試；網路 I/O 留給 CI（見 `.github/workflows/
release.yml`）。這也讓測試能拿一段假位元組當模組，驗完整的串接順序。

## 「安裝.bat」為什麼還是存在

SFX 只會執行一個程式，而我們要執行的是 Python 腳本——中間需要一層「找到 Python」。
那一層**只能**是批次檔（Python 還沒就位，寫不了 Python）。所以它被壓到最小：
偵測、必要時裝 Python、呼叫 `tools/installer.py`。所有判定邏輯都在 Python 那邊。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from tools.console import force_utf8_output
except ImportError:  # 直接以 tools/ 為工作目錄執行時
    from console import force_utf8_output

force_utf8_output()

PRODUCT = "FireReview"
BATCH_NAME = "安裝.bat"
RUNTIME_JSON = Path("packaging") / "python-runtime.json"
CONFIG_TEMPLATE = Path("packaging") / "sfx-config.txt"

# 批次檔一律 CRLF：cmd 對 LF-only 的 .bat 在 label 與 goto 上會有詭異行為，
# 而這個檔剛好兩者都用到。
CRLF = "\r\n"

# `chcp 65001` 必須在任何中文之前——cmd 是逐行讀取執行的，切換之後才讀得對後面的字。
# 檔案本身寫成 **UTF-8 無 BOM**：.bat 開頭有 BOM 會讓 cmd 把它當成命令而報錯。
BATCH_TEMPLATE = """@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo(
echo === Fire Review 消防審圖輔助系統 ===
echo(
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (python --version >nul 2>nul && set "PY=python")
if not defined PY call :get_python
if not defined PY goto no_python
%PY% "tools\\installer.py" --by 安裝程式
exit /b %errorlevel%

:get_python
echo 這台電腦還沒有 Python，正在下載官方安裝程式（約 25 MB）...
curl -L --fail -o "%TEMP%\\fire-review-python.exe" "{url}" || exit /b
powershell -NoProfile -Command "$s=Get-AuthenticodeSignature '%TEMP%\\fire-review-python.exe'; if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notlike '*{publisher}*'){{exit 1}}" || exit /b
echo 正在安裝 Python {version}（使用者層級，不需要管理員權限）...
"%TEMP%\\fire-review-python.exe" {install_args}
rem PrependPath 不影響已經開著的這個行程，所以直接去裝好的位置找
for /d %%D in ("%LOCALAPPDATA%\\Programs\\Python\\Python3*") do set "PY=%%D\\python.exe"
exit /b

:no_python
echo(
echo 沒辦法自動準備好 Python，所以先不動你的任何資料。
echo(
echo 請改用下面任一種方式：
echo   1. 自己安裝 Python（https://www.python.org/downloads/），
echo      安裝時務必勾選「Add python.exe to PATH」，然後重新執行這個安裝程式。
echo   2. 到 GitHub Releases 下載免安裝的 .zip，解壓縮到你要的資料夾即可。
echo(
pause
exit /b 1
"""


def load_runtime(root="."):
    """讀 Python 執行環境的釘選資料。"""
    path = Path(root) / RUNTIME_JSON
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    missing = [k for k in ("version", "url_template", "publisher", "install_args")
               if not doc.get(k)]
    if missing:
        raise ValueError(f"{path} 缺少欄位：{'、'.join(missing)}")
    doc["url"] = doc["url_template"].format(version=doc["version"])
    return doc


def render_batch(runtime):
    """產生「安裝.bat」，把版本與網址烘進去。"""
    text = BATCH_TEMPLATE.format(
        url=runtime["url"], version=runtime["version"],
        publisher=runtime["publisher"], install_args=runtime["install_args"])
    return text.replace("\r\n", "\n").replace("\n", CRLF)


def have_7z():
    for name in ("7z", "7za", "7zr"):
        path = shutil.which(name)
        if path:
            return path
    return None


def build_payload(stage_dir, batch_text, archive_path):
    """把 stage 目錄 ＋ 安裝.bat 壓成 .7z，內容落在封存根目錄。

    `7z a <封存> .`（工作目錄設在 stage）是唯一同時滿足「不多一層目錄」與
    「含 .claude/、.gitkeep 這類 dotfile」的寫法。
    """
    executable = have_7z()
    if executable is None:
        raise RuntimeError(
            "找不到 7z——請先安裝（Debian/Ubuntu：apt-get install p7zip-full）。"
            "本工具刻意不自行下載，網路 I/O 留給 CI。")

    stage_dir = Path(stage_dir).resolve()
    archive_path = Path(archive_path).resolve()
    batch_path = stage_dir / BATCH_NAME
    batch_path.write_text(batch_text, encoding="utf-8", newline="")

    if archive_path.exists():
        archive_path.unlink()
    proc = subprocess.run(
        [executable, "a", "-t7z", "-mx=9", str(archive_path), "."],
        cwd=stage_dir, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"7z 打包失敗：{(proc.stderr or proc.stdout)[-800:]}")
    return archive_path


def assemble(sfx_module, config_text, archive_path, output_path):
    """SFX 模組 ＋ 設定 ＋ 封存，順序不能錯——錯了就不是有效的 exe。"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as out:
        out.write(Path(sfx_module).read_bytes())
        # 設定用 UTF-8 **無 BOM**：`;!@Install@!UTF-8!` 這行本身就是編碼宣告，
        # 前面多一個 BOM 會讓 SFX 認不得這個標記。
        out.write(config_text.encode("utf-8"))
        out.write(Path(archive_path).read_bytes())
    return output_path


def build(stage, out, version, sfx_module, root=".", config=None):
    stage_dir = Path(stage)
    if not (stage_dir / "tools" / "installer.py").is_file():
        raise ValueError(
            f"{stage_dir} 看起來不是 make_release.py 攤出來的安裝包"
            "（找不到 tools/installer.py）")

    runtime = load_runtime(root)
    batch_text = render_batch(runtime)
    config_text = (Path(config) if config else Path(root) / CONFIG_TEMPLATE
                   ).read_text(encoding="utf-8")

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"{PRODUCT}-{version}-setup.exe"

    with tempfile.TemporaryDirectory() as tmp:
        archive = build_payload(stage_dir, batch_text, Path(tmp) / "payload.7z")
        assemble(sfx_module, config_text, archive, output)

    return {"exe": str(output), "size": output.stat().st_size,
            "python_version": runtime["version"], "python_url": runtime["url"],
            "batch_lines": batch_text.count(CRLF)}


def main(argv=None):
    p = argparse.ArgumentParser(
        description="把安裝包組成 Windows 自解壓縮檔（7-Zip SFX）")
    p.add_argument("--root", default=".", help="倉庫根目錄（預設為當前目錄）")
    p.add_argument("--version", required=True, help="版本號，例如 v1.2.0")
    p.add_argument("--stage", required=True,
                   help="make_release.py --stage-only 攤出來的目錄")
    p.add_argument("--sfx-module", required=True,
                   help="7-Zip Extra 的 7zS2.sfx（由 CI 下載，本工具不自行取得）")
    p.add_argument("--config", help="自訂 SFX 設定檔（預設 packaging/sfx-config.txt）")
    p.add_argument("--out", default="dist", help="輸出目錄（預設 dist/）")
    args = p.parse_args(argv)

    result = build(args.stage, args.out, args.version, args.sfx_module,
                   root=args.root, config=args.config)
    print(f"✅ 已組出自解壓縮檔（{result['size'] / 1024 / 1024:.1f} MB）")
    print(f"  {result['exe']}")
    print(f"  內建 Python 取得方式：{result['python_url']}")
    print(f"  安裝.bat 共 {result['batch_lines']} 行"
          "（唯一沒有單元測試的部分，刻意壓到最小）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

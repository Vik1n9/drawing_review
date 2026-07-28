"""所有 CLI 工具在任何主控台編碼下都要印得出中文。

## 這條測試在守什麼

本倉庫的輸出全是繁體中文，而 Windows 的 Python 在 stdout **被重導向或接管道**時
用系統 locale 編碼（英文版 Windows 是 cp1252），一遇到中文就 `UnicodeEncodeError`
當場中斷。直接在主控台跑不會發生，所以這種 bug 很容易一路漏到使用者手上。

v0.1.0 發版時就真的發生了：CI 的 windows job 在 `installer.py` 的**第一個 print**
就炸掉，實測 28 個 CLI 工具裡有 27 個中招。

打中的是兩種真實情況，都不是邊緣案例：

1. **AI 代理執行工具並讀取輸出**——那正是本倉庫的主要使用方式
2. 使用者把輸出導進檔案留存

## 為什麼是子行程而不是靜態檢查

靜態檢查「有沒有呼叫 force_utf8_output」會漏掉順序問題（例如在它生效之前就有
模組層級的 print）。真的開一個 cp1252 的子行程跑一次，才是使用者實際會遇到的路徑。
28 個工具全跑約 1.5 秒，這個代價值得。
"""

import subprocess
import sys
import unittest
from pathlib import Path

from tools.console import force_utf8_output

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"

# 中文、全形標點、emoji——輸出裡實際會出現的東西
SAMPLE = "✅ 消防審圖⛔ 待確認事項——第 24 條"


def cli_tools():
    """有 CLI 入口的工具。新增工具會自動納入，不必維護清單。"""
    found = []
    for path in sorted(TOOLS.glob("*.py")):
        if '__name__ == "__main__"' in path.read_text(encoding="utf-8"):
            found.append(path)
    return found


class ForceUtf8OutputTest(unittest.TestCase):

    def test_reports_which_streams_it_changed(self):
        self.assertIsInstance(force_utf8_output(), list)

    def test_is_idempotent(self):
        force_utf8_output()
        self.assertEqual([], force_utf8_output(),
                         "已經是 UTF-8 了還重設一次——會白白丟掉緩衝區設定")

    def test_survives_a_stream_without_reconfigure(self):
        """測試會把 sys.stdout 換成 StringIO，那東西沒有 reconfigure。"""
        import io
        from unittest import mock
        with mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual([], force_utf8_output(["stdout"]))

    def test_survives_a_closed_stream(self):
        from unittest import mock

        class Closed:
            encoding = "cp1252"

            def reconfigure(self, **kwargs):
                raise ValueError("I/O operation on closed file")

        with mock.patch.object(sys, "stdout", Closed()):
            self.assertEqual([], force_utf8_output(["stdout"]))


class EveryCliToolSurvivesALegacyCodepageTest(unittest.TestCase):
    """實測：每個工具在 cp1252 管道下都要跑得完。"""

    def run_tool(self, path, *args):
        return subprocess.run(
            [sys.executable, str(path), *args],
            cwd=REPO, capture_output=True, text=True, timeout=120,
            env={"PYTHONIOENCODING": "cp1252", "PATH": "/usr/bin:/bin",
                 "HOME": "/tmp"})

    def test_every_cli_tool_prints_its_help(self):
        tools = cli_tools()
        self.assertGreater(len(tools), 20, "工具怎麼變這麼少？清單掃描可能壞了")
        for path in tools:
            with self.subTest(tool=path.name):
                proc = self.run_tool(path, "--help")
                self.assertNotIn("UnicodeEncodeError", proc.stderr,
                                 f"{path.name} 在 cp1252 管道下印不出中文——"
                                 "Windows 使用者把輸出導向檔案就會炸")
                self.assertEqual(0, proc.returncode, proc.stderr[-500:])

    def test_the_tools_users_actually_run_produce_chinese_output(self):
        """--help 可能只有英文；這幾支是一定會吐中文的，要真的跑一次。"""
        for args in (["tools/check_env.py"],
                     ["tools/update_guard.py", "check"],
                     ["tools/onboarding.py", "status"]):
            with self.subTest(tool=args[0]):
                proc = self.run_tool(REPO / args[0], *args[1:])
                self.assertNotIn("UnicodeEncodeError", proc.stderr)
                self.assertIn(proc.returncode, (0, 2, 3),
                              f"非預期結束碼：{proc.stderr[-500:]}")


class LaunchersSetUtf8Test(unittest.TestCase):
    """雙擊 .bat 的使用者不經過 Python 的重設，所以殼層也要先設好。"""

    def test_diagnostic_bat_sets_utf8(self):
        from tools import make_release
        self.assertIn("chcp 65001", make_release.DIAGNOSTIC_BAT)
        self.assertIn("PYTHONUTF8=1", make_release.DIAGNOSTIC_BAT)

    def test_installer_bat_sets_utf8(self):
        from tools import make_sfx
        batch = make_sfx.BATCH_TEMPLATE
        self.assertIn("chcp 65001", batch)
        self.assertIn("PYTHONUTF8=1", batch)


if __name__ == "__main__":
    unittest.main()

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


# 缺選用套件時「乾淨地報錯退出」是**正確行為**（見 requirements.txt 的零安裝哲學），
# 不是這條測試要抓的東西。第一版把整個環境洗掉（寫死 PATH、HOME）想求「乾淨」，
# 結果只是把 CI 裝在 user site 的套件藏起來——本機 pip 裝到 dist-packages 所以測不出來，
# 到了 CI 才紅。環境要繼承，只覆寫真正要測的那一個變數。
ENCODING_ERRORS = ("UnicodeEncodeError", "codec can't encode")

# 只用標準庫的工具：任何環境都該跑得起來，所以連結束碼都可以斷言。
# 其餘工具可能因為缺選用套件而正當地非零退出。
STDLIB_ONLY = ("check_env.py", "update_guard.py", "onboarding.py",
               "installer.py", "guard_hook.py", "make_release.py",
               "regulation_graph.py", "regulation_index.py", "graph_status.py")


class EveryCliToolDeclaresItTest(unittest.TestCase):
    """靜態不變式：每個 CLI 入口都要自己呼叫一次。

    為什麼光靠下面的實跑不夠：工具彼此 import，而被 import 的模組在載入時就會
    呼叫 force_utf8_output()，所以某個檔案漏掉時，往往被它 import 的別人「順便」
    救了——實跑因此看不出來。**那種靠 import 副作用成立的正確性，會在有人重構
    掉一行 import 的那天無聲消失。**

    實測過：拿掉 pending_review.py 的呼叫，實跑仍然全綠（它 import 的模組已經
    把 stdout 重設好了）；拿掉 check_env.py 的（它不 import 別的工具）才會紅。
    """

    def test_every_cli_tool_calls_force_utf8_output(self):
        for path in cli_tools():
            with self.subTest(tool=path.name):
                self.assertIn(
                    "force_utf8_output()", path.read_text(encoding="utf-8"),
                    f"{path.name} 沒有呼叫 force_utf8_output()——"
                    "現在可能因為 import 了別的工具而僥倖沒事，"
                    "但那份保護會隨著任何一次 import 重構消失")


class EveryCliToolSurvivesALegacyCodepageTest(unittest.TestCase):
    """實測：每個工具在 cp1252 管道下都不得因為編碼而中斷。"""

    def run_tool(self, path, *args):
        import os
        return subprocess.run(
            [sys.executable, str(path), *args],
            cwd=REPO, capture_output=True, text=True, timeout=120,
            env=dict(os.environ, PYTHONIOENCODING="cp1252"))

    def assert_no_encoding_error(self, proc, name):
        for marker in ENCODING_ERRORS:
            self.assertNotIn(
                marker, proc.stderr,
                f"{name} 在 cp1252 管道下印不出中文——"
                f"Windows 使用者把輸出導向檔案、或 AI 代理讀取輸出就會炸\n"
                f"{proc.stderr[-600:]}")

    def test_every_cli_tool_survives(self):
        tools = cli_tools()
        self.assertGreater(len(tools), 20, "工具怎麼變這麼少？清單掃描可能壞了")
        for path in tools:
            with self.subTest(tool=path.name):
                proc = self.run_tool(path, "--help")
                self.assert_no_encoding_error(proc, path.name)
                if path.name in STDLIB_ONLY:
                    self.assertEqual(0, proc.returncode, proc.stderr[-500:])

    def test_the_tools_users_actually_run_produce_chinese_output(self):
        """--help 可能只有英文；這幾支是一定會吐中文的，要真的跑一次。"""
        for args in (["tools/check_env.py"],
                     ["tools/update_guard.py", "check"],
                     ["tools/onboarding.py", "status"]):
            with self.subTest(tool=args[0]):
                proc = self.run_tool(REPO / args[0], *args[1:])
                self.assert_no_encoding_error(proc, args[0])
                self.assertIn(proc.returncode, (0, 2, 3),
                              f"非預期結束碼：{proc.stderr[-500:]}")
                self.assertTrue(
                    any("一" <= ch <= "鿿"
                        for ch in proc.stdout + proc.stderr),
                    f"{args[0]} 在 cp1252 下沒吐出任何中文——"
                    "可能被靜默吞掉了，那比報錯更糟")


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

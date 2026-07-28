"""自解壓縮檔組裝（tools/make_sfx.py）的行為測試。

守住的契約：

1. **串接順序**——SFX 模組 → 設定 → 封存。錯了就不是有效的 exe，而這種錯誤
   在 Linux 上組裝時完全看不出來，只有使用者雙擊時才會發現
2. **酬載完整**——stage 整棵樹（含 `.claude/`、`.gitkeep` 這種 dotfile）＋ 安裝.bat
3. **`安裝.bat` 的三個要害**——切 UTF-8 碼頁、驗發行者簽章、呼叫 installer.py。
   這個檔是整個方案唯一沒有單元測試涵蓋的執行路徑，所以它的**內容**必須被測到
4. **缺 7z 要講清楚**——不能靜默產出半成品

`7z` 不在時只跳過真的要壓縮的測試；批次檔與設定的驗證不需要 7z。

**在安裝包裡跑時整批跳過。** `packaging/` 是建置輸入，使用者的安裝資料夾不需要，
`make_release.py` 也就沒把它打包進去——但 `tests/` 是整個包進去的，所以這些測試
會在使用者的安裝包裡找不到建置輸入。發版工具的測試對「已安裝的系統」本來就不適用。
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import installer, make_sfx

REPO = Path(__file__).resolve().parent.parent

# 假的 SFX 模組：測串接順序不需要真的 7zS2.sfx（那是 CI 才下載的東西）
FAKE_SFX = b"MZ\x90\x00" + b"FAKE-7ZS2-SFX-MODULE" * 64

# 判準刻意是「有沒有安裝清單.json」而不是「packaging/ 在不在」：
# 後者會讓有人不小心刪掉建置輸入時，倉庫自己的測試**靜默跳過**而不是紅燈——
# 那等於把守門變成裝飾。安裝清單只有 make_release.py 會產生，是可靠的身分證。
IS_INSTALLED_PACKAGE = (REPO / "安裝清單.json").is_file()

needs_build_inputs = unittest.skipIf(
    IS_INSTALLED_PACKAGE, "安裝包沒有 packaging/ 建置輸入——發版工具的測試不適用")


def has_7z():
    return make_sfx.have_7z() is not None


def make_stage(base):
    """造一個像 make_release.py --stage-only 產物的最小目錄。"""
    stage = Path(base) / "FireReview-v0.0.0-test"
    for rel in ("tools/installer.py", "tools/onboarding.py",
                ".claude/settings.json", "rules/equipment_rules.json",
                "安裝清單.json", "安裝完成-請把這段貼給你的AI.txt"):
        path = stage / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("內容\n", encoding="utf-8")
    (stage / "input").mkdir(parents=True, exist_ok=True)
    (stage / "input" / ".gitkeep").write_text("", encoding="utf-8")
    return stage


@needs_build_inputs
class RuntimePinTest(unittest.TestCase):
    """釘選資料是真的資料檔，不是散在程式裡的字串。"""

    def test_repo_ships_a_valid_runtime_pin(self):
        runtime = make_sfx.load_runtime(REPO)
        self.assertTrue(runtime["version"])
        self.assertIn(runtime["version"], runtime["url"])
        self.assertTrue(runtime["url"].startswith("https://www.python.org/"),
                        "Python 只能從官方站台取得")
        self.assertEqual("Python Software Foundation", runtime["publisher"])

    def test_user_level_install_needs_no_administrator(self):
        """裝進 Program Files 要管理員權限，而使用者多半沒有。"""
        runtime = make_sfx.load_runtime(REPO)
        self.assertIn("InstallAllUsers=0", runtime["install_args"])

    def test_missing_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / make_sfx.RUNTIME_JSON
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"version": "3.12.10"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                make_sfx.load_runtime(tmp)


@needs_build_inputs
class BatchFileTest(unittest.TestCase):
    """整個方案唯一沒被單元測試涵蓋的執行路徑——所以它的內容必須被測到。"""

    def setUp(self):
        self.runtime = make_sfx.load_runtime(REPO)
        self.batch = make_sfx.render_batch(self.runtime)

    def test_switches_to_utf8_before_any_chinese(self):
        """cmd 是逐行讀取執行的；沒先切碼頁，後面的中文會變亂碼。"""
        lines = self.batch.split(make_sfx.CRLF)
        chcp = next(i for i, line in enumerate(lines) if "chcp 65001" in line)
        first_chinese = next(
            i for i, line in enumerate(lines)
            if any("一" <= ch <= "鿿" for ch in line))
        self.assertLess(chcp, first_chinese, "中文出現在切換碼頁之前")

    def test_uses_crlf_line_endings(self):
        """cmd 對 LF-only 的 .bat 在 label 與 goto 上會有詭異行為。"""
        self.assertIn(make_sfx.CRLF, self.batch)
        self.assertNotIn("\n", self.batch.replace(make_sfx.CRLF, ""))

    def test_prefers_an_existing_python(self):
        self.assertIn("py -3 --version", self.batch)
        self.assertIn("python --version", self.batch)

    def test_bakes_in_the_pinned_download_url(self):
        self.assertIn(self.runtime["url"], self.batch)
        self.assertIn(self.runtime["version"], self.batch)

    def test_verifies_the_publisher_signature_before_running_the_installer(self):
        """不驗簽章就等於任何能攔截連線的人都可以塞一個 exe 進來執行。"""
        self.assertIn("Get-AuthenticodeSignature", self.batch)
        self.assertIn(self.runtime["publisher"], self.batch)
        download = self.batch.index("curl")
        verify = self.batch.index("Get-AuthenticodeSignature")
        run = self.batch.index(self.runtime["install_args"].split()[0])
        self.assertLess(download, verify, "驗證要在下載之後")
        self.assertLess(verify, run, "驗證要在執行之前")

    def test_finds_python_by_path_after_installing_it(self):
        """PrependPath 不影響已經開著的這個行程——只靠重新偵測會失敗。"""
        self.assertIn("%LOCALAPPDATA%\\Programs\\Python\\Python3*", self.batch)

    def test_hands_over_to_the_python_installer(self):
        self.assertIn("tools\\installer.py", self.batch)

    def test_failure_path_touches_nothing_and_offers_two_routes(self):
        """Python 準備不起來時，使用者要知道還有哪兩條路可走。"""
        self.assertIn("先不動你的任何資料", self.batch)
        self.assertIn("python.org", self.batch)
        self.assertIn(".zip", self.batch)
        self.assertIn("pause", self.batch, "視窗會一閃而過，使用者看不到原因")

    def test_stays_small(self):
        """換掉 Inno Setup 的意義就在這裡：136 行無測試的 Pascal → 這一小段。"""
        lines = [line for line in self.batch.split(make_sfx.CRLF) if line.strip()]
        self.assertLess(len(lines), 40, f"安裝.bat 膨脹到 {len(lines)} 行了")


class ArtifactHandoffTest(unittest.TestCase):
    """安裝殼層與安裝器之間唯一的共用常數——漂移了，批次檔就會留在使用者資料夾裡。"""

    def test_installer_knows_to_prune_the_batch_file(self):
        self.assertIn(make_sfx.BATCH_NAME, installer.INSTALLER_ARTIFACTS)


@needs_build_inputs
class ConfigTest(unittest.TestCase):

    def setUp(self):
        self.config = (REPO / make_sfx.CONFIG_TEMPLATE).read_text(encoding="utf-8")

    def test_declares_utf8_and_runs_the_batch_file(self):
        self.assertTrue(self.config.startswith(";!@Install@!UTF-8!"),
                        "第一行必須是編碼宣告，SFX 靠它認得後面的中文")
        self.assertIn(f'RunProgram="{make_sfx.BATCH_NAME}"', self.config)
        self.assertIn(";!@InstallEnd@!", self.config)

    def test_prompt_tells_upgraders_their_work_is_safe(self):
        """這是使用者按下「執行」之前看到的唯一一句話。"""
        self.assertIn("不會被覆蓋", self.config)


@needs_build_inputs
@unittest.skipUnless(has_7z(), "這台機器沒有 7z")
class AssemblyTest(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.stage = make_stage(self.tmp)
        self.module = self.tmp / "7zS2.sfx"
        self.module.write_bytes(FAKE_SFX)
        self.result = make_sfx.build(self.stage, self.tmp / "dist", "v0.0.0-test",
                                     self.module, root=REPO)
        self.exe = Path(self.result["exe"])

    def test_output_is_module_then_config_then_archive(self):
        """順序錯了在 Linux 上完全看不出來，只有使用者雙擊時才會發現。"""
        data = self.exe.read_bytes()
        self.assertTrue(data.startswith(FAKE_SFX), "開頭不是 SFX 模組")
        marker = data.index(b";!@Install@!UTF-8!")
        seven_zip = data.index(b"7z\xbc\xaf\x27\x1c")   # .7z 的簽章
        self.assertEqual(len(FAKE_SFX), marker, "設定沒有緊接在模組之後")
        self.assertLess(marker, seven_zip, "封存排在設定之前")

    def test_archive_holds_the_whole_stage_tree_at_its_root(self):
        listing = subprocess.run([make_sfx.have_7z(), "l", str(self.exe)],
                                 capture_output=True, text=True).stdout
        for rel in ("tools/installer.py", ".claude/settings.json",
                    "安裝清單.json", "input/.gitkeep", make_sfx.BATCH_NAME):
            self.assertIn(rel.replace("/", "/"), listing.replace("\\", "/"),
                          f"酬載少了 {rel}")
        self.assertNotIn("FireReview-v0.0.0-test/tools",
                         listing.replace("\\", "/"),
                         "多包了一層目錄——解出來的路徑就會全錯")

    def test_batch_file_lands_in_the_payload(self):
        self.assertTrue((self.stage / make_sfx.BATCH_NAME).is_file())

    def test_reports_where_it_wrote_and_how_big(self):
        self.assertTrue(self.exe.is_file())
        self.assertEqual(self.exe.stat().st_size, self.result["size"])
        self.assertTrue(self.exe.name.endswith("-setup.exe"))

    def test_refuses_a_stage_directory_that_is_not_an_install_package(self):
        empty = self.tmp / "不是安裝包"
        empty.mkdir()
        with self.assertRaises(ValueError):
            make_sfx.build(empty, self.tmp / "dist", "v0", self.module, root=REPO)


class MissingToolTest(unittest.TestCase):

    def test_missing_7z_is_reported_clearly(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(make_sfx, "have_7z", return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                make_sfx.build_payload(make_stage(tmp), "echo hi",
                                       Path(tmp) / "payload.7z")
        self.assertIn("p7zip", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

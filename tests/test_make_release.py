"""發佈打包（tools/make_release.py）的行為測試。

守住四個契約：

1. **不該進包的東西不會進去**——範例圖、示範交付物、.git、快取
2. **該進包的東西一定在**——使用者開箱要能審圖，也要能自己驗證安裝完整
3. **安裝清單就是升級的基準**——沒有它，安裝目錄（沒有 .git）就分不出
   「上游原樣」與「使用者改過」，升級只能盲目覆蓋
4. **owner 與 update_guard 是同一份真相**——兩份會漂移，而漂移的後果是
   共編檔被當成使用者獨佔檔整檔還原，把上游的法規更新一起吃掉
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools import make_release
from tools import update_guard as guard

REPO = Path(__file__).resolve().parent.parent


class ReleaseTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.result = make_release.build(REPO, cls.tmp / "dist", "v0.0.0-test")
        cls.stage = Path(cls.result["stage_dir"])
        cls.manifest = json.loads(
            (cls.stage / guard.MANIFEST_NAME).read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def zip_names(self):
        with zipfile.ZipFile(self.result["zip"]) as zf:
            return set(zf.namelist())


class PackageContentTest(ReleaseTestCase):

    def test_excludes_sample_drawings_and_demo_deliverables(self):
        """範例圖佔 3 MB 卻不是使用者要審的案件；示範交付物會混淆全新安裝。"""
        for name in self.zip_names():
            self.assertFalse(name.startswith("input/範例/"), f"範例圖進包了：{name}")
            self.assertFalse(name.startswith("output/") and name != "output/.gitkeep",
                             f"示範交付物進包了：{name}")

    def test_excludes_git_and_caches(self):
        for name in self.zip_names():
            self.assertFalse(name.startswith(".git/"), name)
            self.assertNotIn("__pycache__", name)
            self.assertFalse(name.endswith(".pyc"), name)

    def test_includes_what_the_user_needs_to_start(self):
        names = self.zip_names()
        for rel in ("AGENTS.md", "CLAUDE.md", "README.md",
                    "tools/onboarding.py", "tools/fire_code_calc.py",
                    "tools/update_guard.py", "skills/onboarding.md",
                    "rules/equipment_rules.json", "graphify-out/graph.json",
                    ".claude/settings.json", "input/README.md"):
            self.assertIn(rel, names, f"安裝包少了 {rel}")

    def test_includes_tests_so_users_can_self_verify(self):
        names = self.zip_names()
        self.assertIn("tests/test_update_guard.py", names)
        self.assertIn("CONTRIBUTING.md", names)

    def test_creates_writable_directories_for_the_tools(self):
        """空目錄進不了 zip——工具要往這裡寫東西，得先有地方。"""
        names = self.zip_names()
        for rel in ("input/.gitkeep", "output/.gitkeep",
                    "training/inbox/.gitkeep", "practice_notes/active/.gitkeep"):
            self.assertIn(rel, names, f"安裝包沒有建出 {rel}")

    def test_ships_a_double_click_entry_point(self):
        """使用者不熟終端機——雙擊就能跑診斷是這條路線的重點之一。"""
        self.assertIn("開場診斷.bat", self.zip_names())
        text = (self.stage / "開場診斷.bat").read_text(encoding="utf-8-sig")
        self.assertIn("onboarding.py status", text)
        self.assertIn("pause", text, "視窗會一閃而過，使用者看不到結果")
        self.assertIn("python.org", text, "沒告訴使用者 Python 沒裝時該去哪")


class ManifestTest(ReleaseTestCase):

    def test_manifest_covers_every_packaged_file(self):
        packaged = {n for n in self.zip_names() if n != guard.MANIFEST_NAME}
        self.assertEqual(packaged, set(self.manifest["files"]),
                         "清單與實際內容對不上——升級會誤判哪些檔案被改過")

    def test_every_entry_has_a_hash_and_an_owner(self):
        for rel, entry in self.manifest["files"].items():
            with self.subTest(path=rel):
                self.assertIsNotNone(entry["sha256"], f"{rel} 沒有 sha256")
                self.assertIn(entry["owner"],
                              (guard.USER, guard.SHARED, make_release.UPSTREAM_OWNER))

    def test_owner_matches_update_guard_for_data_zone_files(self):
        """兩份 owner 表漂移的後果：共編檔被整檔還原，上游修法一起被吃掉。"""
        for rel, entry in self.manifest["files"].items():
            head = rel.split("/", 1)[0]
            if head in guard.DATA_ZONES or rel in guard.ROOT_FILES:
                with self.subTest(path=rel):
                    self.assertEqual(guard.owner_for(rel), entry["owner"])

    def test_rules_are_marked_shared(self):
        self.assertEqual(guard.SHARED,
                         self.manifest["files"]["rules/equipment_rules.json"]["owner"])

    def test_manifest_records_provenance(self):
        self.assertEqual("v0.0.0-test", self.manifest["version"])
        self.assertTrue(self.manifest["released_at"])
        if (REPO / ".git").exists():
            self.assertIsNotNone(self.manifest["source_commit"],
                                 "沒記下 commit，出問題時追不回是哪一版")
        else:
            # 安裝包自己跑這份測試時沒有 .git——記不到 commit 是預期內的
            self.assertIsNone(self.manifest["source_commit"])

    def test_hashes_describe_the_packaged_content(self):
        for rel in ("AGENTS.md", "rules/equipment_rules.json"):
            with self.subTest(path=rel):
                self.assertEqual(guard.sha256_file(self.stage / rel),
                                 self.manifest["files"][rel]["sha256"])


class InstalledPackageTest(ReleaseTestCase):
    """安裝包解出來之後，本身就要是一個可用、可自驗的倉庫。"""

    def setUp(self):
        self.installed = self.tmp / "installed"
        if not self.installed.exists():
            self.installed.mkdir()
            with zipfile.ZipFile(self.result["zip"]) as zf:
                zf.extractall(self.installed)

    def test_guard_reports_a_clean_install_without_git(self):
        """沒有 .git，基準改由安裝清單提供——全新安裝不能亮紅燈。"""
        self.assertFalse((self.installed / ".git").exists())
        result = guard.evaluate(self.installed)
        self.assertEqual("install", result["baseline"])
        self.assertEqual("no_local_data", result["state"])
        self.assertEqual(0, guard.EXIT_CODES[result["state"]])

    def test_user_edit_is_detected_without_git(self):
        rules = self.installed / "rules/equipment_rules.json"
        original = rules.read_text(encoding="utf-8")
        self.addCleanup(rules.write_text, original, encoding="utf-8")
        rules.write_text('{"threshold": 999}\n', encoding="utf-8")

        result = guard.evaluate(self.installed)
        self.assertEqual("unprotected", result["state"])
        self.assertIn("rules/equipment_rules.json", result["local"])

    def test_onboarding_runs_in_the_installed_package(self):
        """裝完就要跑得起來——這是使用者第一個動作。"""
        proc = subprocess.run(
            [sys.executable, "tools/onboarding.py", "status", "--format", "json"],
            cwd=self.installed, capture_output=True, text=True, timeout=180)
        self.assertIn(proc.returncode, (0, 2), proc.stderr[-2000:])
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["steps"])


if __name__ == "__main__":
    unittest.main()

"""安裝與升級入口（tools/installer.py）的行為測試。

守住的契約：

1. **全新安裝要完整**——使用者開箱就能審圖
2. **升級不得蓋掉使用者改過的檔案**——這是整個方案存在的理由。
   上游出貨的 `rules/*.json`、`governance/核定紀錄/`、`待確認事項.md` 正好是
   開場導引第二步（逐則裁示）會寫的檔，直接覆蓋等於裁示歸零
3. **不得裝進 git clone**——那是線1 的倉庫，要走 skills/safe-update.md
4. **選用套件裝不起來不算失敗**——倉庫哲學是零安裝主線 ＋ 替代路徑
5. **歡迎檔要拿到真路徑**——這段邏輯原本在 Pascal Script 裡，沒有任何測試

這些測試全部在 Linux 上跑得起來：升級判定刻意放在 Python 而不是安裝程式殼層裡，
就是為了讓它測得到。
"""

import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import installer, make_release
from tools import update_guard as guard

SHIPPED = {
    "tools/fire_code_calc.py": "# v1 引擎\n",
    "tools/onboarding.py": "# v1 導引\n",
    "skills/onboarding.md": "# v1\n",
    "rules/equipment_rules.json": '{"threshold": 300}\n',
    "rules/rule_tests.json": '{"tests": []}\n',
    "governance/核定紀錄/results-20260101.json": '{"by": "上游種子"}\n',
    "practice_notes/index.json": '{"notes": []}\n',
    "training/registry.json": '{"batches": []}\n',
    "待確認事項.md": "# 待確認事項（上游版）\n",
    "requirements.txt": "ezdxf>=1.3,<2\n",
}

NEW_VERSION = dict(SHIPPED, **{
    "tools/fire_code_calc.py": "# v2 引擎（修了 bug）\n",
    "rules/equipment_rules.json": '{"threshold": 350}\n',   # 上游修法
    "skills/safe-update.md": "# v2 新增\n",
})


def write_tree(base, files):
    for rel, text in files.items():
        path = Path(base) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class InstallerTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.home = self.tmp / "home"
        self.home.mkdir()
        patcher = mock.patch.object(
            guard, "home_index_path",
            lambda: self.home / ".fire_review" / "backups.json")
        patcher.start()
        self.addCleanup(patcher.stop)

        # 預設不打 PyPI——測試不得依賴網路
        optional = mock.patch.object(
            installer, "install_optional_packages",
            lambda target, timeout=300: {"attempted": False, "ok": False,
                                         "reason": "測試中略過"})
        optional.start()
        self.addCleanup(optional.stop)

        self.v1 = self.make_package(self.tmp / "v1", SHIPPED, "v1.0.0")
        self.v2 = self.make_package(self.tmp / "v2", NEW_VERSION, "v2.0.0")
        self.target = self.tmp / "安裝位置"

    def make_package(self, root, files, version):
        """造一個像 make_release.py 產物的安裝包（含清單與歡迎檔）。"""
        write_tree(root, files)
        (root / make_release.WELCOME_NAME).write_text(
            make_release.WELCOME_TEMPLATE, encoding="utf-8-sig")
        packaged = sorted(p.relative_to(root).as_posix()
                          for p in root.rglob("*") if p.is_file())
        manifest = {"schema_version": 1, "version": version,
                    "files": {rel: guard.file_entry(root, rel) for rel in packaged}}
        (root / guard.MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return root

    def read(self, rel):
        return (self.target / rel).read_text(encoding="utf-8")


class FreshInstallTest(InstallerTestCase):

    def test_installs_everything_into_an_empty_folder(self):
        result = installer.install(self.v1, self.target)
        self.assertEqual(installer.FRESH, result["mode"])
        for rel in SHIPPED:
            self.assertTrue((self.target / rel).is_file(), f"少了 {rel}")
        self.assertTrue((self.target / guard.MANIFEST_NAME).is_file(),
                        "沒有安裝清單，下次升級就沒有比較基準")

    def test_creates_the_target_folder_if_missing(self):
        target = self.tmp / "還不存在" / "FireReview"
        installer.install(self.v1, target)
        self.assertTrue((target / "tools/fire_code_calc.py").is_file())

    def test_guard_reports_a_clean_install(self):
        installer.install(self.v1, self.target)
        result = guard.evaluate(self.target)
        self.assertEqual("install", result["baseline"])
        self.assertEqual("no_local_data", result["state"])

    def test_fresh_install_does_not_leave_a_pointless_empty_backup(self):
        """對空資料夾備份只會產生零筆內容的 zip，徒增困惑。"""
        result = installer.install(self.v1, self.target)
        self.assertIsNone(result["snapshot"])

    def test_installer_own_batch_file_does_not_land_in_the_users_folder(self):
        """自解壓縮檔必須把「安裝.bat」放在酬載根目錄，但使用者資料夾不該留著它。"""
        for name in installer.INSTALLER_ARTIFACTS:
            (self.v1 / name).write_text("@echo off\n", encoding="utf-8")
        installer.install(self.v1, self.target)
        for name in installer.INSTALLER_ARTIFACTS:
            self.assertFalse((self.target / name).exists(),
                             f"{name} 留在使用者的資料夾裡了")

    def test_upgrade_also_prunes_the_batch_file(self):
        """升級走 update_guard.install()，它照抄整棵樹——清理得在這一層收尾。"""
        installer.install(self.v1, self.target)
        for name in installer.INSTALLER_ARTIFACTS:
            (self.v2 / name).write_text("@echo off\n", encoding="utf-8")
        result = installer.install(self.v2, self.target)
        self.assertEqual(installer.UPGRADE, result["mode"])
        for name in installer.INSTALLER_ARTIFACTS:
            self.assertFalse((self.target / name).exists())


class UpgradeTest(InstallerTestCase):
    """本方案存在的理由：覆蓋的目標是使用者已經累積了成果的資料夾。"""

    def install_v1_then_work(self):
        installer.install(self.v1, self.target)
        # 使用者走完開場導引第二步會發生的事
        (self.target / "rules/equipment_rules.json").write_text(
            '{"threshold": 999, "裁示": "王大明 2026-07-27"}\n', encoding="utf-8")
        (self.target / "governance/核定紀錄/results-20260101.json").write_text(
            '{"by": "王大明", "decision": "維持現值"}\n', encoding="utf-8")
        (self.target / "待確認事項.md").write_text("# 全部裁示完畢\n", encoding="utf-8")
        # 使用者自己新增的
        note = self.target / "practice_notes/active/PN-1.json"
        note.parent.mkdir(parents=True, exist_ok=True)
        note.write_text('{"id": "PN-1"}\n', encoding="utf-8")
        case = self.target / "input/大樓案/平面圖.dxf"
        case.parent.mkdir(parents=True, exist_ok=True)
        case.write_text("我的圖面\n", encoding="utf-8")

    def test_user_edits_survive_the_upgrade(self):
        self.install_v1_then_work()
        result = installer.install(self.v2, self.target, by="安裝程式")

        self.assertEqual(installer.UPGRADE, result["mode"])
        self.assertIn("王大明", self.read("rules/equipment_rules.json"),
                      "使用者的裁示被上游蓋掉了")
        self.assertIn("王大明", self.read("governance/核定紀錄/results-20260101.json"))
        self.assertEqual("# 全部裁示完畢\n", self.read("待確認事項.md"))

    def test_upstream_version_is_kept_alongside(self):
        """不問就跳過等於他永遠拿不到上游的修法。"""
        self.install_v1_then_work()
        installer.install(self.v2, self.target)
        alongside = "rules/equipment_rules.json" + guard.UPSTREAM_SUFFIX
        self.assertEqual('{"threshold": 350}\n', self.read(alongside))

    def test_unmodified_files_get_the_new_version(self):
        self.install_v1_then_work()
        installer.install(self.v2, self.target)
        self.assertEqual("# v2 引擎（修了 bug）\n", self.read("tools/fire_code_calc.py"))
        self.assertEqual("# v2 新增\n", self.read("skills/safe-update.md"))

    def test_user_added_files_are_untouched(self):
        self.install_v1_then_work()
        installer.install(self.v2, self.target)
        self.assertEqual("我的圖面\n", self.read("input/大樓案/平面圖.dxf"))
        self.assertEqual('{"id": "PN-1"}\n', self.read("practice_notes/active/PN-1.json"))

    def test_upgrade_takes_a_backup_outside_the_folder(self):
        self.install_v1_then_work()
        result = installer.install(self.v2, self.target)
        backup = Path(result["snapshot"]["path"])
        self.assertTrue(backup.is_file())
        self.assertFalse(backup.resolve().is_relative_to(self.target.resolve()),
                         "備份寫進安裝資料夾了——下次重裝會把它一起換掉")

    def test_manifest_is_bumped_so_the_next_upgrade_has_a_baseline(self):
        self.install_v1_then_work()
        installer.install(self.v2, self.target)
        manifest = json.loads(
            (self.target / guard.MANIFEST_NAME).read_text(encoding="utf-8"))
        self.assertEqual("v2.0.0", manifest["version"])

    def test_guard_does_not_call_the_upgrade_a_loss(self):
        self.install_v1_then_work()
        installer.install(self.v2, self.target)
        self.assertNotEqual("suspected_loss", guard.evaluate(self.target)["state"])


class RefusalTest(InstallerTestCase):

    def test_refuses_to_install_over_a_git_clone(self):
        """線1 的倉庫不得被安裝包蓋——那會把 git 紀錄與本機成果攪在一起。"""
        clone = self.tmp / "drawing_review"
        clone.mkdir()
        (clone / ".git").mkdir()
        (clone / "AGENTS.md").write_text("# 契約\n", encoding="utf-8")

        result = installer.install(self.v1, clone)

        self.assertEqual(installer.REFUSE_GIT_CLONE, result["mode"])
        self.assertFalse((clone / "tools").exists(), "拒絕了卻還是寫了東西進去")
        self.assertEqual("# 契約\n", (clone / "AGENTS.md").read_text(encoding="utf-8"))

    def test_refusal_points_at_the_safe_update_procedure(self):
        out = io.StringIO()
        installer.describe({"mode": installer.REFUSE_GIT_CLONE, "plan": None,
                            "target": "/tmp/x", "snapshot": None, "report": None,
                            "welcome": None, "optional": None}, out=out)
        text = out.getvalue()
        self.assertIn("skills/safe-update.md", text)
        self.assertIn("git pull --ff-only", text)

    def test_a_folder_with_a_manifest_wins_over_the_git_check(self):
        """線1 倉庫裝過安裝包（少見但可能）——有清單就當升級處理，仍然安全。"""
        installer.install(self.v1, self.target)
        (self.target / ".git").mkdir()
        self.assertEqual(installer.UPGRADE, installer.classify_target(self.target))

    def test_source_without_a_manifest_is_rejected(self):
        bad = self.tmp / "不是安裝包"
        bad.mkdir()
        (bad / "隨便.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(ValueError):
            installer.install(bad, self.target)
        self.assertFalse(self.target.exists())


class WelcomeFileTest(InstallerTestCase):
    """使用者裝完看到的第一份文字——換錯就等於沒有入口。"""

    def test_placeholder_is_replaced_with_the_real_path(self):
        result = installer.install(self.v1, self.target)
        text = Path(result["welcome"]).read_text(encoding="utf-8-sig")
        self.assertNotIn(make_release.INSTALL_DIR_TOKEN, text)
        self.assertIn(str(self.target.resolve()), text)

    def test_replacement_survives_an_upgrade(self):
        installer.install(self.v1, self.target)
        installer.install(self.v2, self.target)
        text = (self.target / make_release.WELCOME_NAME).read_text(encoding="utf-8-sig")
        self.assertNotIn(make_release.INSTALL_DIR_TOKEN, text)
        self.assertIn(str(self.target.resolve()), text)

    def test_missing_welcome_file_is_not_an_error(self):
        (self.v1 / make_release.WELCOME_NAME).unlink()
        result = installer.install(self.v1, self.target)
        self.assertIsNone(result["welcome"])


class OptionalPackagesTest(InstallerTestCase):
    """零安裝主線：選用套件裝不起來是常態，不是失敗。"""

    def test_pip_failure_does_not_fail_the_install(self):
        self.addCleanup(mock.patch.stopall)
        mock.patch.stopall()
        mock.patch.object(
            guard, "home_index_path",
            lambda: self.home / ".fire_review" / "backups.json").start()
        with mock.patch.object(installer.subprocess, "run",
                               side_effect=OSError("沒有網路")):
            result = installer.install(self.v1, self.target)
        self.assertEqual(installer.FRESH, result["mode"])
        self.assertFalse(result["optional"]["ok"])
        self.assertTrue((self.target / "tools/fire_code_calc.py").is_file())

    def test_failure_message_offers_the_alternative_route(self):
        out = io.StringIO()
        installer.describe({"mode": installer.FRESH, "plan": {"new": ["a"]},
                            "target": "/tmp/x", "snapshot": None, "report": None,
                            "welcome": None,
                            "optional": {"attempted": True, "ok": False,
                                         "reason": "無網路"}}, out=out)
        text = out.getvalue()
        self.assertIn("不影響審圖", text)
        self.assertIn("替代路徑", text)

    def test_missing_requirements_file_is_reported_not_attempted(self):
        (self.v1 / "requirements.txt").unlink()
        self.target.mkdir(parents=True)
        outcome = installer.install_optional_packages(self.target)
        self.assertFalse(outcome["attempted"])


class InteractionTest(InstallerTestCase):

    def test_empty_answer_takes_the_default(self):
        default = self.tmp / "預設位置"
        chosen = installer.ask_target(default, stream=io.StringIO("\n"),
                                      prompt_stream=io.StringIO())
        self.assertEqual(default, chosen)

    def test_typed_path_wins_and_quotes_are_stripped(self):
        """檔案總管的「複製路徑」會帶雙引號——使用者很可能直接貼上。"""
        chosen = installer.ask_target(
            self.tmp / "預設位置",
            stream=io.StringIO('"D:\\我的資料\\FireReview"\n'),
            prompt_stream=io.StringIO())
        self.assertEqual("D:\\我的資料\\FireReview", str(chosen))

    def test_default_target_is_not_program_files(self):
        """工具要往自己的資料夾寫東西——Program Files 需要管理員權限。"""
        target = str(installer.default_target())
        self.assertNotIn("Program Files", target)
        self.assertTrue(target.endswith(installer.PRODUCT_DIR))

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = installer.main(list(args))
        return code, buf.getvalue()

    def test_non_interactive_mode_needs_no_input(self):
        code, _ = self.run_cli("--source", str(self.v1), "--target",
                               str(self.target), "--yes", "--no-optional",
                               "--no-pause")
        self.assertEqual(0, code)
        self.assertTrue((self.target / "tools/fire_code_calc.py").is_file())

    def test_cli_reports_a_refusal_with_a_nonzero_code(self):
        clone = self.tmp / "clone"
        clone.mkdir()
        (clone / ".git").mkdir()
        code, output = self.run_cli("--source", str(self.v1), "--target",
                                    str(clone), "--yes", "--no-optional",
                                    "--no-pause")
        self.assertEqual(2, code)
        self.assertIn("safe-update.md", output)


class InstalledPackageIsUsableTest(unittest.TestCase):
    """真的用倉庫打一次包、裝起來、跑得動——比任何單元測試都接近使用者的處境。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        repo = Path(__file__).resolve().parent.parent
        cls.result = make_release.build(repo, cls.tmp / "dist", "v0.0.0-test",
                                        stage_only=True)
        cls.stage = Path(cls.result["stage_dir"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_installed_package_runs_onboarding(self):
        target = self.tmp / "安裝位置"
        home = self.tmp / "home"
        home.mkdir(exist_ok=True)
        with mock.patch.object(guard, "home_index_path",
                               lambda: home / ".fire_review" / "backups.json"):
            installer.install(self.stage, target, with_optional=False)

        proc = subprocess.run(
            [str(Path(__import__("sys").executable)), "tools/onboarding.py",
             "status", "--format", "json"],
            cwd=target, capture_output=True, text=True, timeout=180)
        self.assertIn(proc.returncode, (0, 2), proc.stderr[-2000:])
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["steps"])


if __name__ == "__main__":
    unittest.main()

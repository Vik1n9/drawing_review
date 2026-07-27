"""線2 升級語意（tools/update_guard.py 的 install 子命令）的行為測試。

安裝程式偵測到目標資料夾已有舊版時，逐檔四種處置：

  · 不在保護範圍            → 直接更新（工具、skill、文件都是上游的）
  · 在範圍內且**未改過**    → 直接更新
  · 在範圍內且**改過**      → 保住原檔，新版另存 `.上游新版`
  · 使用者自己新增的        → 完全不動

第三種是重點：不問就覆蓋等於抹掉成果，不問就跳過等於他永遠拿不到上游的修法。
兩份都留著、把選擇權交回給他，才是唯一誠實的做法。

這些測試不需要 Windows——升級邏輯刻意放在 Python 端而不是 Inno Setup 的
Pascal Script 裡，就是為了讓它只有一份實作而且測得到。
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import update_guard as guard

SHIPPED = {
    "tools/fire_code_calc.py": "# v1 引擎\n",
    "skills/onboarding.md": "# v1 導引\n",
    "rules/equipment_rules.json": '{"threshold": 300}\n',
    "rules/rule_tests.json": '{"tests": []}\n',
    "rules/README.md": "# 規則庫說明\n",
    "governance/核定紀錄/results-20260101.json": '{"by": "上游種子"}\n',
    "practice_notes/index.json": '{"notes": []}\n',
}

NEW_VERSION = {
    "tools/fire_code_calc.py": "# v2 引擎（修了 bug）\n",
    "skills/onboarding.md": "# v2 導引\n",
    "rules/equipment_rules.json": '{"threshold": 350}\n',   # 上游修法
    "rules/rule_tests.json": '{"tests": ["新測試"]}\n',
    "rules/README.md": "# 規則庫說明（v2）\n",
    "governance/核定紀錄/results-20260101.json": '{"by": "上游種子"}\n',
    "practice_notes/index.json": '{"notes": []}\n',
    "skills/safe-update.md": "# v2 新增的 skill\n",
}


def write_tree(base, files):
    for rel, text in files.items():
        path = Path(base) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class InstallTestCase(unittest.TestCase):

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

        # 已安裝的舊版：沒有 .git（安裝包就是這樣），基準來自 安裝清單.json
        self.installed = self.tmp / "FireReview"
        write_tree(self.installed, SHIPPED)
        self.write_manifest(self.installed, "v1.0.0")

        self.new = self.tmp / "新版"
        write_tree(self.new, NEW_VERSION)
        self.write_manifest(self.new, "v2.0.0")

    def write_manifest(self, root, version):
        files = {rel: guard.file_entry(root, rel)
                 for rel in sorted(guard.iter_protected_paths(root))}
        doc = {"schema_version": 1, "version": version, "files": files}
        (Path(root) / guard.MANIFEST_NAME).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def read(self, rel):
        return (self.installed / rel).read_text(encoding="utf-8")

    def run_install(self, **kwargs):
        return guard.install(self.installed, source=self.new, by="安裝程式", **kwargs)


class UnmodifiedFilesTest(InstallTestCase):

    def test_upstream_code_is_always_updated(self):
        self.run_install()
        self.assertEqual("# v2 引擎（修了 bug）\n", self.read("tools/fire_code_calc.py"))
        self.assertEqual("# v2 導引\n", self.read("skills/onboarding.md"))

    def test_unmodified_protected_file_is_updated(self):
        """使用者沒改過的規則檔，就該拿到上游的修法。"""
        self.run_install()
        self.assertEqual('{"threshold": 350}\n', self.read("rules/equipment_rules.json"))
        self.assertFalse((self.installed / ("rules/equipment_rules.json"
                                            + guard.UPSTREAM_SUFFIX)).exists())

    def test_new_files_are_added(self):
        result = self.run_install()
        self.assertIn("skills/safe-update.md", result["plan"]["new"])
        self.assertEqual("# v2 新增的 skill\n", self.read("skills/safe-update.md"))


class ModifiedFilesTest(InstallTestCase):

    def test_user_modified_file_is_kept_and_new_version_saved_alongside(self):
        """本次需求的核心：倉庫內容不得蓋掉使用者自行訓練的資料。"""
        (self.installed / "rules/equipment_rules.json").write_text(
            '{"threshold": 999}\n', encoding="utf-8")

        result = self.run_install()

        self.assertIn("rules/equipment_rules.json", result["plan"]["preserved"])
        self.assertEqual('{"threshold": 999}\n',
                         self.read("rules/equipment_rules.json"),
                         "使用者改過的參數被上游蓋掉了")
        self.assertEqual('{"threshold": 350}\n',
                         self.read("rules/equipment_rules.json" + guard.UPSTREAM_SUFFIX),
                         "上游新版沒留下來，使用者永遠拿不到修法")

    def test_user_decisions_are_preserved(self):
        (self.installed / "governance/核定紀錄/results-20260101.json").write_text(
            '{"by": "王大明", "decision": "維持現值"}\n', encoding="utf-8")
        self.run_install()
        self.assertIn("王大明", self.read("governance/核定紀錄/results-20260101.json"))

    def test_user_added_files_are_left_untouched(self):
        case = self.installed / "input/大樓案/平面圖.dxf"
        case.parent.mkdir(parents=True)
        case.write_text("使用者的圖面\n", encoding="utf-8")
        note = self.installed / "practice_notes/active/PN-1.json"
        note.parent.mkdir(parents=True)
        note.write_text('{"id": "PN-1"}\n', encoding="utf-8")

        self.run_install()

        self.assertEqual("使用者的圖面\n", case.read_text(encoding="utf-8"))
        self.assertEqual('{"id": "PN-1"}\n', note.read_text(encoding="utf-8"))

    def test_a_protected_file_absent_from_the_old_manifest_is_preserved(self):
        """舊清單沒記到、但目標有檔——無從判斷是不是他改的，一律當成他的。"""
        note = self.installed / "practice_notes/index.json"
        note.write_text('{"notes": ["使用者的"]}\n', encoding="utf-8")
        manifest = json.loads((self.installed / guard.MANIFEST_NAME)
                              .read_text(encoding="utf-8"))
        del manifest["files"]["practice_notes/index.json"]
        (self.installed / guard.MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

        result = self.run_install()
        self.assertIn("practice_notes/index.json", result["plan"]["preserved"])
        self.assertIn("使用者的", note.read_text(encoding="utf-8"))


class InstallSafetyTest(InstallTestCase):

    def test_install_takes_a_snapshot_first(self):
        (self.installed / "rules/equipment_rules.json").write_text(
            '{"threshold": 999}\n', encoding="utf-8")
        result = self.run_install()
        backup = Path(result["snapshot"]["path"])
        self.assertTrue(backup.is_file())
        self.assertFalse(backup.resolve().is_relative_to(self.installed.resolve()),
                         "備份寫進安裝目錄了——下次重裝會把它一起換掉")

    def test_dry_run_writes_nothing(self):
        before = self.read("tools/fire_code_calc.py")
        result = self.run_install(dry_run=True)
        self.assertEqual(before, self.read("tools/fire_code_calc.py"))
        self.assertIsNone(result["snapshot"])
        self.assertTrue(result["plan"]["updated"])

    def test_manifest_is_replaced_so_the_next_upgrade_has_a_baseline(self):
        self.run_install()
        manifest = json.loads((self.installed / guard.MANIFEST_NAME)
                              .read_text(encoding="utf-8"))
        self.assertEqual("v2.0.0", manifest["version"])

    def test_report_lists_every_preserved_file(self):
        (self.installed / "rules/equipment_rules.json").write_text(
            '{"threshold": 999}\n', encoding="utf-8")
        (self.installed / "rules/rule_tests.json").write_text(
            '{"tests": ["我的"]}\n', encoding="utf-8")

        result = self.run_install()
        report = Path(result["report"]).read_text(encoding="utf-8")

        for rel in result["plan"]["preserved"]:
            self.assertIn(rel, report, f"更新報告沒提到被保留的 {rel}")
        self.assertIn(guard.UPSTREAM_SUFFIX, report)
        self.assertIn(result["snapshot"]["path"], report,
                      "更新報告沒告訴使用者備份在哪")

    def test_report_survives_when_nothing_was_preserved(self):
        result = self.run_install()
        report = Path(result["report"]).read_text(encoding="utf-8")
        self.assertIn("（無）", report)

    def test_missing_source_directory_is_rejected(self):
        with self.assertRaises(ValueError):
            guard.install(self.installed, source=self.tmp / "不存在")

    def test_guard_reports_healthy_state_after_upgrade(self):
        (self.installed / "rules/equipment_rules.json").write_text(
            '{"threshold": 999}\n', encoding="utf-8")
        self.run_install()
        result = guard.evaluate(self.installed)
        self.assertEqual("install", result["baseline"])
        self.assertNotEqual("suspected_loss", result["state"],
                            "升級本身不該被誤判成成果遺失")


if __name__ == "__main__":
    unittest.main()

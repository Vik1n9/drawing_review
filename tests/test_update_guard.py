"""本機成果守門（tools/update_guard.py）的行為測試。

守住的契約，一條都不能省：

1. **全新使用者不能看到紅燈**——第一次載入就卡住的導引沒有人會走完
2. **`git status` 答不出來的那一類要抓得到**——破壞發生後工作目錄一片乾淨，
   只有備份 manifest 還記得「這個檔案曾經是使用者的版本」
3. **備份寫在倉庫外**——repo 內就算 gitignore 也擋不住 `git clean -fdx` 與重裝
4. **共編檔不整檔還原**——會把上游的法規更新一起蓋掉
5. **救援不得造成第二次遺失**——restore 之前先備份現況，且不得蓋到來源備份
6. **保護清單漏檔要自己叫**——不變式破功時紅燈，不是靜默漏保護
"""

import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tools import update_guard as guard
from tools.update_guard import EXIT_CODES, SHARED, USER


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, check=True)


def git_available():
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


# 上游出貨的內容：資料區內同時有正典（README、.gitkeep、範例案件）與使用者要動的檔案
UPSTREAM_FILES = {
    "rules/equipment_rules.json": '{"threshold": 300}\n',
    "rules/rule_tests.json": '{"tests": []}\n',
    "rules/README.md": "# 規則庫說明（上游正典）\n",
    "rules/core/設置標準.md": "第十四條 ……\n",
    "governance/核定紀錄/results-20260101.json": '{"verified_by": "上游種子"}\n',
    "governance/README.md": "# 治理說明\n",
    "practice_notes/index.json": '{"schema_version": 1, "notes": []}\n',
    "practice_notes/active/.gitkeep": "",
    "training/registry.json": '{"schema_version": 1, "batches": []}\n',
    "training/inbox/.gitkeep": "",
    "input/README.md": "# 把圖面放這裡\n",
    "input/範例/示範圖.dxf": "上游附的範例\n",
    "graphify-out/graph.json": '{"nodes": []}\n',
    "tools/some_tool.py": "# 上游的程式碼，不屬於資料區\n",
    "skills/onboarding.md": "# 導引\n",
}


class GuardTestCase(unittest.TestCase):
    """每個測試都有自己的暫存家目錄——絕不可寫到真的家目錄。"""

    def setUp(self):
        if not git_available():
            self.skipTest("這台機器沒有 git")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self.home = self.tmp / "home"
        self.home.mkdir()
        patcher = mock.patch.object(
            guard, "home_index_path",
            lambda: self.home / ".fire_review" / "backups.json")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.repo = self.make_clone()

    def seed_upstream(self):
        """建一次上游 bare repo，之後每個 clone 都從它來。"""
        upstream = self.tmp / "upstream.git"
        if upstream.exists():
            return upstream
        work = self.tmp / "_seed"
        work.mkdir()
        for rel, text in UPSTREAM_FILES.items():
            path = work / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(work, "init", "-q", "-b", "main")
        git(work, "config", "user.email", "t@example.com")
        git(work, "config", "user.name", "測試")
        git(work, "add", "-A")
        git(work, "commit", "-qm", "上游初版")
        git(work, "clone", "-q", "--bare", str(work), str(upstream))
        return upstream

    def make_clone(self, name="案場A", parent=None):
        """造一個「上游 → clone」的真倉庫，讓 @{u} 存在。

        不能只 git init 一個目錄：那樣 git_reference() 只找得到 HEAD，
        測不出「使用者本機 commit 之後守門會不會變成假綠燈」。
        """
        upstream = self.seed_upstream()
        base = Path(parent) if parent else self.tmp
        base.mkdir(parents=True, exist_ok=True)
        clone = base / name
        subprocess.run(["git", "clone", "-q", str(upstream), str(clone)],
                       capture_output=True, check=True)
        git(clone, "config", "user.email", "t@example.com")
        git(clone, "config", "user.name", "測試")
        return clone

    # -- 造使用者成果的捷徑 --------------------------------------------------

    def edit_rule(self, value=500):
        (self.repo / "rules/equipment_rules.json").write_text(
            '{"threshold": %d}\n' % value, encoding="utf-8")

    def add_practice_note(self, name="PN-20260727-001.json"):
        path = self.repo / "practice_notes/active" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"id": "PN-1"}\n', encoding="utf-8")
        return path

    def add_case(self, case="大樓案"):
        path = self.repo / "input" / case / "平面圖.dxf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("DXF 內容\n", encoding="utf-8")
        return path

    def state(self):
        return guard.evaluate(self.repo)["state"]


class ProtectedScopeTest(GuardTestCase):
    """保護範圍：資料區內反向排除上游正典。"""

    def test_upstream_canon_inside_data_zones_is_not_user_data(self):
        protected = guard.collect_protected(self.repo)
        for rel in ("rules/README.md", "governance/README.md", "input/README.md",
                    "practice_notes/active/.gitkeep", "training/inbox/.gitkeep",
                    "input/範例/示範圖.dxf"):
            self.assertNotIn(rel, protected,
                             f"{rel} 是上游正典，不該被當成使用者成果")

    def test_files_outside_data_zones_are_not_protected(self):
        protected = guard.collect_protected(self.repo)
        for rel in ("tools/some_tool.py", "skills/onboarding.md"):
            self.assertNotIn(rel, protected, f"{rel} 不在資料區，不該進保護範圍")

    def test_user_files_are_protected(self):
        self.add_practice_note()
        self.add_case()
        protected = guard.collect_protected(self.repo)
        for rel in ("rules/equipment_rules.json",
                    "governance/核定紀錄/results-20260101.json",
                    "practice_notes/active/PN-20260727-001.json",
                    "input/大樓案/平面圖.dxf"):
            self.assertIn(rel, protected)

    def test_owner_marks_shared_files_that_upstream_also_edits(self):
        """rules/ 與 graphify-out/ 是共編——restore 不能整檔蓋回去。"""
        self.assertEqual(SHARED, guard.owner_for("rules/equipment_rules.json"))
        self.assertEqual(SHARED, guard.owner_for("rules/core/設置標準.md"))
        self.assertEqual(SHARED, guard.owner_for("graphify-out/graph.json"))
        self.assertEqual(USER, guard.owner_for("governance/核定紀錄/x.json"))
        self.assertEqual(USER, guard.owner_for("input/案件/圖.dxf"))
        self.assertEqual(USER, guard.owner_for("待確認事項.md"))


class StateMachineTest(GuardTestCase):

    def test_untouched_clone_reports_no_local_data(self):
        """全新使用者不能看到紅燈，否則第一步就卡住。"""
        result = guard.evaluate(self.repo)
        self.assertEqual("no_local_data", result["state"])
        self.assertEqual(0, EXIT_CODES[result["state"]])
        self.assertEqual("ready", guard.STEP_STATES[result["state"]])

    def test_user_work_without_backup_reports_unprotected(self):
        self.edit_rule()
        self.add_case()
        result = guard.evaluate(self.repo)
        self.assertEqual("unprotected", result["state"])
        self.assertEqual(3, EXIT_CODES[result["state"]])
        self.assertIn("rules/equipment_rules.json", result["local"])
        self.assertIn("input/大樓案/平面圖.dxf", result["local"])

    def test_snapshot_then_check_reports_protected(self):
        self.edit_rule()
        guard.snapshot(self.repo, note="更新前")
        self.assertEqual("protected", self.state())

    def test_edit_after_snapshot_reports_drifted(self):
        self.edit_rule(500)
        guard.snapshot(self.repo)
        self.edit_rule(700)
        result = guard.evaluate(self.repo)
        self.assertEqual("drifted", result["state"])
        self.assertEqual(2, EXIT_CODES[result["state"]])
        self.assertIn("rules/equipment_rules.json", result["drift"]["changed"])

    def test_local_commit_does_not_turn_the_guard_green(self):
        """比較基準是遠端追蹤分支——用 HEAD 的話 commit 完就變假綠燈。"""
        self.edit_rule()
        guard.commit(self.repo, by="測試")
        result = guard.evaluate(self.repo)
        self.assertIn("rules/equipment_rules.json", result["local"],
                      "本機 commit 之後成果就被判成「與上游相同」——守門失效了")
        self.assertNotEqual("no_local_data", result["state"])

    def test_exit_codes_match_documented_semantics(self):
        self.assertEqual({0, 2, 3, 4}, set(EXIT_CODES.values()))
        self.assertEqual(set(EXIT_CODES), set(guard.STEP_STATES))
        self.assertEqual(set(EXIT_CODES), set(guard.SEVERITY))
        for name, step in guard.STEP_STATES.items():
            with self.subTest(state=name):
                self.assertEqual(EXIT_CODES[name] == 0, step == "ready")


class SuspectedLossTest(GuardTestCase):
    """核心：破壞發生後 `git status` 一片乾淨，只有備份記得出過事。"""

    def test_file_reverted_to_upstream_content_is_flagged(self):
        self.edit_rule()
        guard.snapshot(self.repo, note="更新前")
        git(self.repo, "checkout", "--", "rules/equipment_rules.json")

        porcelain = git(self.repo, "status", "--porcelain").stdout
        self.assertEqual("", porcelain.strip(),
                         "前提破了：這個測試要驗的正是 git status 乾淨的情形")

        result = guard.evaluate(self.repo)
        self.assertEqual("suspected_loss", result["state"])
        self.assertEqual(4, EXIT_CODES[result["state"]])
        self.assertEqual("blocked", guard.STEP_STATES[result["state"]])
        self.assertEqual(["rules/equipment_rules.json"],
                         [item["path"] for item in result["lost"]])

    def test_deleted_user_file_is_flagged(self):
        note = self.add_practice_note()
        guard.snapshot(self.repo)
        note.unlink()
        result = guard.evaluate(self.repo)
        self.assertEqual("suspected_loss", result["state"])
        self.assertIn("practice_notes/active/PN-20260727-001.json",
                      [item["path"] for item in result["lost"]])

    def test_pristine_files_do_not_trigger_false_alarms(self):
        """備份當下就是上游原樣的檔案，之後還是原樣，不代表出事。"""
        self.edit_rule()
        guard.snapshot(self.repo)
        self.assertEqual("protected", self.state())

    def test_untracked_case_folder_survives_git_clean_scenario(self):
        """input/{案件}/ 是使用者唯一一份原始圖面——被刪掉一定要叫。"""
        case = self.add_case()
        guard.snapshot(self.repo)
        shutil.rmtree(case.parent)
        result = guard.evaluate(self.repo)
        self.assertEqual("suspected_loss", result["state"])
        self.assertIn("input/大樓案/平面圖.dxf",
                      [item["path"] for item in result["lost"]])


class ForeignBackupTest(GuardTestCase):
    """重新下載／重裝到別的位置——家目錄索引是唯一找得回舊備份的線索。"""

    def test_reinstall_to_another_path_reports_foreign_backup(self):
        """真實的重裝樣態：安裝程式預設同一個資料夾名，使用者換了安裝位置。"""
        self.edit_rule()
        guard.snapshot(self.repo, note="更新前")

        fresh = self.make_clone(name=self.repo.name, parent=self.tmp / "另一顆硬碟")
        result = guard.evaluate(fresh)
        self.assertEqual("foreign_backup", result["state"])
        self.assertEqual(4, EXIT_CODES[result["state"]])
        self.assertTrue(result["foreign_backups"])
        self.assertIn("重新下載或重裝", guard.format_check(result))

    def test_renaming_the_folder_too_is_a_known_blind_spot(self):
        """已知極限，寫成測試以免日後有人以為它壞了。

        索引以資料夾名認親；連名字都換掉就認不出來。要涵蓋這種情形只能放寬成
        「索引裡任何一筆都算」，但那會讓同時開兩個獨立安裝的使用者永遠卡在 ⛔。
        寧可漏報也不要製造無法解除的紅燈。
        """
        self.edit_rule()
        guard.snapshot(self.repo)
        renamed = self.make_clone(name="完全不同的名字",
                                  parent=self.tmp / "另一顆硬碟")
        self.assertEqual("no_local_data", guard.evaluate(renamed)["state"])

    def test_backup_survives_repo_deletion(self):
        self.edit_rule()
        info = guard.snapshot(self.repo)
        shutil.rmtree(self.repo)
        self.assertTrue(Path(info["path"]).is_file(),
                        "備份跟著倉庫一起消失了——那它就沒有存在的意義")


class UnlistedInvariantTest(GuardTestCase):
    """把「清單是完整的」變成每次 check 都驗的不變式。

    判準是**分區歸屬**而不是「有沒有進保護清單」——後者永遠不會觸發，
    因為 collect_protected() 與 unlisted_changes() 套用同一份 UPSTREAM_EXCLUDE。
    """

    def test_new_artifact_directory_outside_every_known_zone_is_reported(self):
        """日後有工具開始寫 reports/，保護清單沒跟上時要有人被叫醒。"""
        stray = self.repo / "reports" / "月報.json"
        stray.parent.mkdir()
        stray.write_text("{}\n", encoding="utf-8")
        result = guard.evaluate(self.repo)
        self.assertEqual("unlisted", result["state"])
        self.assertIn("reports/月報.json", result["unlisted"])
        self.assertIn("→", guard.format_check(result))

    def test_changes_in_upstream_zones_do_not_trigger_it(self):
        """維護者改 tools/、skills/、tests/ 不該天天紅燈——那會讓人學會無視它。"""
        (self.repo / "tools/some_tool.py").write_text("# 改過了\n", encoding="utf-8")
        (self.repo / "skills/onboarding.md").write_text("# 改過了\n", encoding="utf-8")
        self.assertEqual([], guard.unlisted_changes(self.repo))
        self.assertEqual("no_local_data", self.state())

    def test_work_inside_data_zones_does_not_trigger_it(self):
        self.edit_rule()
        self.add_case()
        self.assertEqual([], guard.unlisted_changes(self.repo))

    def test_known_zones_cover_the_whole_repository(self):
        """兩份分區清單合起來必須涵蓋整個倉庫，否則不變式會誤報。"""
        repo = Path(__file__).resolve().parent.parent
        known = set(guard.DATA_ZONES) | set(guard.UPSTREAM_ZONES)
        known_files = set(guard.ROOT_FILES) | set(guard.UPSTREAM_ROOT_FILES)
        for entry in repo.iterdir():
            name = entry.name
            if name.startswith(".") and name not in (".github", ".claude"):
                continue  # .git、.fire_review、編輯器暫存……都不是倉庫內容
            if name in ("dist",):
                continue  # 打包產物，已在 .gitignore
            if entry.is_dir():
                self.assertIn(name, known,
                              f"倉庫多了 {name}/ 目錄卻沒歸類——"
                              "請加進 DATA_ZONES 或 UPSTREAM_ZONES")
            elif not guard.matches_any(name, guard.UPSTREAM_EXCLUDE):
                self.assertIn(name, known_files,
                              f"倉庫根目錄多了 {name} 卻沒歸類")


class SnapshotTest(GuardTestCase):

    def test_snapshot_writes_outside_the_repo(self):
        self.edit_rule()
        info = guard.snapshot(self.repo)
        backup = Path(info["path"]).resolve()
        self.assertFalse(backup.is_relative_to(self.repo.resolve()),
                         "備份寫進倉庫內了——git clean -fdx 與重裝都會把它一起帶走")
        self.assertEqual(self.repo.resolve().parent, backup.parent)

    def test_snapshot_refuses_a_destination_inside_the_repo(self):
        with self.assertRaises(ValueError):
            guard.snapshot(self.repo, dest=self.repo / "backup.zip")

    def test_pristine_files_are_recorded_but_not_stored(self):
        """上游原樣的檔案從上游本來就拿得回來——照抄一份只會讓使用者不敢常備份。"""
        self.edit_rule()
        info = guard.snapshot(self.repo)
        with zipfile.ZipFile(info["path"]) as zf:
            stored = {n[len("files/"):] for n in zf.namelist() if n.startswith("files/")}
            manifest = json.loads(zf.read("manifest.json"))
        self.assertIn("rules/equipment_rules.json", stored)
        self.assertNotIn("governance/核定紀錄/results-20260101.json", stored)
        self.assertIn("governance/核定紀錄/results-20260101.json", manifest["entries"])

    def test_snapshot_is_idempotent_when_nothing_changed(self):
        self.edit_rule()
        first = guard.snapshot(self.repo)
        second = guard.snapshot(self.repo)
        self.assertTrue(second["skipped"])
        self.assertEqual(first["path"], second["path"])

    def test_two_snapshots_in_the_same_second_do_not_overwrite_each_other(self):
        """開發時真的發生過：救援前備份把要還原的那份備份蓋掉了。"""
        self.edit_rule(500)
        first = guard.snapshot(self.repo)
        self.edit_rule(700)
        second = guard.snapshot(self.repo)
        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue(Path(first["path"]).is_file())
        self.assertTrue(Path(second["path"]).is_file())

    def test_index_lets_a_different_directory_find_the_backup(self):
        self.edit_rule()
        info = guard.snapshot(self.repo)
        self.assertTrue(info["indexed"])
        records = json.loads(guard.home_index_path().read_text(encoding="utf-8"))
        self.assertIn(info["path"], [b["path"] for b in records["backups"]])

    def test_index_failure_does_not_lose_the_backup(self):
        """家目錄唯讀是常見的沙盒限制——索引寫不進去，備份本體還是要落地。"""
        self.edit_rule()
        with mock.patch.object(guard, "record_in_index", return_value=False):
            info = guard.snapshot(self.repo)
        self.assertFalse(info["indexed"])
        self.assertTrue(Path(info["path"]).is_file())


class RestoreTest(GuardTestCase):

    def backup_with_work(self):
        self.edit_rule()
        self.add_practice_note()
        self.add_case()
        guard.snapshot(self.repo, note="更新前")
        return guard.latest_backup(self.repo)

    def test_dry_run_writes_nothing(self):
        backup = self.backup_with_work()
        note = self.repo / "practice_notes/active/PN-20260727-001.json"
        note.unlink()
        result = guard.restore(self.repo, backup, paths=[
            "practice_notes/active/PN-20260727-001.json"], dry_run=True)
        self.assertFalse(note.exists(), "預演不該寫入任何檔案")
        self.assertEqual([], result["restored"])
        self.assertIsNone(result["pre_restore"])

    def test_restore_brings_user_files_back(self):
        backup = self.backup_with_work()
        note = self.repo / "practice_notes/active/PN-20260727-001.json"
        case = self.repo / "input/大樓案/平面圖.dxf"
        note.unlink()
        case.unlink()
        guard.restore(self.repo, backup, paths=[
            "practice_notes/active/PN-20260727-001.json",
            "input/大樓案/平面圖.dxf"], dry_run=False)
        self.assertTrue(note.is_file())
        self.assertEqual("DXF 內容\n", case.read_text(encoding="utf-8"))

    def test_shared_files_are_refused_without_the_explicit_flag(self):
        """整檔蓋回舊版會把上游的法規更新一起吃掉。"""
        backup = self.backup_with_work()
        git(self.repo, "checkout", "--", "rules/equipment_rules.json")
        result = guard.restore(self.repo, backup,
                               paths=["rules/equipment_rules.json"], dry_run=True)
        self.assertEqual(["rules/equipment_rules.json"],
                         [item["path"] for item in result["refused"]])
        self.assertEqual([], result["planned"])

    def test_shared_files_can_be_forced(self):
        backup = self.backup_with_work()
        rules = self.repo / "rules/equipment_rules.json"
        git(self.repo, "checkout", "--", "rules/equipment_rules.json")
        guard.restore(self.repo, backup, paths=["rules/equipment_rules.json"],
                      force_shared=True, dry_run=False)
        self.assertIn("500", rules.read_text(encoding="utf-8"))

    def test_restore_takes_a_pre_restore_snapshot_first(self):
        """救援本身就是覆蓋——現況比備份新是很常見的事。"""
        backup = self.backup_with_work()
        self.add_practice_note("PN-20260727-002.json")
        result = guard.restore(self.repo, backup, paths=[
            "input/大樓案/平面圖.dxf"], dry_run=False)
        self.assertIsNotNone(result["pre_restore"])
        pre = Path(result["pre_restore"]["path"])
        self.assertTrue(pre.is_file())
        self.assertNotEqual(pre.resolve(), Path(backup["path"]).resolve(),
                            "救援前備份蓋掉了要還原的來源")
        with zipfile.ZipFile(pre) as zf:
            self.assertIn("files/practice_notes/active/PN-20260727-002.json",
                          zf.namelist())

    def test_pristine_entries_are_reported_as_unavailable(self):
        backup = self.backup_with_work()
        result = guard.restore(self.repo, backup, paths=[
            "governance/核定紀錄/results-20260101.json"], dry_run=True)
        self.assertEqual(["governance/核定紀錄/results-20260101.json"],
                         [item["path"] for item in result["unavailable"]])


class CommitTest(GuardTestCase):

    def test_commit_moves_work_into_the_object_database(self):
        """未提交的改動被 checkout 蓋掉是永久消失；提交過的 reflog 救得回。"""
        self.edit_rule()
        result = guard.commit(self.repo, by="測試")
        self.assertTrue(result["ok"])
        self.assertTrue(result["committed"])
        self.assertIn("rules/equipment_rules.json", result["changed"])
        self.assertEqual("", git(self.repo, "status", "--porcelain").stdout.strip())

    def test_commit_is_a_noop_when_there_is_nothing_to_save(self):
        result = guard.commit(self.repo)
        self.assertTrue(result["ok"])
        self.assertFalse(result["committed"])

    def test_commit_does_not_stage_upstream_code(self):
        """只把資料區送進 object database，不順手 commit 別人的程式碼改動。"""
        self.edit_rule()
        (self.repo / "tools/some_tool.py").write_text("# 改過了\n", encoding="utf-8")
        guard.commit(self.repo)
        porcelain = git(self.repo, "status", "--porcelain").stdout
        self.assertIn("tools/some_tool.py", porcelain)


class WithoutGitTest(GuardTestCase):
    """線2 安裝包沒有 .git——基準改由安裝清單.json 提供。"""

    def strip_git(self):
        shutil.rmtree(self.repo / ".git")

    def write_install_manifest(self):
        protected = guard.collect_protected(self.repo)
        doc = {"schema_version": 1, "version": "v1.0.0", "files": protected}
        (self.repo / guard.MANIFEST_NAME).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_install_manifest_is_used_as_the_baseline(self):
        self.write_install_manifest()
        self.strip_git()
        self.assertEqual("no_local_data", self.state())

        self.edit_rule()
        result = guard.evaluate(self.repo)
        self.assertEqual("install", result["baseline"])
        self.assertEqual("unprotected", result["state"])
        self.assertIn("rules/equipment_rules.json", result["local"])

    def test_reverting_to_the_shipped_version_is_flagged_without_git(self):
        self.write_install_manifest()
        self.strip_git()
        self.edit_rule()
        guard.snapshot(self.repo)
        (self.repo / "rules/equipment_rules.json").write_text(
            '{"threshold": 300}\n', encoding="utf-8")
        self.assertEqual("suspected_loss", self.state())

    def test_no_git_and_no_manifest_degrades_to_unknown_without_crashing(self):
        self.strip_git()
        result = guard.evaluate(self.repo)
        self.assertEqual("unknown", result["state"])
        self.assertEqual(3, EXIT_CODES[result["state"]])
        self.assertIsNone(result["baseline"])
        self.assertIsInstance(guard.format_check(result), str)

    def test_commit_says_so_when_there_is_no_git(self):
        self.strip_git()
        result = guard.commit(self.repo)
        self.assertFalse(result["ok"])
        self.assertIn("snapshot", result["reason"])


class LargeFileTest(GuardTestCase):
    """開場診斷每次都跑——使用者的大型 DXF 不能讓它慢到沒人願意等。"""

    def test_oversized_file_is_recorded_without_a_hash(self):
        case = self.add_case()
        with mock.patch.object(guard, "MAX_HASH_BYTES", 1):
            entry = guard.file_entry(self.repo, "input/大樓案/平面圖.dxf")
        self.assertIsNone(entry["sha256"])
        self.assertEqual(case.stat().st_size, entry["size"])


class FormatTest(GuardTestCase):
    """每個狀態都要印得出人看得懂的中文，且**帶著下一步**。"""

    def test_every_state_formats_without_crashing(self):
        base = guard.evaluate(self.repo)
        for name in EXIT_CODES:
            with self.subTest(state=name):
                result = dict(base, state=name)
                result["lost"] = [{"path": "rules/x.json", "reason": "測試",
                                   "owner": USER}]
                result["unlisted"] = ["rules/x.json"]
                result["foreign_backups"] = ["/tmp/backup.zip"]
                result["backup"] = {"path": "/tmp/b.zip",
                                    "created_at": "2026-07-27T10:00:00.000001",
                                    "note": None}
                text = guard.format_check(result)
                self.assertTrue(text.strip())
                if EXIT_CODES[name] != 0:
                    self.assertIn("→", text, f"{name} 沒告訴使用者下一步該做什麼")

    def test_display_time_hides_the_sorting_microseconds(self):
        self.assertEqual("2026-07-27T10:00:00",
                         guard.display_time("2026-07-27T10:00:00.123456"))
        self.assertEqual("—", guard.display_time(None))


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.practice_note_engine import (
    CONFIRM_PHRASE,
    PLACEHOLDER,
    conflict_check,
    draft_from_candidate,
    main,
    next_note_id,
    reindex,
    run_tests,
    validate_schema,
)


def make_repo(tmp):
    root = Path(tmp)
    (root / "practice_notes" / "active").mkdir(parents=True)
    (root / "practice_notes" / "staging").mkdir(parents=True)
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "equipment_rules.json").write_text(json.dumps({"rules": [
        {"id": "sprinkler-threshold", "legal_basis": "§17", "verified": True},
        {"id": "fire-alarm-threshold", "legal_basis": "§19", "verified": False},
    ]}), encoding="utf-8")
    (root / "rules" / "regulation_index.json").write_text(
        json.dumps({"by_article": {"17": ["article-017"], "19": ["article-019"]}}), encoding="utf-8")
    return root


def good_note(note_id="PN-20260725-001", decision="strengthen", rule="sprinkler-threshold",
              article="17", conditions=None):
    return {
        "id": note_id,
        "ref_article": article,
        "ref_rule_ids": [rule],
        "scenario": {"summary": "挑空區超過 12 公尺且該區無常駐人員",
                     "conditions": conditions or {"space_type": "挑空區", "ceiling_height_gt_m": 12}},
        "judgment": {"equipment": "自動撒水設備", "decision": decision,
                     "detail": "依 §17 但書及主管機關函釋，本情境加強設置紅外線火焰探測器"},
        "source_case": "測試案件",
        "status": "active",
        "created": "2026-07-25T10:00:00+08:00",
    }


def write_note(root, note, subdir="active"):
    path = root / "practice_notes" / subdir / f"{note['id']}.json"
    path.write_text(json.dumps(note, ensure_ascii=False), encoding="utf-8")
    return path


class SchemaTest(unittest.TestCase):
    def test_a_complete_note_validates(self):
        self.assertEqual(validate_schema(good_note()), [])

    def test_missing_required_fields_are_reported(self):
        note = good_note()
        del note["source_case"]
        note["scenario"]["conditions"] = {}
        problems = validate_schema(note)
        self.assertTrue(any("source_case" in p for p in problems))
        self.assertTrue(any("scenario.conditions" in p for p in problems))

    def test_bad_id_format_is_rejected(self):
        self.assertTrue(any("PN-YYYYMMDD-NNN" in p
                            for p in validate_schema(good_note(note_id="note-1"))))

    def test_unknown_decision_is_rejected(self):
        self.assertTrue(any("judgment.decision" in p
                            for p in validate_schema(good_note(decision="whatever"))))

    def test_empty_ref_rule_ids_is_rejected(self):
        note = good_note()
        note["ref_rule_ids"] = []
        self.assertTrue(any("ref_rule_ids" in p for p in validate_schema(note)))

    def test_placeholders_block_validation(self):
        """草案的（待填）必須由人工填實，嚴禁 Agent 推測填充。"""
        note = good_note()
        note["judgment"]["detail"] = PLACEHOLDER
        problems = validate_schema(note)
        self.assertTrue(any("judgment.detail" in p and PLACEHOLDER in p for p in problems))


class ConflictCheckTest(unittest.TestCase):
    def test_clean_note_has_no_blocking_or_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = conflict_check(good_note(), root)
            self.assertEqual(result["blocking"], [])
            self.assertEqual(result["warnings"], [])

    def test_unknown_rule_id_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = conflict_check(good_note(rule="no-such-rule"), root)
            self.assertTrue(any("no-such-rule" in b for b in result["blocking"]))

    def test_unknown_article_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = conflict_check(good_note(article="999"), root)
            self.assertTrue(any("999" in b for b in result["blocking"]))

    def test_exempting_decision_raises_a_red_warning(self):
        """免除法定應設設備一律紅色警示，須人工確認法源。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = conflict_check(good_note(decision="exempt"), root)
            self.assertEqual(result["blocking"], [])
            self.assertTrue(any("🔴" in w for w in result["warnings"]))

    def test_rule_verification_state_is_not_a_warning(self):
        """使用者本身即為消防專業人員，規則的 verified 旗標不再是註解的警示來源。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = conflict_check(good_note(rule="fire-alarm-threshold", article="19"), root)
            self.assertEqual(result["blocking"], [])
            self.assertEqual(result["warnings"], [])

    def test_identical_article_and_conditions_blocks_as_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note("PN-20260725-001"))
            result = conflict_check(good_note("PN-20260725-002"), root)
            self.assertTrue(any("PN-20260725-001" in b for b in result["blocking"]))

    def test_same_condition_keys_with_different_values_only_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note("PN-20260725-001"))
            other = good_note("PN-20260725-002",
                              conditions={"space_type": "挑空區", "ceiling_height_gt_m": 20})
            result = conflict_check(other, root)
            self.assertEqual(result["blocking"], [])
            self.assertTrue(any("PN-20260725-001" in w for w in result["warnings"]))


class DraftTest(unittest.TestCase):
    def test_draft_leaves_judgment_fields_unfilled(self):
        note = draft_from_candidate(
            {"article": "§17", "rule_id": "sprinkler-threshold", "equipment": "自動撒水設備",
             "case_context": "3F 挑空區"}, "測試案件", "PN-20260725-001")
        self.assertEqual(note["ref_article"], "17")
        self.assertEqual(note["ref_rule_ids"], ["sprinkler-threshold"])
        self.assertEqual(note["judgment"]["decision"], PLACEHOLDER)
        self.assertTrue(validate_schema(note))

    def test_note_ids_increment_within_a_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            self.assertEqual(next_note_id(root, "20260725"), "PN-20260725-001")
            write_note(root, good_note("PN-20260725-001"))
            self.assertEqual(next_note_id(root, "20260725"), "PN-20260725-002")
            write_note(root, good_note("PN-20260725-002"), subdir="staging")
            self.assertEqual(next_note_id(root, "20260725"), "PN-20260725-003")


class ApplyTest(unittest.TestCase):
    def apply_argv(self, root, path, **kwargs):
        argv = ["--root", str(root), "apply", "--draft", str(path),
                "--approved-by", kwargs.get("approved_by", "測試人員"),
                "--confirm", kwargs.get("confirm", CONFIRM_PHRASE)]
        if kwargs.get("ack"):
            argv += ["--acknowledge-conflict", kwargs["ack"]]
        return argv

    def test_wrong_confirm_phrase_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = write_note(root, good_note(), subdir="staging")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(self.apply_argv(root, path, confirm="好")), 2)
            self.assertFalse((root / "practice_notes" / "active" / "PN-20260725-001.json").exists())

    def test_blocking_problems_refuse_even_with_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = write_note(root, good_note(rule="no-such-rule"), subdir="staging")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(self.apply_argv(root, path)), 2)

    def test_red_warning_requires_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = write_note(root, good_note(decision="exempt"), subdir="staging")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(self.apply_argv(root, path)), 2)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.apply_argv(root, path, ack="§17 但書，函釋字號 X")), 0)
            note = json.loads((root / "practice_notes" / "active" / "PN-20260725-001.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(note["conflict_acknowledgement"], "§17 但書，函釋字號 X")

    def test_apply_moves_note_and_writes_governance_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = write_note(root, good_note(), subdir="staging")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(self.apply_argv(root, path)), 0)
            self.assertFalse(path.exists())
            note = json.loads((root / "practice_notes" / "active" / "PN-20260725-001.json")
                              .read_text(encoding="utf-8"))
            self.assertEqual(note["approved_by"], "測試人員")
            self.assertTrue(note["approved"])
            log = root / "governance" / "註解紀錄" / "PN-20260725-001.md"
            self.assertTrue(log.is_file())
            self.assertIn("PN-20260725-001", log.read_text(encoding="utf-8"))

    def test_apply_reindexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = write_note(root, good_note(), subdir="staging")
            with contextlib.redirect_stdout(io.StringIO()):
                main(self.apply_argv(root, path))
            index = json.loads((root / "practice_notes" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["count"], 1)
            self.assertEqual(index["by_article"]["17"], ["PN-20260725-001"])


class ReindexAndTestTest(unittest.TestCase):
    def test_index_groups_by_article_equipment_and_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note("PN-20260725-001"))
            index = reindex(root)
            self.assertEqual(index["count"], 1)
            self.assertEqual(index["by_equipment"]["自動撒水設備"], ["PN-20260725-001"])
            self.assertEqual(index["by_rule_id"]["sprinkler-threshold"], ["PN-20260725-001"])

    def test_superseded_notes_are_excluded_from_the_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            note = good_note("PN-20260725-001")
            note["status"] = "superseded"
            write_note(root, note)
            self.assertEqual(reindex(root)["count"], 0)

    def test_run_tests_is_green_on_a_consistent_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note())
            reindex(root)
            failures, active, staging = run_tests(root)
            self.assertEqual(failures, [])
            self.assertEqual((active, staging), (1, 0))

    def test_run_tests_catches_a_stale_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note())
            reindex(root)
            write_note(root, good_note("PN-20260725-002",
                                       conditions={"space_type": "中庭"}))
            failures, _, _ = run_tests(root)
            self.assertTrue(any("不同步" in f for f in failures))

    def test_run_tests_catches_filename_id_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "practice_notes" / "active" / "PN-20260725-009.json").write_text(
                json.dumps(good_note("PN-20260725-001"), ensure_ascii=False), encoding="utf-8")
            failures, _, _ = run_tests(root)
            self.assertTrue(any("檔名與 id 不一致" in f for f in failures))

    def test_strict_test_exits_nonzero_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            write_note(root, good_note(rule="no-such-rule"))
            reindex(root)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--root", str(root), "test", "--strict"]), 1)


if __name__ == "__main__":
    unittest.main()

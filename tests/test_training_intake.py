import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from tools.training_intake import (
    apply_plan,
    check_destination,
    classify_file,
    classify_inbox,
    count_active_corrections,
    count_practice_notes,
    main,
    status,
)


def make_repo(tmp):
    root = Path(tmp)
    (root / "training" / "inbox").mkdir(parents=True)
    (root / "rules" / "core" / "1各類場所消防安全設備設置標準_assets").mkdir(parents=True)
    (root / "rules" / "checklists").mkdir(parents=True)
    (root / "rules" / "equipment_rules.json").write_text(
        json.dumps({"rules": [{"id": "a", "verified": False}, {"id": "b", "verified": True}]}),
        encoding="utf-8")
    return root


def drop(root, name, content=""):
    path = root / "training" / "inbox" / name
    path.write_text(content, encoding="utf-8")
    return path


def fulltext(articles=25):
    return "\n".join(f"## 第 {i} 條\n內容" for i in range(1, articles + 1))


class ClassifyTest(unittest.TestCase):
    def test_regulation_fulltext_always_needs_confirmation(self):
        """rules/core/ 必須維持單一全文 md，新全文是替換不是並存。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "新法規全文.md", fulltext())
            item = classify_file(path, root=root)
            self.assertEqual(item["kind"], "regulation-fulltext")
            self.assertEqual(item["destination"], "rules/core/新法規全文.md")
            self.assertTrue(item["needs_confirmation"])

    def test_short_markdown_is_not_mistaken_for_fulltext(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "備忘.md", fulltext(3))
            self.assertEqual(classify_file(path, root=root)["kind"], "unknown")

    def test_article_asset_routes_to_the_assets_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = root / "training" / "inbox" / "article-18-page-2.png"
            path.write_bytes(b"\x89PNG")
            item = classify_file(path, root=root)
            self.assertEqual(item["kind"], "regulation-asset")
            self.assertEqual(item["destination"],
                             "rules/core/1各類場所消防安全設備設置標準_assets/article-18-page-2.png")
            self.assertFalse(item["needs_confirmation"])

    def test_article_asset_needs_confirmation_without_a_unique_assets_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "rules" / "core" / "另一份_assets").mkdir()
            path = root / "training" / "inbox" / "article-18-page-2.png"
            path.write_bytes(b"\x89PNG")
            self.assertTrue(classify_file(path, root=root)["needs_confirmation"])

    def test_judgment_checklist_routes_to_rules_checklists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "設置標準14~31條判斷用.xlsx", "x")
            item = classify_file(path, root=root)
            self.assertEqual(item["kind"], "judgment-checklist")
            self.assertEqual(item["destination"], "rules/checklists/設置標準14~31條判斷用.xlsx")

    def test_format_template_stays_in_the_batch_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "第一階段-格式範本.xlsx", "x")
            item = classify_file(path, root=root, batch_rel="training/測試-20260725")
            self.assertEqual(item["kind"], "format-template")
            self.assertEqual(item["destination"], "training/測試-20260725/formats/第一階段-格式範本.xlsx")

    def test_case_feedback_is_never_written_into_the_notes_file(self):
        """回饋筆記必須經人工確認後依既有格式追加，工具不代寫。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "回饋.md", "- Error: 判錯了\n- Correction: 應該這樣")
            item = classify_file(path, root=root, batch_rel="training/測試-20260725")
            self.assertEqual(item["kind"], "case-feedback")
            self.assertNotIn("review_corrections", item["destination"])

    def test_practice_note_json_routes_to_staging_not_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "PN-20260725-001.json", json.dumps(
                {"id": "PN-20260725-001", "ref_article": "17", "judgment": {"equipment": "自動撒水設備"}}))
            item = classify_file(path, root=root)
            self.assertEqual(item["kind"], "practice-note")
            self.assertEqual(item["destination"], "practice_notes/staging/PN-20260725-001.json")

    def test_unknown_extension_needs_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "神秘檔案.bin", "?")
            item = classify_file(path, root=root)
            self.assertEqual(item["kind"], "unknown")
            self.assertTrue(item["needs_confirmation"])

    def test_empty_inbox_yields_no_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(classify_inbox(make_repo(tmp)), [])


class ForbiddenDestinationTest(unittest.TestCase):
    def test_rule_base_and_notes_are_refused(self):
        for dest in ("rules/equipment_rules.json", "rules/mixed_use_rules.json",
                     "rules/rule_tests.json", "rules/review_corrections.md",
                     "rules/stage_two_judgment_rules.md"):
            self.assertIsNotNone(check_destination(dest), dest)

    def test_generated_and_governed_paths_are_refused(self):
        for dest in ("rules/regulation_articles/article-001.json",
                     "governance/核定紀錄/results.json",
                     "practice_notes/active/PN-20260725-001.json",
                     "input/案件/圖.dxf", "output/案件-20260725/case.json"):
            self.assertIsNotNone(check_destination(dest), dest)

    def test_legitimate_destinations_pass(self):
        for dest in ("rules/core/判斷基準.pdf", "rules/checklists/判斷用.xlsx",
                     "practice_notes/staging/PN-20260725-001.json",
                     "training/批次-20260725/formats/範本.xlsx"):
            self.assertIsNone(check_destination(dest), dest)


class ApplyTest(unittest.TestCase):
    def test_archives_original_and_copies_to_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            drop(root, "判斷用.xlsx", "x")
            items = classify_inbox(root)
            manifest, errors = apply_plan(items, "測試批次", "審圖人", root=root,
                                          batch_date="2026-07-25")
            self.assertEqual(errors, [])
            self.assertEqual(manifest["batch"], "測試批次-20260725")
            self.assertTrue((root / "rules" / "checklists" / "判斷用.xlsx").is_file())
            self.assertTrue((root / "training" / "測試批次-20260725" / "sources" / "判斷用.xlsx").is_file())
            self.assertTrue((root / "training" / "測試批次-20260725" / "NOTES.md").is_file())

    def test_unconfirmed_items_abort_without_touching_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            drop(root, "新法規全文.md", fulltext())
            manifest, errors = apply_plan(classify_inbox(root), "測試批次", "審圖人", root=root,
                                          batch_date="2026-07-25")
            self.assertIsNone(manifest)
            self.assertTrue(any("需人工確認" in e for e in errors))
            self.assertFalse((root / "rules" / "core" / "新法規全文.md").exists())
            self.assertFalse((root / "training" / "測試批次-20260725").exists())

    def test_confirmed_by_unblocks_a_flagged_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            drop(root, "新法規全文.md", fulltext())
            items = classify_inbox(root)
            items[0]["confirmed_by"] = "使用者"
            manifest, errors = apply_plan(items, "測試批次", "審圖人", root=root,
                                          batch_date="2026-07-25")
            self.assertEqual(errors, [])
            self.assertEqual(manifest["items"][0]["confirmed_by"], "使用者")
            self.assertTrue((root / "rules" / "core" / "新法規全文.md").is_file())

    def test_a_tampered_plan_cannot_write_into_the_rule_base(self):
        """訓練模式不得繞過先紅再綠。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            drop(root, "壞東西.md", "x")
            items = classify_inbox(root)
            items[0]["destination"] = "rules/equipment_rules.json"
            items[0]["needs_confirmation"] = False
            manifest, errors = apply_plan(items, "測試批次", "審圖人", root=root,
                                          batch_date="2026-07-25")
            self.assertIsNone(manifest)
            self.assertTrue(any("先紅再綠" in e for e in errors))
            self.assertEqual((root / "rules" / "equipment_rules.json").read_text(encoding="utf-8"),
                             json.dumps({"rules": [{"id": "a", "verified": False},
                                                   {"id": "b", "verified": True}]}))

    def test_registry_records_the_batch_and_format_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            drop(root, "第一階段-格式範本.xlsx", "x")
            apply_plan(classify_inbox(root), "測試批次", "審圖人", root=root, batch_date="2026-07-25")
            registry = json.loads((root / "training" / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(registry["latest_batch"], "測試批次-20260725")
            self.assertEqual(registry["assets"]["format_templates"][0]["path"],
                             "training/測試批次-20260725/formats/第一階段-格式範本.xlsx")

    def test_clear_inbox_removes_processed_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            path = drop(root, "判斷用.xlsx", "x")
            apply_plan(classify_inbox(root), "測試批次", "審圖人", root=root,
                       batch_date="2026-07-25", clear_inbox=True)
            self.assertFalse(path.exists())


class StatusTest(unittest.TestCase):
    def test_counts_active_corrections_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "rules" / "review_corrections.md").write_text(
                "### 2026-07-15 — 甲\n- Status: Active\n\n"
                "### 2026-07-12 — 乙\n- Status: Superseded\n\n"
                "### 2026-07-10 — 丙\n- Status: Active\n", encoding="utf-8")
            self.assertEqual(count_active_corrections(root), 2)

    def test_counts_practice_notes_from_index_and_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            (root / "practice_notes" / "staging").mkdir(parents=True)
            (root / "practice_notes" / "index.json").write_text(
                json.dumps({"count": 3, "notes": []}), encoding="utf-8")
            (root / "practice_notes" / "staging" / "PN-20260725-001.json").write_text("{}", encoding="utf-8")
            self.assertEqual(count_practice_notes(root), (3, 1))

    def test_status_blocks_while_the_graph_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            result = status(root)
            self.assertEqual(result["unverified_rules"], 1)
            self.assertFalse(result["ready"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--root", str(root), "status"]), 2)

    def test_status_ready_once_the_graph_is_stamped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            from tools.graph_status import main as graph_main
            with contextlib.redirect_stdout(io.StringIO()):
                graph_main(["--root", str(root), "stamp"])
                self.assertEqual(main(["--root", str(root), "status"]), 0)
            self.assertTrue(status(root)["ready"])

    def test_graph_pending_flag_blocks_even_when_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(tmp)
            from tools.graph_status import main as graph_main
            with contextlib.redirect_stdout(io.StringIO()):
                graph_main(["--root", str(root), "stamp"])
            (root / "training" / "graph_pending.json").write_text('{"reason": "graphify 未安裝"}',
                                                                  encoding="utf-8")
            self.assertFalse(status(root)["ready"])


if __name__ == "__main__":
    unittest.main()

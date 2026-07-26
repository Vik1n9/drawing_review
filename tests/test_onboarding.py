"""開場導引（tools/onboarding.py）的行為測試。

重點不只在「跑得起來」，而在守住三個契約：

1. 結束碼 `0`／`2` 的語意（有待處理步驟即 2，資訊性步驟不算待處理）
2. **寫入先問**——每條會改動系統的命令都必須標成 `寫`，AI 才知道要先取得同意
3. **工具中立**——引用 skill 的步驟必須帶自然語言請求，命令不得硬寫 python3
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from tools import onboarding as ob
from tools.onboarding import EXIT_OK, EXIT_PENDING, STEP_TOTAL, WRITE

SHEET_DIR = Path("governance") / "待確認清單"

ALL_READY_ENV = {
    "python_version": "3.11.15",
    "interpreter": "python3",
    "has_bash": True,
    "deps": [],
    "missing": [],
    "graphify": True,
    "stdlib_only": [],
}


def write_sheet(root, findings):
    """寫一份最小可用的疑義檔（pending_review.load_sheet 讀得到的形狀）。"""
    path = root / SHEET_DIR / "rule-discrepancies-20260725.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"sheet_id": "D-015", "regulation_version": "測試版", "findings": findings}
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def finding(fid, rule_id, decision=None):
    f = {"id": fid, "rule_id": rule_id, "equipment": "滅火器", "article": "§14",
         "type": "threshold"}
    if decision:
        f["decision"] = decision
    return f


def stamp_fresh_graph(root):
    """讓 graph_status.evaluate() 回 fresh：一個來源檔＋對得上的指紋。"""
    source = root / "rules" / "README.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# 規則庫\n", encoding="utf-8")
    graph = root / "graphify-out" / "graph.json"
    graph.parent.mkdir(parents=True, exist_ok=True)
    graph.write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")
    from tools import graph_status
    with contextlib.redirect_stdout(io.StringIO()):
        code = graph_status.main(["--root", str(root), "stamp"])
    assert code == 0, f"stamp 失敗（結束碼 {code}）"


@contextlib.contextmanager
def temp_repo(*, findings=None, fresh_graph=True, env=None, calc_ok=True):
    """臨時倉庫 ＋ 打樁掉外部相依，讓每個測試只驗一件事。

    onboarding 會 chdir 到 --root，所以結束時要把 cwd 還原。
    """
    original = (ob.check_env.probe, ob.run_calc, ob.training_snapshot, os.getcwd())
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        if findings is not None:
            write_sheet(root, findings)
        if fresh_graph:
            stamp_fresh_graph(root)
        ob.check_env.probe = lambda: dict(env or ALL_READY_ENV)
        ob.run_calc = lambda args, timeout=90: (calc_ok, "" if calc_ok else "測試用失敗")
        ob.training_snapshot = lambda: {}
        try:
            yield root
        finally:
            (ob.check_env.probe, ob.run_calc, ob.training_snapshot, _) = original
            os.chdir(original[3])


def steps_by_title(result):
    return {s["title"]: s for s in result["steps"]}


class OnboardingStatusTest(unittest.TestCase):

    def test_all_ready_exits_zero_and_stays_short(self):
        with temp_repo() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = ob.main(["status", "--root", str(root)])
        self.assertEqual(EXIT_OK, code)
        # 全就緒的開場不該洗版：標頭＋結論＋操作簡介提示，就三行
        self.assertEqual(3, len(buf.getvalue().strip().splitlines()))

    def test_undecided_sheet_blocks_and_flags_pending_step(self):
        findings = [finding("D-1", "extinguisher-threshold"),
                    finding("D-2", "sprinkler-threshold")]
        with temp_repo(findings=findings) as root:
            with contextlib.redirect_stdout(io.StringIO()):
                code = ob.main(["status", "--root", str(root)])
            os.chdir(root)
            result = ob.evaluate()
        self.assertEqual(EXIT_PENDING, code)
        pending = steps_by_title(result)["待確認事項裁示"]
        self.assertEqual("action", pending["state"])
        self.assertIn(pending["no"], result["outstanding"])
        self.assertTrue(any("2 則待確認" in line for line in pending["lines"]))

    def test_decided_but_unexecuted_sheet_offers_apply_not_decide(self):
        """已裁示但還沒 apply：不必再問使用者，直接執行修正即可。"""
        with temp_repo(findings=[finding("D-1", "r1", decision="採納更正")]) as root:
            os.chdir(root)
            result = ob.evaluate()
        pending = steps_by_title(result)["待確認事項裁示"]
        self.assertEqual("action", pending["state"])
        cmds = " ".join(c["cmd"] for c in pending["commands"])
        self.assertIn("apply --all", cmds)
        self.assertNotIn("decide", cmds)
        self.assertTrue(any("0 則尚未裁示、1 則已裁示待執行" in line
                            for line in pending["lines"]))

    def test_fully_resolved_sheet_only_needs_render(self):
        """apply 之後 findings 轉 resolved，剩下的只是移除疑義檔的收尾。"""
        resolved = dict(finding("D-1", "r1", decision="採納更正"), status="resolved")
        with temp_repo(findings=[resolved]) as root:
            os.chdir(root)
            result = ob.evaluate()
        pending = steps_by_title(result)["待確認事項裁示"]
        self.assertEqual("action", pending["state"])
        self.assertIn("render", " ".join(c["cmd"] for c in pending["commands"]))

    def test_missing_graph_baseline_blocks_graph_step(self):
        with temp_repo(fresh_graph=False) as root:
            with contextlib.redirect_stdout(io.StringIO()):
                code = ob.main(["status", "--root", str(root)])
            os.chdir(root)
            result = ob.evaluate()
        self.assertEqual(EXIT_PENDING, code)
        self.assertEqual("blocked", steps_by_title(result)["法規圖譜"]["state"])

    def test_failing_rule_tests_block_rules_step(self):
        with temp_repo(calc_ok=False) as root:
            os.chdir(root)
            result = ob.evaluate()
        rules = steps_by_title(result)["規則庫健康"]
        self.assertEqual("blocked", rules["state"])
        self.assertFalse(result["ready"])

    def test_missing_packages_flag_environment_step(self):
        env = dict(ALL_READY_ENV, missing=["ezdxf"], deps=[
            {"module": "ezdxf", "package": "ezdxf", "use": "交付物1", "ok": False}])
        with temp_repo(env=env) as root:
            os.chdir(root)
            result = ob.evaluate()
        environment = steps_by_title(result)["環境工具"]
        self.assertEqual("action", environment["state"])
        self.assertIn("setup.sh", " ".join(c["cmd"] for c in environment["commands"]))

    def test_no_bash_suggests_pip_instead_of_setup_sh(self):
        """Windows 情境：沒有 bash 就不該推 setup.sh。"""
        env = dict(ALL_READY_ENV, has_bash=False, interpreter="python",
                   missing=["ezdxf"], graphify=False, deps=[
                       {"module": "ezdxf", "package": "ezdxf", "use": "交付物1",
                        "ok": False}])
        with temp_repo(env=env) as root:
            os.chdir(root)
            result = ob.evaluate()
        cmds = " ".join(c["cmd"] for s in result["steps"] for c in s["commands"])
        self.assertNotIn("bash tools/setup.sh", cmds)
        self.assertIn("python -m pip install -r requirements.txt", cmds)

    def test_intro_step_is_informational_not_a_gate(self):
        """操作簡介永遠待執行，但不能因此讓 status 永遠回 2。"""
        with temp_repo() as root:
            os.chdir(root)
            result = ob.evaluate()
        self.assertEqual("info", steps_by_title(result)["操作簡介"]["state"])
        self.assertTrue(result["ready"])


class OnboardingContractTest(unittest.TestCase):
    """守住「寫入先問」與「工具中立」兩個契約。"""

    def build(self, root):
        os.chdir(root)
        return ob.evaluate()

    def test_write_commands_are_tagged_so_ai_knows_to_ask(self):
        findings = [finding("D-1", "extinguisher-threshold")]
        env = dict(ALL_READY_ENV, missing=["ezdxf"], graphify=False, deps=[
            {"module": "ezdxf", "package": "ezdxf", "use": "交付物1", "ok": False}])
        with temp_repo(findings=findings, env=env) as root:
            result = self.build(root)
        writes = [c["cmd"] for s in result["steps"] for c in s["commands"]
                  if c["kind"] == WRITE]
        # 三個會改動系統的動作都必須標成「寫」
        self.assertTrue(any("setup.sh" in c for c in writes))
        self.assertTrue(any("decide" in c for c in writes))
        self.assertTrue(any("apply" in c for c in writes))
        # 反面：唯讀命令不得被標成寫
        reads = [c["cmd"] for s in result["steps"] for c in s["commands"]
                 if c["kind"] != WRITE]
        self.assertTrue(any("pending_review.py list" in c for c in reads))
        self.assertTrue(all("apply" not in c for c in reads))

    def test_actionable_steps_carry_natural_language_request(self):
        """工具中立：待處理的步驟一定要有一句不依賴斜線指令的自然語言請求。"""
        findings = [finding("D-1", "r1")]
        env = dict(ALL_READY_ENV, missing=["ezdxf"], deps=[
            {"module": "ezdxf", "package": "ezdxf", "use": "交付物1", "ok": False}])
        with temp_repo(findings=findings, env=env, calc_ok=False) as root:
            result = self.build(root)
        for s in result["steps"]:
            if s["state"] in ob.BLOCKING:
                self.assertTrue(s["say"].strip(), f"步驟「{s['title']}」缺自然語言請求")
                self.assertNotIn("/", s["say"], "自然語言請求不該塞斜線指令")

    def test_commands_use_reported_interpreter_not_hardcoded_python3(self):
        env = dict(ALL_READY_ENV, interpreter="python", has_bash=False,
                   graphify=False)
        with temp_repo(findings=[finding("D-1", "r1")], env=env) as root:
            result = self.build(root)
        self.assertEqual("python", result["interpreter"])
        python_cmds = [c["cmd"] for s in result["steps"] for c in s["commands"]
                       if "tools/" in c["cmd"] and c["cmd"].startswith("python")]
        self.assertTrue(python_cmds)
        for cmd in python_cmds:
            self.assertTrue(cmd.startswith("python "),
                            f"命令硬寫了解譯器：{cmd}")

    def test_status_json_is_machine_readable(self):
        with temp_repo(findings=[finding("D-1", "r1")]) as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = ob.main(["status", "--root", str(root), "--format", "json"])
        self.assertEqual(EXIT_PENDING, code)
        payload = json.loads(buf.getvalue())
        self.assertEqual(STEP_TOTAL, len(payload["steps"]))
        self.assertEqual(list(range(1, STEP_TOTAL + 1)),
                         [s["no"] for s in payload["steps"]])
        self.assertFalse(payload["ready"])

    def test_step_order_follows_the_documented_sequence(self):
        with temp_repo() as root:
            result = self.build(root)
        self.assertEqual(
            ["待確認事項裁示", "法規圖譜", "環境工具", "規則庫健康", "操作簡介"],
            [s["title"] for s in result["steps"]])


class OnboardingIntroTest(unittest.TestCase):

    def test_intro_covers_the_four_deliverables_and_exits_zero(self):
        with temp_repo() as root:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = ob.main(["intro", "--root", str(root)])
        out = buf.getvalue()
        self.assertEqual(EXIT_OK, code)
        for deliverable in ("圖面審查", "問題清單", "法條檢核清單",
                            "複合用途及樓層屬性檢討"):
            self.assertIn(deliverable, out)

    def test_intro_states_the_assist_not_replace_boundary(self):
        """審圖最高原則：輸出只是輔助，最終判斷歸消防專業人員。"""
        out = ob.format_intro("python3")
        self.assertIn("輔助，不取代", out)
        self.assertIn("需人工判讀", out)
        self.assertIn("input/ 只讀不改", out)


if __name__ == "__main__":
    unittest.main()

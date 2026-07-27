"""破壞性命令攔截（tools/guard_hook.py）的行為測試。

守住三個契約：

1. **會讓本機成果永久消失的命令一定攔得下來**——這是本檔存在的理由
2. **正常工作不得被誤攔**——尤其是「命令裡只是提到那些字串」的情形。
   誤攔比漏擋更傷：使用者會學會繞過這道關卡，那它就等於不存在
3. **fail-open**——payload 壞掉、格式沒見過、任何例外，一律放行
"""

import io
import json
import unittest
from unittest import mock

from tools import guard_hook
from tools.guard_hook import EXIT_ALLOW, EXIT_BLOCK, check_command


class BlocksDestructiveCommandsTest(unittest.TestCase):
    """底線 6：使用者的訓練成果只存在本機，這些命令會不可逆地抹掉它。"""

    BLOCKED = [
        # 未提交的改動從未進 object database，reflog 也救不回
        "git reset --hard",
        "git reset --hard origin/main",
        "git checkout -- .",
        "git checkout -- rules/equipment_rules.json",
        "git checkout .",
        "git checkout -f main",
        "git restore rules/",
        # 未追蹤的 input/{案件}/ 是使用者唯一一份原始圖面
        "git clean -fd",
        "git clean -fdx",
        "git stash drop",
        "git stash clear",
        "git pull --force",
        # 倉庫或資料區被整個刪掉
        "rm -rf .",
        "rm -rf input/案件A",
        "rm -fr governance",
        "rm -rf ./training/",
    ]

    def test_destructive_commands_are_blocked(self):
        for command in self.BLOCKED:
            with self.subTest(command=command):
                self.assertIsNotNone(
                    check_command(command),
                    f"「{command}」沒被攔下——它會讓本機訓練成果永久消失")

    def test_destructive_command_hidden_in_a_chain_is_blocked(self):
        """`foo && git reset --hard` 不能從縫裡溜過去。"""
        for command in ("npm test && git reset --hard HEAD",
                        "cd /tmp; git clean -fd",
                        "git fetch origin || git checkout -- ."):
            with self.subTest(command=command):
                self.assertIsNotNone(check_command(command))

    def test_block_message_tells_the_agent_where_to_go_instead(self):
        """只說「不行」會讓 AI 換個寫法再試一次——必須給它替代路徑。"""
        message = guard_hook.block_message(check_command("git clean -fd"))
        self.assertIn("update_guard.py check", message)
        self.assertIn("skills/safe-update.md", message)


class DoesNotBlockNormalWorkTest(unittest.TestCase):
    """誤攔比漏擋更傷——使用者會學會繞過，那這道關卡就等於不存在。"""

    ALLOWED = [
        "git status",
        "git pull --ff-only",
        "git commit -m '裁示回填'",
        "git log --oneline -20",
        "git diff --stat",
        "git add -A",
        "git restore --staged",
        "git stash",
        "git stash pop",
        # 預演不刪任何東西——擋掉它只會把代理推向「不檢查就動手」
        "git clean -n",
        "git clean --dry-run",
        "git clean -nd",
        "git clean -fd --dry-run",
        # rm 只在打到倉庫或資料區時才攔
        "rm -rf /tmp/build",
        "rm -f output/案件-問題清單.md",
        "python3 tools/onboarding.py status",
        "python3 -m unittest discover tests",
    ]

    def test_normal_commands_pass(self):
        for command in self.ALLOWED:
            with self.subTest(command=command):
                self.assertIsNone(
                    check_command(command),
                    f"「{command}」被誤攔了——正常工作不該被擋")

    def test_dangerous_text_inside_quotes_is_not_a_command(self):
        """本檔開發時真的被自己的測試腳本擋下來過——引號內的不是命令。

        字面切割會把這些拆出看起來像危險命令的片段；shlex 不會。
        """
        for command in (
            'echo "git clean -fd"',
            'echo "cd /tmp && git clean -fd"',
            "grep -rn 'git reset --hard' skills/",
            'python3 tools/guard_hook.py check "git clean -fd"',
            'git commit -m "契約新增禁止 git reset --hard 的紅線"',
        ):
            with self.subTest(command=command):
                self.assertIsNone(
                    check_command(command),
                    f"「{command}」被誤攔了——危險字串只是它的參數，不是它要跑的命令")


class FailsOpenTest(unittest.TestCase):
    """這道關卡寧可漏擋，也不能因為自己壞掉就讓使用者連正常工作都做不了。"""

    def test_empty_and_non_string_input_is_allowed(self):
        for command in (None, "", 0, [], {"cmd": "git clean -fd"}):
            with self.subTest(command=command):
                self.assertIsNone(check_command(command))

    def test_unbalanced_quotes_do_not_raise(self):
        self.assertIsNone(check_command('echo "沒收尾的引號'))

    def run_hook(self, stdin_text):
        with mock.patch("sys.stdin", io.StringIO(stdin_text)), \
             mock.patch("sys.stderr", io.StringIO()):
            return guard_hook.main(["hook"])

    def test_malformed_payload_is_allowed(self):
        for payload in ("", "not json", "[]", '"字串"', "null",
                        '{"tool_input": "不是 dict"}'):
            with self.subTest(payload=payload):
                self.assertEqual(EXIT_ALLOW, self.run_hook(payload))

    def test_other_tools_are_not_inspected(self):
        payload = json.dumps({"tool_name": "Read",
                              "tool_input": {"command": "git clean -fd"}})
        self.assertEqual(EXIT_ALLOW, self.run_hook(payload))

    def test_bash_payload_with_destructive_command_is_blocked(self):
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "git reset --hard"}})
        self.assertEqual(EXIT_BLOCK, self.run_hook(payload))

    def test_bash_payload_with_normal_command_is_allowed(self):
        payload = json.dumps({"tool_name": "Bash",
                              "tool_input": {"command": "git status"}})
        self.assertEqual(EXIT_ALLOW, self.run_hook(payload))


if __name__ == "__main__":
    unittest.main()

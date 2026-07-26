"""tools/check_env.py 的測試：能力矩陣必須誠實且可行動。

目標使用者裝不了套件，所以「缺什麼」本身沒有意義——
真正有用的是「現在能做什麼、不能做的有沒有別條路」。
"""

import contextlib
import io
import unittest
import unittest.mock

from tools import check_env


class CapabilityMatrixTest(unittest.TestCase):
    def test_every_unavailable_capability_offers_an_alternative(self):
        """不能做的事一定要給替代路徑，否則等於把使用者丟在原地。"""
        for capability in check_env.probe()["capabilities"]:
            if not capability["ok"]:
                self.assertTrue(
                    capability["alternative"],
                    f"能力「{capability['name']}」不可用卻沒有替代路徑",
                )

    def test_core_review_works_with_nothing_installed(self):
        """什麼都沒裝時，法規計算與 DXF 標註仍必須可用。"""
        with unittest.mock.patch.object(check_env, "has_module", return_value=False):
            with unittest.mock.patch.object(check_env.shutil, "which", return_value=None):
                capabilities = {c["name"]: c for c in check_env.probe()["capabilities"]}

        self.assertTrue(capabilities["法規門檻計算與法條查詢"]["ok"])
        self.assertTrue(capabilities["DXF 圖面標註（交付物1）"]["ok"])
        self.assertTrue(capabilities["PDF／DOCX／XLSX 判讀"]["ok"])

    def test_zero_install_capabilities_are_marked_as_such(self):
        with unittest.mock.patch.object(check_env, "has_module", return_value=False):
            zero_install = [c for c in check_env.probe()["capabilities"] if c["zero_install"]]
        self.assertTrue(zero_install)
        self.assertTrue(all(c["ok"] for c in zero_install))

    def test_dxf_annotation_no_longer_requires_ezdxf(self):
        """交付物1 已改用 stdlib 解析，ezdxf 不得再是它的必要條件。"""
        with unittest.mock.patch.object(check_env, "has_module", return_value=False):
            capabilities = {c["name"]: c for c in check_env.probe()["capabilities"]}
        self.assertIsNone(capabilities["DXF 圖面標註（交付物1）"]["requires"])


class ProbeCompatibilityTest(unittest.TestCase):
    """onboarding.py 與既有測試依賴這些鍵，不得移除。"""

    def test_legacy_keys_still_present(self):
        env = check_env.probe()
        for key in ("python_version", "interpreter", "has_bash", "deps",
                    "missing", "graphify", "stdlib_only"):
            self.assertIn(key, env)


class StrictModeTest(unittest.TestCase):
    def test_strict_ignores_optional_packages(self):
        """CI 不得因為沒裝選用套件而紅燈——那些都有替代路徑。"""
        with unittest.mock.patch.object(check_env, "has_module", return_value=False):
            with contextlib.redirect_stdout(io.StringIO()):
                code = check_env.main(["--strict"])
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()

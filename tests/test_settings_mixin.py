"""设置桥测试（system.kernel.settings_mixin）：回归防线。

起因：P3 删掉 base.py 的 `_is_connected()` 后，`get_system_info` 仍调用它，
属真实回归。这里用真 Api 实例（不启窗口）把这类"桥方法自洽性"钉住。
"""
import unittest

from system.kernel.api import Api


class SettingsMixinTest(unittest.TestCase):

    def setUp(self):
        # 不触发 BaseApi.__init__ 的网络/线程初始化，只借 Mixin 方法
        self.api = Api.__new__(Api)
        self.api._window = None

    def test_system_info_has_version(self):
        info = self.api.get_system_info()
        self.assertIn("version", info)
        self.assertTrue(info["version"].startswith("v"))

    def test_system_info_no_service_fields(self):
        """V3.0.0 · P4 起「服务」类别已废除，系统信息不应再包含服务字段。"""
        info = self.api.get_system_info()
        self.assertNotIn("services_total", info)
        self.assertNotIn("services_running", info)

    def test_no_bridge_method_references_removed_conn_state(self):
        """桥方法不得再依赖已删除的连接状态（防止同类回归）。"""
        for m in dir(self.api):
            if m.startswith("_"):
                continue
            fn = getattr(self.api, m)
            if not callable(fn):
                continue
            try:
                # 只调用零参方法；带参方法跳过
                import inspect
                sig = inspect.signature(fn)
                if any(p.default is inspect.Parameter.empty
                       and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                       for p in list(sig.parameters.values())[1:]):
                    continue
                fn()
            except AttributeError as e:
                self.fail(f"{m} 引用了已不存在的属性: {e}")
            except Exception:
                pass   # 其它异常（如未启窗口）不算回归


if __name__ == "__main__":
    unittest.main()

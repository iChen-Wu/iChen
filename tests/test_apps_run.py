"""App 运行时（shell.api.apps.run_core / AppsMixin.run_app）单元测试

覆盖：动态加载 core.run 并执行、异常隔离（加载/执行错误收口 ok:false）、
按 id 查找、回执结构、缺失入口提示。
"""
import unittest

from system.apphost.apps import APPS_ROOT, run_core, _module_name_for


class RunCoreTest(unittest.TestCase):

    def test_demo_hello_run(self):
        result = run_core(APPS_ROOT / "work" / "demo_hello", "core.py", "demo.hello", "hello", {})
        self.assertTrue(result.get("ok"), result)
        self.assertIn("core.run", result.get("message", ""))

    def test_song_core_loads_and_routes(self):
        # byu.song：未知 action 会返回 ok:false，但证明 core 与 song 库均已成功加载
        result = run_core(APPS_ROOT / "work" / "班级管理" / "歌曲管理", "core.py", "byu.song", "ping", {})
        self.assertFalse(result.get("ok"))
        self.assertIn("未知 action", result.get("error", ""))

    def test_missing_entry(self):
        result = run_core(APPS_ROOT / "work" / "demo_hello", "not_exist.py", "demo.hello", "x", {})
        self.assertFalse(result.get("ok"))
        self.assertIn("缺少逻辑入口", result.get("error", ""))

    def test_module_name_sanitize(self):
        self.assertEqual(_module_name_for("demo.hello"), "ichen_app_demo_hello")

    def test_mixin_run_app_lookup(self):
        from system.kernel.api import Api
        # 仅验证查找与回执结构（不依赖 WYuan 连接）
        api = Api.__new__(Api)  # 不触发 BaseApi.__init__（避免起线程连 WYuan）
        out = api.run_app("no.such.app", "run", {})
        self.assertEqual(out["ok"], False)
        self.assertIn("未找到", out.get("error", ""))


if __name__ == "__main__":
    unittest.main()

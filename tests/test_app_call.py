"""App 互调测试（V3.0.0 · P3：按 id 运行时解析，替代写死模块路径的 import 直调）。

用真实 App（demo.hello）验证；不写临时 App，避免污染 apps/。
"""
import json
import tempfile
import unittest
from pathlib import Path

from system.apphost import apps
from system.apphost.apps import APPS_ROOT, call_app


class CallAppTest(unittest.TestCase):

    def test_calls_another_app_by_id(self):
        r = call_app("demo.hello", "hello", {})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["app"], "demo.hello")
        self.assertIn("来自 core.run", r.get("message", ""))

    def test_unknown_app_returns_error(self):
        r = call_app("no.such.app", "x", {})
        self.assertFalse(r["ok"])
        self.assertIn("未找到 App", r["error"])

    def test_folder_is_not_callable(self):
        """分类 / 文件夹不是 App，不能调用（按 id 解析只认 App 节点）。"""
        r = call_app("班级管理", "x", {})
        self.assertFalse(r["ok"])
        self.assertIn("未找到 App", r["error"])

    def test_depth_guard(self):
        r = call_app("demo.hello", "x", {}, _depth=99)
        self.assertFalse(r["ok"])
        self.assertIn("层级过深", r["error"])

    def test_resolves_by_id_regardless_of_path(self):
        """搬移 / 改名不改 id 也能找到——这正是「按 id 解析」的含义。"""
        # demo.hello 位于 apps/work/demo_hello，id 与目录名并不相同
        r = call_app("demo.hello", "hello", {})
        self.assertTrue(r["ok"], r)
        self.assertTrue((APPS_ROOT / "work" / "demo_hello").is_dir())


class AutostartAppsTest(unittest.TestCase):
    """App 自启动（manifest 的 autostart: true）—— 用临时 root，不碰真实 apps/。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old = apps.APPS_ROOT
        apps.APPS_ROOT = self.root

    def tearDown(self):
        apps.APPS_ROOT = self._old
        self._tmp.cleanup()

    def _mk(self, rel, app_id, autostart=None, order=None):
        d = self.root / rel
        d.mkdir(parents=True, exist_ok=True)
        meta = {"name": app_id, "id": app_id}
        if autostart is not None:
            meta["autostart"] = autostart
        if order is not None:
            meta["order"] = order
        (d / "manifest.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def test_none_declared(self):
        self._mk("work/a", "a.one")
        self.assertEqual(apps.list_autostart_apps(self.root), [])

    def test_finds_and_orders(self):
        self._mk("work/b", "b.second", autostart=True, order=2)
        self._mk("work/a", "a.first", autostart=True, order=1)
        self._mk("work/c", "c.no", autostart=False)
        ids = [n["id"] for n in apps.list_autostart_apps(self.root)]
        self.assertEqual(ids, ["a.first", "b.second"])

    def test_real_apps_have_no_autostart_by_default(self):
        """真实 apps/ 下当前没有任何 App 声明自启动——启动时桌面是干净的。"""
        self.assertEqual(apps.list_autostart_apps(apps.APPS_ROOT), [])


if __name__ == "__main__":
    unittest.main()

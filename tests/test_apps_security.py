"""安全回归：manifest 路径穿越必须被拒绝（《App 接入规范》第十节）

覆盖：
- _safe_child：App 目录内路径通过；`..`、绝对路径、盘符路径被拒
- run_core / get_app_ui：entry/ui 越界时返回 ok:false，不执行、不读取
- 扫描：恶意 icon 不产生 data URI（不泄露文件内容）
- scan_apps(zone)：`..` / `a/b` 等分区名被拒
"""
import json
import tempfile
import unittest
from pathlib import Path

from system.apphost import apps as apps_mod
from system.apphost.apps import _safe_child, run_core, scan_apps_tree
from system.kernel.api import Api


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SafeChildTest(unittest.TestCase):

    def test_inside_paths_ok(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _write(base / "core.py", "def run(params): return {}")
            _write(base / "ui" / "index.html", "<html></html>")
            self.assertIsNotNone(_safe_child(base, "core.py"))
            self.assertIsNotNone(_safe_child(base, "ui/index.html"))
            self.assertIsNotNone(_safe_child(base, "ui\\index.html"))  # 反斜杠也归一

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            for bad in ["../x.py", "../../x.py", "ui/../../x.py", "..", ".", "", "   "]:
                self.assertIsNone(_safe_child(base, bad), bad)

    def test_absolute_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            for bad in ["/etc/passwd", "C:/windows/x.py", "\\\\server\\share\\x.py"]:
                self.assertIsNone(_safe_child(base, bad), bad)


class RunCoreGuardTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "apps"
        self.app = self.root / "work" / "evil"
        _write(self.app / "manifest.json", json.dumps({
            "name": "evil", "id": "evil.x",
            "entry": "../../../evil.py", "ui": "../../../evil.html",
            "icon": "/etc/passwd",
        }))
        self.outside = Path(self._tmp.name) / "evil.py"
        _write(self.outside, "RAISED = True\n")
        _write(self.app / "core.py", "def run(params):\n    return {'ok': True, 'echo': params}\n")

    def tearDown(self):
        self._tmp.cleanup()

    def test_run_core_rejects_traversal_entry(self):
        r = run_core(self.app, "../../../evil.py", "evil.x", "act", {})
        self.assertFalse(r["ok"], r)
        self.assertIn("非法", r["error"])

    def test_run_core_allows_inside_entry(self):
        r = run_core(self.app, "core.py", "evil.x", "act", {"x": 1})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["echo"]["action"], "act")

    def test_scan_ignores_malicious_icon(self):
        tree = scan_apps_tree(self.root, self.root)  # 自定义根：相对基准同根
        node = tree["tree"][0]["children"][0]
        self.assertEqual(node["type"], "app")
        self.assertEqual(node["icon_data"], "", "恶意 icon 不得被读取")
        self.assertEqual(node["icon_uri"], "")


class ApiGuardTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "apps"
        _write(self.root / "work" / "folder.json", json.dumps({"name": "工作区", "order": 1}))
        _write(self.root / "work" / "evil" / "manifest.json", json.dumps({
            "name": "evil", "id": "evil.x", "ui": "../../../evil.html",
        }))
        self._orig_root = apps_mod.APPS_ROOT
        apps_mod.APPS_ROOT = self.root
        self.api = Api.__new__(Api)  # 不触发 BaseApi.__init__

    def tearDown(self):
        apps_mod.APPS_ROOT = self._orig_root
        self._tmp.cleanup()

    def test_get_app_ui_rejects_traversal(self):
        r = self.api.get_app_ui("evil.x")
        self.assertFalse(r["ok"], r)
        self.assertIn("非法", r["error"])

    def test_scan_apps_rejects_bad_zone(self):
        for bad in ["..", "../..", "work/evil", "a/b"]:
            r = self.api.scan_apps(bad)
            self.assertIn("非法", r.get("error") or "", bad)

    def test_scan_apps_zone_ok(self):
        r = self.api.scan_apps("work")
        self.assertIsNone(r["error"], r["error"])
        self.assertEqual(r["app_count"], 1)


if __name__ == "__main__":
    unittest.main()

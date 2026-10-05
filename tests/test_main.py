"""system/main.py 启动脚本静态检查（不真正启动 GUI）"""
import unittest

import system.main as m


class MainScriptTest(unittest.TestCase):

    def test_paths_resolve(self):
        self.assertTrue(m.SYSTEM_DIR.exists())
        self.assertTrue(m.PROJECT_ROOT.exists())
        self.assertTrue(m.DESKTOP_DIR.exists())
        self.assertTrue((m.DESKTOP_DIR / "index.html").exists())
        self.assertTrue((m.DESKTOP_DIR / "iChen.ico").exists())

    def test_modules_on_sys_path(self):
        """启动脚本应把 shared/ 加进 sys.path（未 pip install 也能跑）。"""
        import sys
        joined = [str(p) for p in sys.path]
        self.assertIn(str(m.PROJECT_ROOT / "shared"), joined)

    def test_index_uri_absolute(self):
        page = (m.DESKTOP_DIR / "index.html").as_uri()
        self.assertTrue(page.startswith("file:///"))
        self.assertIn("index.html", page)


if __name__ == "__main__":
    unittest.main()

"""get_app_ui（srcdoc 挂载通道）测试"""
import unittest

from system.kernel.api import Api


class GetAppUiTest(unittest.TestCase):

    def setUp(self):
        self.api = Api.__new__(Api)  # 不触发 BaseApi.__init__

    def test_demo_ui_html(self):
        r = self.api.get_app_ui("demo.hello")
        self.assertTrue(r["ok"], r)
        self.assertIn("<!DOCTYPE html>", r["html"])
        self.assertTrue(r["dir"].startswith("file:///"))

    def test_logic_app_ui(self):
        r = self.api.get_app_ui("byu.song")
        self.assertTrue(r["ok"], r)
        self.assertIn("<!DOCTYPE html>", r["html"])
        self.assertEqual(r["ui"], "ui/index.html")

    def test_unknown_app(self):
        r = self.api.get_app_ui("no.such.app")
        self.assertFalse(r["ok"])
        self.assertIn("未找到", r.get("error", ""))


if __name__ == "__main__":
    unittest.main()

"""shell.api.apps 附加能力测试（shared css 注入文本）"""
import unittest

from system.kernel.api import Api


class SharedCssTest(unittest.TestCase):

    def test_get_shared_css_contains_tokens_and_components(self):
        api = Api.__new__(Api)  # 不触发 BaseApi.__init__
        css = api.get_shared_css()
        self.assertIn("--color-bg", css)     # tokens.css 内容
        self.assertIn(".btn", css)           # components.css 内容
        self.assertGreater(len(css), 1000)


if __name__ == "__main__":
    unittest.main()

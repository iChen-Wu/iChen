"""默认配置基线测试（shell.kernel.settings.bootstrap）。

不碰真实 data/config：用临时目录替换模块级的 CONFIG_DIR。
"""
import tempfile
import unittest
from pathlib import Path

from system.kernel.settings import bootstrap


class BootstrapTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self._tmp.name) / "config"
        self._old = bootstrap.CONFIG_DIR
        bootstrap.CONFIG_DIR = self.config_dir

    def tearDown(self):
        bootstrap.CONFIG_DIR = self._old
        self._tmp.cleanup()

    # ---------- 基线本体 ----------

    def test_defaults_dir_exists_and_has_baseline(self):
        names = bootstrap.list_defaults()
        self.assertIn("config.yaml", names)
        self.assertIn("score_rules.json", names)
        self.assertIn("class_datacenter.json", names)

    def test_defaults_excludes_env(self):
        """密钥不能进基线。"""
        self.assertNotIn(".env", bootstrap.list_defaults())

    # ---------- 补齐行为 ----------

    def test_fills_missing_files(self):
        self.assertFalse(self.config_dir.exists())
        created = bootstrap.ensure_config()
        self.assertEqual(sorted(created), bootstrap.list_defaults())
        for name in bootstrap.list_defaults():
            self.assertTrue((self.config_dir / name).is_file(), name)

    def test_does_not_overwrite_user_modified_file(self):
        self.config_dir.mkdir(parents=True)
        target = self.config_dir / "config.yaml"
        target.write_text("USER EDITED", encoding="utf-8")
        created = bootstrap.ensure_config()
        self.assertNotIn("config.yaml", created)
        self.assertEqual(target.read_text(encoding="utf-8"), "USER EDITED")

    def test_second_run_is_noop(self):
        bootstrap.ensure_config()
        self.assertEqual(bootstrap.ensure_config(), [])


if __name__ == "__main__":
    unittest.main()

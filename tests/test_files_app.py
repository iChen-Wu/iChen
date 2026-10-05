"""「文件」App（apps/work/系统/文件）的 core 行为与安全测试。

不碰真实 data/：加载模块后把它的 ROOT 指到临时目录。
"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "apps" / "work" / "系统" / "文件" / "core.py"


def _load_core():
    """按路径加载 App 的 core.py（目录名含中文，故不用包导入）。"""
    spec = importlib.util.spec_from_file_location("ichen_app_sys_files_test", CORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FilesAppTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.core = _load_core()
        self.core.ROOT = self.root

        (self.root / "config").mkdir()
        (self.root / "config" / "a.json").write_text('{"x": 1}', encoding="utf-8")
        (self.root / "logs").mkdir()
        (self.root / "notes").mkdir()
        (self.root / "readme.md").write_text("# hi", encoding="utf-8")
        (self.root / "blob.bin").write_bytes(b"\x00\x01\x02")

    def tearDown(self):
        self._tmp.cleanup()

    def run_action(self, action, **payload):
        return self.core.run({"action": action, "payload": payload})

    # ---------- 读 ----------

    def test_root_info(self):
        r = self.run_action("root")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["path"], "")
        self.assertGreaterEqual(r["count"], 4)

    def test_list_dirs_first(self):
        r = self.run_action("list", path="")
        self.assertTrue(r["ok"], r)
        names = [e["name"] for e in r["entries"]]
        dirs = [e["dir"] for e in r["entries"]]
        self.assertEqual(dirs, sorted(dirs, reverse=True), "文件夹应排在前面")
        self.assertIn("config", names)
        self.assertIn("readme.md", names)

    def test_list_marks_sensitive(self):
        r = self.run_action("list", path="")
        by = {e["name"]: e for e in r["entries"]}
        self.assertTrue(by["config"]["sensitive"])
        self.assertFalse(by["notes"]["sensitive"])

    def test_read_text(self):
        r = self.run_action("read", path="readme.md")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["text"], "# hi")

    def test_read_binary_refused(self):
        r = self.run_action("read", path="blob.bin")
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("binary"))

    def test_raw_returns_data_uri(self):
        r = self.run_action("raw", path="blob.bin")
        self.assertTrue(r["ok"], r)
        self.assertTrue(r["data_uri"].startswith("data:"))

    # ---------- 写 ----------

    def test_mkdir_and_rename_and_delete(self):
        self.assertTrue(self.run_action("mkdir", path="", name="新目录")["ok"])
        self.assertTrue((self.root / "新目录").is_dir())

        self.assertTrue(self.run_action("rename", path="新目录", newName="改名后")["ok"])
        self.assertTrue((self.root / "改名后").is_dir())

        self.assertTrue(self.run_action("delete", paths=["改名后"], confirm=True)["ok"])
        self.assertFalse((self.root / "改名后").exists())

    def test_newfile(self):
        r = self.run_action("newfile", path="notes", name="a.md", content="hello")
        self.assertTrue(r["ok"], r)
        self.assertEqual((self.root / "notes" / "a.md").read_text(encoding="utf-8"), "hello")

    def test_move(self):
        r = self.run_action("move", paths=["readme.md"], destDir="notes")
        self.assertTrue(r["ok"], r)
        self.assertTrue((self.root / "notes" / "readme.md").is_file())

    def test_delete_requires_confirm(self):
        r = self.run_action("delete", paths=["readme.md"])
        self.assertFalse(r["ok"])
        self.assertTrue((self.root / "readme.md").is_file(), "未确认时不应删除")

    def test_mkdir_refuses_duplicate_and_illegal(self):
        self.assertFalse(self.run_action("mkdir", path="", name="notes")["ok"])
        self.assertFalse(self.run_action("mkdir", path="", name="a/b")["ok"])

    # ---------- 路径安全（核心） ----------

    def test_path_traversal_is_rejected(self):
        for bad in ("..", "../..", "notes/../..", "C:/Windows", "/etc/passwd"):
            r = self.run_action("list", path=bad)
            self.assertFalse(r["ok"], f"{bad} 应被拒绝")

    def test_cannot_delete_root(self):
        r = self.run_action("delete", paths=[""], confirm=True)
        self.assertFalse(r["ok"])
        self.assertTrue(self.root.is_dir())

    def test_cannot_rename_root(self):
        self.assertFalse(self.run_action("rename", path="", newName="x")["ok"])

    def test_cannot_move_into_own_subdir(self):
        self.assertFalse(self.run_action("move", paths=["notes"], destDir="notes")["ok"])

    def test_resolve_stays_inside(self):
        """_resolve 只认 data/ 之内的路径。"""
        self.assertIsNotNone(self.core._resolve(""))
        self.assertIsNotNone(self.core._resolve("notes"))
        self.assertIsNone(self.core._resolve("../x"))
        self.assertIsNone(self.core._resolve("D:/x"))

    # ---------- 杂项 ----------

    def test_unknown_action(self):
        self.assertFalse(self.run_action("nope")["ok"])

    def test_manifest_and_ui_present(self):
        base = CORE.parent
        self.assertTrue((base / "manifest.json").is_file())
        self.assertTrue((base / "ui" / "index.html").is_file())
        meta = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], "sys.files")
        self.assertEqual(meta["name"], "文件")

    def test_app_does_not_import_system(self):
        """App 不得 import system.*（分层约定，见 tests/test_dependency_direction.py）。"""
        text = CORE.read_text(encoding="utf-8")
        self.assertNotIn("from system", text)
        self.assertNotIn("import system", text)

    # ---------- 桥协议契约（防"回执匹配不上 → 一直卡在载入中"这类 bug 复发） ----------

    def test_ui_matches_reply_by_action_not_custom_seq(self):
        """框架回执**只带 {app, action, ...结果}**，不原样带回 payload 里的自定义字段。

        所以 App 必须按 app/action 匹配回执；一旦依赖自定义请求号就永远等不到，
        表现正是"一直停在正在载入…"。这里把该约束钉住。
        """
        ui = (CORE.parent / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("_seq", ui, "不要依赖 payload 里的自定义字段回传（框架不会带回）")
        self.assertIn("m.app === APP_ID", ui, "应按 app 匹配回执")
        self.assertIn("w.action === m.action", ui, "应按 action 做 FIFO 匹配")

    def test_framework_reply_only_carries_app_action(self):
        """反向校验：框架的回执构造确实只补 app/action（若框架改了，这条会提醒）。"""
        js = Path(__file__).resolve().parents[1] / "system" / "desktop" / "js" / "appframe.js"
        text = js.read_text(encoding="utf-8")
        self.assertIn("{ app: m.app, action: m.action }", text)

    def test_ui_never_stalls_on_loading(self):
        """列表区任何分支都要有结果：载入中 / 出错 / 空，不能停在「正在载入…」。"""
        ui = (CORE.parent / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn("showListMessage", ui)
        idx = ui.index('const r = await call("list"')
        self.assertIn("showListMessage", ui[idx:idx + 500], "失败分支必须写回列表，而不是只弹 toast")


if __name__ == "__main__":
    unittest.main()

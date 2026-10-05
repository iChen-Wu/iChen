"""apps/ 分区（zones）与目录树扫描（shell.api.apps）单元测试

结构约定（用户拍板）：apps/ 一级目录 = 主体（Tab）分区，folder.json 提供
名称/图标/顺序；App 放各分区下。
覆盖：scan_zones、按分区 scan_apps、整树统计、根目录缺失报错。
"""
import unittest

from system.apphost.apps import APPS_ROOT, scan_apps_tree, scan_zones_tree


def _all_ids(nodes, out=None):
    """收集树中所有 App 的 id（不依赖具体数量，避免用户增删 App 就红）。"""
    out = [] if out is None else out
    for n in nodes or []:
        if n.get("type") == "app":
            out.append(n.get("id"))
        if n.get("children"):
            _all_ids(n["children"], out)
    return out


def _all_names(nodes, out=None):
    out = [] if out is None else out
    for n in nodes or []:
        out.append(n.get("name"))
        if n.get("children"):
            _all_names(n["children"], out)
    return out


class ScanZonesTest(unittest.TestCase):

    def test_zones_from_apps_root(self):
        r = scan_zones_tree()
        self.assertIsNone(r["error"], r["error"])
        names = [z["name"] for z in r["zones"]]
        keys = [z["key"] for z in r["zones"]]
        # order：工作区(1) → 空间(2)；显示名用户可在「App 管理」里改，不写死
        self.assertEqual(keys, ["work", "space"], keys)
        self.assertTrue(names[0] and names[1], "分区显示名不应为空")
        for z in r["zones"]:
            self.assertTrue(z["icon_data"].startswith("data:image/svg+xml;base64,"), z["key"])
            self.assertEqual(z["path"], z["key"])

    def test_zone_missing_root(self):
        r = scan_zones_tree(APPS_ROOT / "not_exist")
        self.assertIsNotNone(r["error"])
        self.assertEqual(r["zones"], [])


class ScanZoneTreeTest(unittest.TestCase):

    def test_work_zone_tree(self):
        r = scan_apps_tree(APPS_ROOT / "work")
        self.assertIsNone(r["error"], r["error"])
        # 断言"包含已知 App"而非精确数量：用户随时可能增删自己的 App
        ids = _all_ids(r["tree"])
        self.assertGreaterEqual(r["app_count"], 5, r["app_count"])
        for expected in ("demo.hello", "byu.song", "byu.datacenter", "byu.points", "icon", "idle"):
            self.assertIn(expected, ids, f"work 分区应含 {expected}")
        top = [n["name"] for n in r["tree"]]
        # 分类(班级管理 order1) 在前；app 无 order 按名称
        self.assertEqual(top[0], "班级管理", top)
        self.assertIn("图标集", _all_names(r["tree"]))
        folder = [n for n in r["tree"] if n["type"] == "folder"][0]
        song = [c for c in folder["children"] if c.get("id") == "byu.song"][0]
        self.assertEqual(song["path"], "work/班级管理/歌曲管理")
        self.assertTrue(song["icon_data"].startswith("data:image/svg+xml;base64,"))

    def test_space_zone_tree(self):
        """space 分区现在含 qxia / wyuan 两个占位 App。"""
        r = scan_apps_tree(APPS_ROOT / "space")
        self.assertIsNone(r["error"], r["error"])
        self.assertEqual(r["app_count"], 2)
        ids = _all_ids(r["tree"])
        self.assertIn("qxia", ids)
        self.assertIn("wyuan", ids)

    def test_full_tree_counts_all_zones(self):
        r = scan_apps_tree(APPS_ROOT)
        # 跨分区扫到的 App 至少覆盖 work 里那几个（数量随用户增删变化，不写死）
        self.assertGreaterEqual(r["app_count"], 5, r["app_count"])
        for expected in ("demo.hello", "byu.song", "byu.datacenter", "byu.points"):
            self.assertIn(expected, _all_ids(r["tree"]))
        # scan_apps_tree 顶层节点仍是 folder 语义；确认根下只有 work/space 两个分区目录
        # （显示名可由用户在「App 管理」编辑，这里只断言稳定的目录名）
        top = [n["path"] for n in r["tree"]]
        self.assertEqual(top, ["work", "space"], top)

    def test_mixin_scan_apps_zone(self):
        from system.kernel.api import Api
        api = Api.__new__(Api)  # 不触发 BaseApi.__init__
        # 未知分区 → error
        bad = api.scan_apps("no_such_zone")
        self.assertIsNotNone(bad["error"])
        self.assertEqual(bad["tree"], [])
        # zones 列表通路
        zones = api.scan_zones()
        self.assertEqual([z["key"] for z in zones["zones"]], ["work", "space"])
        self.assertIsNone(zones["error"], zones["error"])


if __name__ == "__main__":
    unittest.main()

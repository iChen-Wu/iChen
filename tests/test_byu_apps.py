"""BYu 外壳化 App 的运行时测试（byu.datacenter / byu.points）

覆盖：core.py 能被 shell 的 run_core 动态加载、成功 import 对应 BYu 业务库、
action 路由生效（未知 action 明确报错，而不是"业务库加载失败"）。
"""
import unittest

from system.apphost.apps import APPS_ROOT, run_core

DATACENTER_DIR = APPS_ROOT / "work" / "班级管理" / "数据中心"
POINTS_DIR = APPS_ROOT / "work" / "班级管理" / "积分管理"


class DatacenterAppTest(unittest.TestCase):

    def test_core_loads_and_routes(self):
        # 能路由到"未知 action"即证明 core.py 与 datacenter 业务库都加载成功
        r = run_core(DATACENTER_DIR, "core.py", "byu.datacenter", "no_such_action", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("未知 action", r.get("error", ""))

    def test_types_action_reads_whitelist(self):
        r = run_core(DATACENTER_DIR, "core.py", "byu.datacenter", "types", {})
        self.assertTrue(r.get("ok"), r)
        self.assertIn("person", (r.get("data") or {}).get("allowed", []))

    def test_view_requires_entity_id(self):
        r = run_core(DATACENTER_DIR, "core.py", "byu.datacenter", "view", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("entity_id", r.get("error", ""))


class PointsAppTest(unittest.TestCase):

    def test_core_loads_and_routes(self):
        r = run_core(POINTS_DIR, "core.py", "byu.points", "no_such_action", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("未知 action", r.get("error", ""))

    def test_import_json_requires_content(self):
        r = run_core(POINTS_DIR, "core.py", "byu.points", "import_json", {"json": "   "})
        self.assertFalse(r.get("ok"))
        self.assertIn("未提供 JSON", r.get("error", ""))

    def test_reset_requires_confirm(self):
        # 危险操作必须显式确认，未确认一律中止（不碰数据库）
        r = run_core(POINTS_DIR, "core.py", "byu.points", "reset", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("未确认", r.get("error", ""))

    def test_correct_record_requires_entity_id(self):
        r = run_core(POINTS_DIR, "core.py", "byu.points", "correct_record", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("entity_id", r.get("error", ""))

    def test_correct_record_passes_recorder(self):
        # 纠错必须能改「记录人」（recorder）：core.py 需把它透传给 store.correct_record。
        # 这里 patch 掉业务函数（不落库），只校验 payload -> store 的参数透传。
        from unittest import mock
        from BYu.class_manager.points import points_store
        with mock.patch.object(points_store, "correct_record", return_value=True) as m:
            r = run_core(POINTS_DIR, "core.py", "byu.points", "correct_record",
                         {"entity_id": "ent-1", "event": "早读迟到", "persons": "ZBY,WGF",
                          "score": "-1", "recorder": "HHR", "remark": "改记录人"})
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(m.call_args.kwargs.get("recorder"), "HHR")
        self.assertEqual(m.call_args.kwargs.get("persons"), ["ZBY", "WGF"])

    def test_correct_record_recorder_absent_means_keep(self):
        # 未提交 recorder 时传 None（store 语义：None = 不改），避免误清空记录人
        from unittest import mock
        from BYu.class_manager.points import points_store
        with mock.patch.object(points_store, "correct_record", return_value=True) as m:
            run_core(POINTS_DIR, "core.py", "byu.points", "correct_record",
                     {"entity_id": "ent-1", "event": "早读迟到"})
        self.assertIsNone(m.call_args.kwargs.get("recorder"))

    def test_ui_exposes_recorder_field(self):
        # 纠错抽屉必须提供「记录人」输入框，且保存时提交 recorder（否则界面改不了记载人）
        html = (POINTS_DIR / "ui" / "index.html").read_text(encoding="utf-8")
        self.assertIn('"d-recorder"', html)
        self.assertIn("r.recorder", html)
        self.assertIn('recorder: $("d-recorder")', html)

    # ---------- 导入去重（同一批日志被识别两次不再重复落库） ----------

    def test_create_points_records_skips_existing_id(self):
        from unittest import mock
        from BYu.class_manager.points import points_store
        units = [
            {"Operation": "event", "id": "2026091901",
             "data": {"item_event": "早操前迟到", "person_list": ["ZBY"], "date": "2026-09-19"}},
            {"Operation": "event", "id": "2026091999",
             "data": {"item_event": "课堂积极", "person_list": ["ZBY"], "date": "2026-09-19"}},
        ]
        fake_client = mock.MagicMock()
        fake_client.batch_create_entities.return_value = ["eid-new"]
        stats = {}
        with mock.patch.object(points_store, "load_person_map", return_value=({}, {})), \
             mock.patch.object(points_store, "existing_record_ids", return_value={"2026091901"}), \
             mock.patch.object(points_store, "get_client", return_value=fake_client):
            pairs = points_store.create_points_records(units, stats=stats)
        self.assertEqual(pairs, [("2026091999", "eid-new")])
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["skipped_ids"], ["2026091901"])
        created = fake_client.batch_create_entities.call_args[0][0]
        self.assertEqual([c["extra"]["id"] for c in created], ["2026091999"])

    def test_create_points_records_all_duplicate_writes_nothing(self):
        from unittest import mock
        from BYu.class_manager.points import points_store
        units = [{"Operation": "event", "id": "2026091901",
                  "data": {"item_event": "早操前迟到", "person_list": [], "date": "2026-09-19"}}]
        fake_client = mock.MagicMock()
        stats = {}
        with mock.patch.object(points_store, "load_person_map", return_value=({}, {})), \
             mock.patch.object(points_store, "existing_record_ids", return_value={"2026091901"}), \
             mock.patch.object(points_store, "get_client", return_value=fake_client):
            pairs = points_store.create_points_records(units, stats=stats)
        self.assertEqual(pairs, [])
        self.assertEqual(stats["created"], 0)
        self.assertEqual(stats["skipped"], 1)
        fake_client.batch_create_entities.assert_not_called()

    def test_import_json_reports_skipped(self):
        from unittest import mock
        from BYu.class_manager.points import points_store

        def fake_create(units, initial_status=None, stats=None, **_kw):
            if stats is not None:
                stats.update({"created": 0, "skipped": 2, "skipped_ids": ["a", "b"]})
            return []

        payload = {"json": '[{"Operation": "event", "id": "a", "data": {"item_event": "x"}}]'}
        with mock.patch.object(points_store, "create_points_records", side_effect=fake_create):
            r = run_core(POINTS_DIR, "core.py", "byu.points", "import_json", payload)
        self.assertTrue(r.get("ok"), r)
        self.assertIn("跳过 2 条重复", r.get("message", ""))

    # ---------- 批量删除（界面清理重复记录用） ----------

    def test_delete_records_batch(self):
        from unittest import mock
        from BYu.class_manager.points import points_store
        with mock.patch.object(points_store, "soft_delete_record", return_value=True) as m:
            r = run_core(POINTS_DIR, "core.py", "byu.points", "delete_records",
                         {"entity_ids": "e1,e2,e3"})
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["data"]["deleted"], 3)
        self.assertEqual([c.args[0] for c in m.call_args_list], ["e1", "e2", "e3"])

    def test_delete_records_requires_selection(self):
        r = run_core(POINTS_DIR, "core.py", "byu.points", "delete_records", {})
        self.assertFalse(r.get("ok"))
        self.assertIn("未选择", r.get("error", ""))

    def test_delete_records_all_failed(self):
        from unittest import mock
        from BYu.class_manager.points import points_store
        with mock.patch.object(points_store, "soft_delete_record", return_value=False):
            r = run_core(POINTS_DIR, "core.py", "byu.points", "delete_records",
                         {"entity_ids": ["gone-1"]})
        self.assertFalse(r.get("ok"))
        self.assertIn("删除失败", r.get("error", ""))

    def test_ui_exposes_batch_delete(self):
        html = (POINTS_DIR / "ui" / "index.html").read_text(encoding="utf-8")
        for needle in ['id="btn-del-selected"', 'id="chk-rec-all"', "row-chk",
                       'call("delete_records"', "重复×"]:
            self.assertIn(needle, html)


if __name__ == "__main__":
    unittest.main()

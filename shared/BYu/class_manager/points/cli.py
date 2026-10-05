# cli.py
# =============================================================================
# 模块：命令行交互界面（V3.0 简化流程）
# =============================================================================
# 功能：
#   1. 班务日志识别 / JSON 导入
#   2. 编辑单识别 / JSON 导入
#   3. 统一纠错（积分记录 + 编辑请求）
#   4. 应用并预览（应用编辑 → 校验 → 匹配 → 预览）
#   5. 编辑（手动修改字段）
#   6. 上传积分
#   7. 查询历史
#   8. 数据管理
#   0. 退出
# =============================================================================

import sys
import os
import json
import copy
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

# ============================================================
# 使用包绝对导入
# ============================================================
from BYu.class_manager.points.points_core import PointsProcessor
from BYu.class_manager.points.config import NAME_CODE_MAP, ABBR_TO_NAME
from BYu.class_manager.points.validator import is_valid_event_name



class InteractivePointsCLI:
    """班级积分管理命令行界面（V3.0）"""

    def __init__(self):
        self.processor = PointsProcessor(verbose=True, debug=True)
        self.current_data: List[Dict] = []
        self.backup_data: List[Dict] = []
        self.history: List[Dict] = []
        self.data_file: Optional[str] = None
        # 状态跟踪
        self.is_ready: bool = False
        self.final_events: List[Dict] = []

    # ============================================================
    # 主循环
    # ============================================================

    def run(self):
        self._print_banner()
        self._restore_from_store()
        while True:
            self._show_menu()
            choice = input("\n请选择操作: ").strip().lower()

            if choice == "0":
                self._exit()
                break
            elif choice == "1":
                self._import_log()
            elif choice == "2":
                self._import_edits_menu()
            elif choice == "3":
                self._correct_all()
            elif choice == "4":
                self._apply_and_preview()
            elif choice == "5":
                self._free_edit()
            elif choice == "6":
                self._upload()
            elif choice == "7":
                self._history_browser()
            elif choice == "8":
                self._data_management()
            else:
                print("❌ 无效选择，请重新输入")

    # ============================================================
    # 启动恢复：从数据中枢找回未完成记录（防丢失核心）
    # ============================================================

    def _restore_from_store(self):
        """启动时从库加载待处理记录（pending_review / pending_match / matched）"""
        from BYu.class_manager.points import points_store as store

        units = self._reload_pending()
        if units:
            self.current_data = units
            self._update_ready_from_store()
            stats = store.count_by_status()
            print(f"\n💾 已从数据中枢恢复 {len(units)} 条待处理记录")
            print(f"   待纠错 {stats.get('pending_review', 0)} | 待匹配 "
                  f"{stats.get('pending_match', 0)} | 已匹配 {stats.get('matched', 0)} | "
                  f"已上传 {stats.get('uploaded', 0)}")
        else:
            self.current_data = []

    def _reload_pending(self):
        """从库加载待处理记录（排除 uploaded / cancelled，即未完结的）"""
        from BYu.class_manager.points import points_store as store

        return (self.processor.load_store_units(status=store.STATUS_PENDING_REVIEW)
                + self.processor.load_store_units(status=store.STATUS_PENDING_MATCH)
                + self.processor.load_store_units(status=store.STATUS_MATCHED))

    def _update_ready_from_store(self):
        """若库中有 matched 记录，恢复为已就绪状态（可直接上传）"""
        from BYu.class_manager.points import points_store as store

        matched = self.processor.load_store_units(status=store.STATUS_MATCHED)
        if matched:
            self.final_events = [{
                "id": u.get("id"),
                "item_event": (u.get("data") or {}).get("item_event", "?"),
                "person_list": (u.get("data") or {}).get("person_list", []),
                "points": float(u.get("points", 0)),
                "_match_source": u.get("_match_source", "store"),
            } for u in matched]
            self.is_ready = True

    # ============================================================
    # 界面显示
    # ============================================================

    def _print_banner(self):
        print("=" * 70)
        print("  📊 班级积分管理系统 V3.0  (简化流程)")
        print("=" * 70)
        print("  流程：导入 → 生成预览 → 确认 → 上传")
        print("=" * 70)

    def _show_menu(self):
        data_count = len(self.current_data)
        status_text = "✅ 已就绪" if self.is_ready else "⚠️ 未就绪（需预览）"
        if self.is_ready:
            status_text += f" (事件数: {len(self.final_events)})"
        has_backup = "💾" if self.backup_data else ""

        print("\n" + "=" * 70)
        print(f"  当前数据: {data_count} 条  |  状态: {status_text}  {has_backup}")
        if self.data_file:
            print(f"  数据来源: {self.data_file}")
        print("=" * 70)
        print("  1. 班务日志识别 / JSON 导入")
        print("  2. 编辑单识别 / JSON 导入")
        print("  3. 纠错              ← 积分记录 + 编辑请求 统一纠错")
        print("  4. 应用并预览        ← 应用编辑 → 校验 → 匹配 → 预览")
        print("  5. 编辑              ← 手动修改字段")
        print("  6. 上传积分")
        print("  7. 查询历史          ← 浏览库中记录 + 统计")
        print("  8. 数据管理          ← 保存 / 清空 / 撤销 / 重置 / 导出编辑")
        print("  0. 退出")
        print("-" * 70)

    # ============================================================
    # 1. 班务日志导入（识别 / JSON）
    # ============================================================

    def _import_log(self):
        print("\n📂 班务日志导入")
        print("-" * 40)
        print("  1. 图片识别")
        print("  2. JSON 导入")
        choice = input("请选择 (1/2): ").strip()
        if choice == "1":
            self._load_images()
        elif choice == "2":
            self._load_json()
        else:
            print("❌ 无效选择")

    # ============================================================
    # 2. 编辑单导入（识别 / JSON）
    # ============================================================

    def _import_edits_menu(self):
        print("\n📂 编辑单导入")
        print("-" * 40)
        print("  1. 图片识别")
        print("  2. JSON 导入（免识别）")
        choice = input("请选择 (1/2): ").strip()
        if choice == "1":
            self._load_edit_images()
        elif choice == "2":
            self._load_edits_json()
        else:
            print("❌ 无效选择")

    def _load_edits_json(self):
        """从 JSON 文件导入编辑指令（免识别，测试复用）"""
        from BYu.class_manager.points import points_store as store

        print("\n📂 导入编辑指令 JSON")
        path = input("JSON 文件路径: ").strip()
        if not path or not os.path.exists(path):
            print("❌ 文件不存在")
            input("按回车继续...")
            return
        r = store.import_edits(path)
        if r.get("imported", 0) > 0:
            print(f"✅ 导入 {r['imported']} 条编辑指令")
            for edit in r.get("edits", []):
                err = edit.get("error_info")
                mark = f" ❌{err.get('type')}" if err else ""
                print(f"   {edit.get('raw')}{mark}")
            print("   请用菜单 6 校验/应用")
        else:
            print(f"❌ 导入失败: {r.get('error', '未知错误')}")
        input("按回车继续...")

    # ============================================================
    # 辅助：获取可用的识别类型列表（返回编号选择）
    # ============================================================

    def _list_vision_types(self):
        try:
            from BYu.class_manager.points.vision import list_types
            types = list_types()
            if types:
                print("\n可用的识别类型:")
                for idx, t in enumerate(types, 1):
                    print(f"  {idx}. {t}")
                return types, None
            else:
                print("  ⚠️ 未获取到可用类型，将使用默认 '班务日志'")
                return None, "未获取到类型"
        except Exception as e:
            print(f"  ⚠️ 无法获取类型列表: {e}，将使用默认 '班务日志'")
            return None, str(e)

    def _load_images(self):
        """识别班务日志图片并落库（菜单 1 专用）"""
        print("\n📷 识别班务日志图片")

        paths_input = input("图片路径（多个用空格分隔）: ").strip()
        if not paths_input:
            print("❌ 未输入路径")
            input("按回车继续...")
            return

        paths = [p.strip() for p in paths_input.split() if os.path.exists(p.strip())]
        if not paths:
            print("❌ 没有有效的图片文件")
            input("按回车继续...")
            return

        # 识别并落库（防丢失：识别完成立即写入数据中枢）
        self._backup()
        result = self.processor.recognize_and_store(paths, type="班务日志")
        if result.get("success") and result.get("created", 0) > 0:
            self.current_data = self._reload_pending()
            self._reset_ready_state()
            self._record_history("导入班务日志", f"{result['created']} 条")
            print(f"✅ 识别并落库 {result['created']} 条数据，请用菜单 3 纠错 / 菜单 4 应用预览")
        else:
            self._restore_backup()
            print(f"❌ 识别失败: {result.get('error', '未知错误')}")
        input("按回车继续...")

    def _load_edit_images(self):
        """识别编辑单图片并落库（菜单 2 专用）"""
        print("\n📷 识别编辑单图片")

        paths_input = input("图片路径（多个用空格分隔）: ").strip()
        if not paths_input:
            print("❌ 未输入路径")
            input("按回车继续...")
            return

        paths = [p.strip() for p in paths_input.split() if os.path.exists(p.strip())]
        if not paths:
            print("❌ 没有有效的图片文件")
            input("按回车继续...")
            return

        self._backup()
        result = self.processor.recognize_edits_and_store(paths, type="修改单")
        if result.get("success") and result.get("created", 0) > 0:
            self._record_history("导入编辑单", f"{result['created']} 条")
            print(f"✅ 识别并落库 {result['created']} 条编辑指令（畸形行进纠错）")
            for edit in result.get("edits", []):
                err = edit.get("error_info")
                mark = f" ❌{err.get('type')}: {err.get('invalid_values')}" if err else ""
                print(f"   {edit.get('raw')}{mark}")
            print("   请用菜单 3 纠错 / 菜单 4 应用")
        else:
            self._restore_backup()
            print(f"❌ 识别失败: {result.get('error', '未知错误')}")
        input("按回车继续...")

    def _load_json(self):
        print("\n📂 加载 JSON")
        path = input("JSON 文件路径: ").strip()
        if not path or not os.path.exists(path):
            print("❌ 文件不存在或未输入")
            input("按回车继续...")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                units = data
            elif isinstance(data, dict) and "data" in data:
                units = data["data"]
            else:
                print("❌ 格式错误，应为列表或包含 data 键的字典")
                input("按回车继续...")
                return

            if not units:
                print("⚠️ 文件为空")
                input("按回车继续...")
                return

            # ============================================================
            # 为没有合法 ID 的事件生成 "010" 格式的 ID，然后落库
            # ============================================================
            units = self._ensure_event_ids(units)

            from BYu.class_manager.points import points_store as store
            pairs = store.create_points_records(units)
            if not pairs:
                print("❌ 落库失败，没有有效数据")
                input("按回车继续...")
                return

            self._backup()
            reloaded = self.processor.load_store_units()  # 从库加载全部待处理
            self.current_data = reloaded
            self.data_file = path
            self._reset_ready_state()
            self._record_history("加载JSON", f"{len(pairs)} 条")
            print(f"✅ 加载并落库 {len(pairs)} 条数据，请执行菜单 2 生成预览")
        except Exception as e:
            self._restore_backup()
            print(f"❌ 加载失败: {e}")
        input("按回车继续...")

    # ============================================================
    # 辅助：为新增事件生成 ID（010 格式）
    # ============================================================

    def _ensure_event_ids(self, units: List[Dict]) -> List[Dict]:
        """
        为没有合法 ID 的事件单元生成 "日期+010+编号" 格式的 ID。
        
        规则：
            - 如果有 id 且格式为 YYYYMMDD+3位数字，保留
            - 如果有 id 且格式为 YYYYMMDD010+3位数字，保留（视为新增事件）
            - 如果没有 id 或 id 格式不合法，生成新 ID
            - 新 ID 格式：当前日期 + "010" + 编号（3位）
            - 编号按日期独立递增
        
        入参：
            units: List[Dict] - 数据单元列表
        
        出参：
            List[Dict] - 处理后的数据单元列表
        """
        if not units:
            return units

        # ---- 第一步：检查哪些单元需要生成 ID ----
        need_id_units = []
        for u in units:
            if u.get("Operation") != "event":
                continue
            
            uid = u.get("id", "")
            if not uid:
                need_id_units.append(u)
                continue
            
            # 检查 ID 格式（编号两位：YYYYMMDD + 2位 或 YYYYMMDD010 + 2位）
            import re
            if re.match(r'^\d{8}\d{2}$', uid):
                continue
            if re.match(r'^\d{8}010\d{2}$', uid):
                continue
            need_id_units.append(u)

        if not need_id_units:
            return units

        # ---- 第二步：获取当前日期 ----
        today_str = datetime.now().strftime("%Y%m%d")

        # ---- 第三步：统计当前数据中已有的 "010" 格式 ID ----
        existing_ids = set()
        all_data = self.current_data + units
        for u in all_data:
            uid = u.get("id", "")
            if uid and uid.startswith(today_str + "010"):
                existing_ids.add(uid)

        existing_nums = set()
        for eid in existing_ids:
            try:
                num = int(eid[-3:])
                existing_nums.add(num)
            except ValueError:
                pass

        max_num = max(existing_nums) if existing_nums else 0

        # ---- 第四步：为每个需要 ID 的单元生成新 ID ----
        for u in need_id_units:
            max_num += 1
            new_id = f"{today_str}010{max_num:02d}"
            u["id"] = new_id
            u["_source"] = "manual"
            u["_new_event"] = True
            print(f"  📝 为新增事件生成 ID: {new_id}")

        return units

    # ============================================================
    # 2. 生成并预览最终积分（核心管道）
    # ============================================================

    def _generate_and_preview(self):
        # 从库重新加载最新待处理数据（丢弃内存中可能过期的 current_data，
        # 避免覆盖编辑应用/其他会话对库的修改）
        from BYu.class_manager.points import points_store as store
        self.current_data = self._reload_pending()
        if not self.current_data:
            print("⚠️ 数据中枢中没有待处理记录，请先导入")
            input("按回车继续...")
            return

        print("\n🔄 正在处理数据...")
        print("-" * 40)

        # 库驱动：校验 -> 匹配 -> 从库加载 matched 预览
        validate_result = self.processor.validate_store()
        if validate_result["errors"] > 0:
            print(f"⚠️ 数据存在 {validate_result['errors']} 处错误，请用菜单 6 纠错后再生成预览")
            print("   （错误详情已写入库中对应记录的 error_info）")
            input("按回车继续...")
            return

        match_result = self.processor.match_store()
        if match_result["failed"] > 0:
            print(f"⚠️ {match_result['failed']} 个事件匹配失败，请用菜单 6 纠错")
            input("按回车继续...")
            return

        from BYu.class_manager.points import points_store as store
        matched = self.processor.load_store_units(status=store.STATUS_MATCHED)
        self.final_events = [{
            "id": u.get("id"),
            "item_event": (u.get("data") or {}).get("item_event", "?"),
            "person_list": (u.get("data") or {}).get("person_list", []),
            "points": float(u.get("points", 0)),
            "_match_source": u.get("_match_source", "store"),
        } for u in matched]
        self.is_ready = True
        self.current_data = (self.processor.load_store_units(status=store.STATUS_PENDING_REVIEW)
                             + self.processor.load_store_units(status=store.STATUS_PENDING_MATCH)
                             + matched)
        self._display_final_preview(self.final_events)
        print(f"\n✅ 预览已生成（{len(self.final_events)} 条已匹配），状态变为'已就绪'，可以执行上传。")
        print("   (若需修改数据，请用菜单 6 纠错，然后重新生成预览)")

        input("\n按回车继续...")

    def _display_final_preview(self, events: List[Dict]):
        if not events:
            print("⚠️ 没有有效事件")
            return

        total = len(events)
        show = min(total, 20)
        print(f"\n📊 最终事件预览 (共 {total} 条，显示前 {show} 条):")
        print("-" * 70)

        total_points = 0.0
        for i, ev in enumerate(events[:show], 1):
            name = ev.get("item_event", "?")
            persons = ",".join(ev.get("person_list", []))
            points = float(ev.get("points", 0))
            total_points += points
            source = ev.get("_match_source", "")
            source_str = f" [{source}]" if source else ""
            print(f"  {i:3d}. {name:15} {persons:20} {points:+6.1f}{source_str}")

        if total > show:
            print(f"  ... 还有 {total - show} 条")
        print("-" * 70)
        print(f"  总计: {total} 个事件，总积分变化: {total_points:+6.1f}")

    # ============================================================
    # 3. 上传积分
    # ============================================================

    def _upload(self):
        from BYu.class_manager.points import points_store as store

        matched = store.query_records(status=store.STATUS_MATCHED)
        if not matched:
            print("❌ 库中没有已匹配（matched）的记录，请先用菜单 2 生成预览")
            input("按回车继续...")
            return

        total = len(matched)
        total_points = sum(float((e.get("extra") or {}).get("score") or 0.0) for e in matched)
        print(f"\n即将上传 {total} 个事件，总积分变化: {total_points:+6.1f}")
        confirm = input("确认上传？(y/n): ").strip().lower()
        if confirm != 'y':
            print("已取消")
            input("按回车继续...")
            return

        print("\n⏳ 正在上传...")
        upload_result = self.processor.upload_store()

        if upload_result.get("success"):
            print(f"✅ 上传成功 {upload_result.get('uploaded', 0)} 条!")
            api_resp = upload_result.get("upload_result", {})
            if api_resp.get("api_response"):
                print(f"   API 响应: {json.dumps(api_resp['api_response'], ensure_ascii=False)}")
            self._record_history("上传", f"{upload_result.get('uploaded', 0)} 个事件")
            # 上传后重载：只保留未上传的待处理记录（uploaded 已清零）
            self._reset_ready_state()
            self.current_data = self._reload_pending()
        else:
            err = upload_result.get("error", "未知错误")
            print(f"❌ 上传失败: {err}")
            if "error_info" in upload_result:
                print(f"   详情: {upload_result['error_info']}")

            # 该周积分已存在：引导删除后重试（危险操作，需确认）
            if "已存在" in err:
                print("\n⚠️ 该周积分计算数据已存在，需要先删除该周积分才能重新上传（不可逆！）")
                confirm = input("是否删除该周积分后重新上传？(y/n): ").strip().lower()
                if confirm == 'y':
                    try:
                        from GYun.scmAPI import del_points
                        day = input("  删除指定日期所在周 (YYYY-MM-DD，回车=当周): ").strip() or None
                        dr = del_points(day)
                        print(f"  🗑️ 删除结果: {dr.get('message')}")
                        if dr.get("code") != 0:
                            print("  ❌ 删除失败，已取消重传")
                        else:
                            print("  ⏳ 重新上传...")
                            upload_result = self.processor.upload_store()
                            if upload_result.get("success"):
                                print(f"✅ 重新上传成功 {upload_result.get('uploaded', 0)} 条!")
                                self._record_history("上传", f"{upload_result.get('uploaded', 0)} 个事件")
                                self._reset_ready_state()
                                self.current_data = self._reload_pending()
                            else:
                                print(f"❌ 重新上传失败: {upload_result.get('error', '未知错误')}")
                    except Exception as e:
                        print(f"  ❌ 删除失败: {e}")

        input("\n按回车继续...")

    # ============================================================
    # 4. 编辑 / 纠错数据
    # ============================================================

    def _edit_or_correct(self):
        if not self.current_data:
            print("⚠️ 无数据")
            input("按回车继续...")
            return

        print("\n📝 编辑/纠错数据")
        print("-" * 40)
        print("  1. 快速纠错（逐条修复所有错误，含分数，显示上下文，AI 人员修正）")
        print("  2. 自由编辑（按序号修改任意字段，含分数）")
        mode = input("请选择模式 (1/2): ").strip()
        if mode == "1":
            self._quick_correct()
        elif mode == "2":
            self._free_edit()
        else:
            print("❌ 无效选择")

    # ---- 4.1 快速纠错 ----
    def _quick_correct(self):
        """自动扫描 mistake 并引导修复，集成 AI 人员修正（支持中文全名）"""
        validate_result = self.processor.validate(self.current_data)
        if not validate_result["has_errors"]:
            print("✅ 没有错误需要修正")
            input("按回车继续...")
            return

        # ---- 第一步：AI 人员修正（所有不在映射中的名字，包括中文全名） ----
        print("\n🔄 正在识别可疑名字...")
        all_names = set()
        for u in self.current_data:
            if u.get("Operation") == "event":
                inner = u.get("data", {})
                person_list = inner.get("person_list", [])
                if not person_list:
                    person_list = u.get("person_list", [])
                all_names.update(person_list)

        # 找出所有不在映射中的名字（无论是中文全名还是错误缩写）
        suspect_names = set()
        for n in all_names:
            if not n:
                continue
            if n in NAME_CODE_MAP or n in ABBR_TO_NAME:
                continue
            suspect_names.add(n)

        name_corrections = {}
        if suspect_names:
            try:
                from BYu.class_manager.points.matcher import _batch_ai_correct_names
                name_corrections = _batch_ai_correct_names(suspect_names, verbose=False)
                print(f"✅ AI 修正 {len(name_corrections)} 个名字")
                for orig, corr in name_corrections.items():
                    if orig != corr:
                        # 如果修正值是缩写，显示对应的中文全名
                        if corr in ABBR_TO_NAME:
                            full_name = ABBR_TO_NAME[corr]
                            print(f"   {orig} → {corr} ({full_name})")
                        else:
                            print(f"   {orig} → {corr}")
            except Exception as e:
                print(f"⚠️ AI 修正失败: {e}")

        # ---- 第二步：逐条纠错 ----
        mistakes = validate_result["mistakes"]
        print(f"\n发现 {len(mistakes)} 个错误单元，开始逐条修正:")
        self._backup()
        # 记录 id -> entity_id 映射（用于删除整条时同步库）
        id_to_eid = {u.get("id"): u.get("entity_id")
                     for u in self.current_data if u.get("entity_id")}
        fix_maps = []
        processed = set()

        for idx, mu in enumerate(mistakes, 1):
            uid = mu.get("id", "?")
            print(f"\n[{idx}/{len(mistakes)}] 修正 ID: {uid}")
            original = None
            for u in self.current_data:
                if u.get("id") == uid:
                    original = u
                    break
            if not original:
                print("  ⚠️ 找不到原始数据，跳过")
                continue

            op_type = original.get("Operation")
            inner = original.get("data", {})
            if op_type == "event":
                self._handle_event_error(
                    original, inner, mu.get("content", []),
                    fix_maps, processed, name_corrections
                )
            else:
                print(f"  ⚠️ 未知类型: {op_type}，跳过")

        # ---- 第三步：应用修正 ----
        if not fix_maps:
            print("\n⚠️ 未修正任何错误")
            self._restore_backup()
        else:
            self.current_data = self.processor.apply_fix_map(self.current_data, fix_maps)
            # 删除整条（__DELETE_UNIT__）的单元同步软删库中记录
            from BYu.class_manager.points import points_store as store
            for fm in fix_maps:
                if fm.get("mistake") == "__DELETE_UNIT__":
                    eid = id_to_eid.get(fm.get("id"))
                    if eid:
                        store.soft_delete_record(eid)
                        print(f"  🗑️ 已从数据中枢删除 ID {fm.get('id')}")
            self._sync_current_data_to_store()  # 修正写回库
            self.processor.clear_cache()
            self._reset_ready_state()
            self._record_history("快速纠错", f"{len(fix_maps)} 条修正")
            print(f"\n✅ 已应用 {len(fix_maps)} 条修正")
            recheck = self.processor.validate(self.current_data)
            if recheck["has_errors"]:
                print(f"⚠️ 仍有 {len(recheck['mistakes'])} 个错误未修复，请再次纠错或手动编辑")
            else:
                print("✅ 所有错误已修复！")
            print("💡 请执行菜单 2 重新生成预览以确认")
        input("\n按回车继续...")

    # ============================================================
    # 处理 Event 错误（支持 AI 人员修正建议，显示中文全名）
    # ============================================================

    def _handle_event_error(self, unit, inner, err_msgs, fix_maps, processed, name_corrections=None):
        """
        处理 event 的错误，显示上下文，支持 AI 修正建议。
        """
        uid = unit.get("id")
        if name_corrections is None:
            name_corrections = {}

        for err_msg in err_msgs:
            key = f"{uid}_{err_msg}"
            if key in processed:
                continue
            processed.add(key)

            # ---------- 分数错误 ----------
            if "分数" in err_msg or "未匹配" in err_msg:
                event_name = inner.get("item_event", "?")
                person_list = ",".join(inner.get("person_list", []))
                print(f"  事件: {event_name}")
                print(f"  人员: {person_list}")
                print(f"  当前分数: {unit.get('points', '未设置')}")
                print("  选项: [输入新分数] 修正 | [回车] 跳过（保留当前状态）")
                choice = input("  > ").strip()
                if choice:
                    try:
                        score = float(choice)
                        fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": "__SET_POINTS__", "Content": str(score)})
                        print(f"  ✅ 分数设为 {score}")
                    except ValueError:
                        print("  ❌ 请输入有效数字")
                else:
                    print("  ⏭️ 跳过")
                continue

            # ---------- 记录人错误 ----------
            if "记录人" in err_msg:
                recorder = inner.get("recorder", "")
                print(f"  记录人: '{recorder}'")
                new_rec = input("  输入新值 (回车跳过, del删除): ").strip()
                if new_rec == "del":
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": recorder, "Content": "__DELETE__"})
                    print("  ✅ 已删除记录人")
                elif new_rec:
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": recorder, "Content": new_rec})
                    print(f"  ✅ 修正为: {new_rec}")
                continue

            # ---------- 人员错误 ----------
            if "人员" in err_msg:
                # 人员列表为空：整表补人（或删除整条）
                if "人员列表为空" in err_msg:
                    event_name = inner.get("item_event", "?")
                    print(f"  事件: {event_name} | 人员列表为空")
                    print("  选项: [输入人员(空格分隔)] 补人 | [del] 删除整条 | [回车] 跳过")
                    choice = input("  > ").strip()
                    if choice == "del":
                        fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": "__DELETE_UNIT__", "Content": "DELETED"})
                        print("  ✅ 已标记删除整条")
                    elif choice:
                        fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": "__SET_PERSON_LIST__", "Content": choice})
                        print(f"  ✅ 人员设为: {choice}")
                    else:
                        print("  ⏭️ 跳过")
                    continue

                import re
                name = None
                match = re.search(r"未知人员[:：]\s*(\S+)", err_msg)
                if match:
                    name = match.group(1)
                else:
                    match = re.search(r"['\"]([^'\"]+)['\"]", err_msg)
                    if match:
                        name = match.group(1)
                if not name:
                    if ":" in err_msg:
                        name = err_msg.split(":", 1)[1].strip()
                    elif "：" in err_msg:
                        name = err_msg.split("：", 1)[1].strip()
                    else:
                        name = "未知"

                event_name = inner.get("item_event", "?")
                print(f"  事件: {event_name}")
                
                display_name = name
                if name in ABBR_TO_NAME:
                    display_name = f"{name} ({ABBR_TO_NAME[name]})"
                elif name in NAME_CODE_MAP:
                    display_name = f"{name} ({NAME_CODE_MAP[name]})"
                print(f"  人员: {display_name}")

                ai_suggestion = name_corrections.get(name)
                if ai_suggestion and ai_suggestion != name:
                    if ai_suggestion in ABBR_TO_NAME:
                        full_name = ABBR_TO_NAME[ai_suggestion]
                        print(f"  💡 AI 建议修正为: {full_name} ({ai_suggestion})")
                    else:
                        print(f"  💡 AI 建议修正为: {ai_suggestion}")

                prompt = "  输入新值 (回车跳过, del删除"
                if ai_suggestion and ai_suggestion != name:
                    prompt += ", 回车使用AI建议"
                prompt += "): "
                new_name = input(prompt).strip()

                if new_name == "" and ai_suggestion and ai_suggestion != name:
                    new_name = ai_suggestion
                    print(f"  ✅ 使用 AI 建议: {new_name}")

                if new_name == "del":
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": name, "Content": "__DELETE__"})
                    print(f"  ✅ 已删除 '{name}'")
                elif new_name and new_name != name:
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": name, "Content": new_name})
                    print(f"  ✅ 修正为: {new_name}")
                else:
                    print("  ⏭️ 跳过")
                continue

            # ---------- 事件名错误 ----------
            if "事件名" in err_msg:
                event_name = inner.get("item_event", "")
                print(f"  当前事件名: '{event_name}'")
                choice = input("  输入新值 (回车跳过, del删除): ").strip()
                if choice == "del":
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": event_name, "Content": "__DELETE__"})
                    print("  ✅ 已删除事件名")
                elif choice:
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": event_name, "Content": choice})
                    print(f"  ✅ 修正为: {choice}")
                continue

            # ---------- 【新增】日期错误 ----------
            if "日期" in err_msg:
                current_date = inner.get("date", "")
                print(f"  当前日期: '{current_date}'")
                print("  选项: [输入新日期 YYYY-MM-DD] 修正 | [del] 删除 | [回车] 跳过")
                choice = input("  > ").strip()
                if choice == "del":
                    inner["date"] = ""
                    fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": current_date, "Content": "__DELETE__"})
                    print("  ✅ 已删除日期")
                elif choice:
                    import re
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', choice):
                        inner["date"] = choice
                        fix_maps.append({"Operation": "fix_map", "id": uid, "mistake": current_date, "Content": choice})
                        print(f"  ✅ 日期修正为: {choice}")
                    else:
                        print("  ❌ 日期格式错误，请使用 YYYY-MM-DD 格式")
                else:
                    print("  ⏭️ 跳过")
                continue

            print(f"  ⚠️ 未处理的错误: {err_msg}")


    # ---- 4.2 自由编辑 ----
    def _free_edit(self):
        self._list_all_units()
        choice = input("\n请输入序号或ID (回车取消): ").strip()
        if not choice:
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(self.current_data):
                unit = self.current_data[idx]
            else:
                print("❌ 序号超出范围")
                input("按回车继续...")
                return
        except ValueError:
            unit = None
            for u in self.current_data:
                if u.get("id") == choice:
                    unit = u
                    break
            if not unit:
                print(f"❌ 未找到ID: {choice}")
                input("按回车继续...")
                return

        self._backup()
        self._edit_unit_interactive(unit)
        self._sync_current_data_to_store()
        self._reset_ready_state()
        self.processor.clear_cache()
        print("\n✅ 修改完成并已写入数据中枢，请重新生成预览")
        input("按回车继续...")

    def _list_all_units(self):
        print("\n当前数据列表:")
        print("-" * 70)
        for i, u in enumerate(self.current_data, 1):
            op = u.get("Operation", "?")
            uid = u.get("id", "N/A")
            inner = u.get("data", {})
            event = inner.get("item_event", "?")
            if op == "event":
                persons = ",".join(inner.get("person_list", []))
                points = u.get("points") or inner.get("points")
                points_str = f" {points:+g}" if points is not None else ""
                print(f"  {i:3d}. [事件] {uid} {event:12} 人员:{persons} {points_str}")
            elif op == "mistake":
                content = " | ".join(u.get("content", []))
                print(f"  {i:3d}. [❌错误] {uid} {content[:40]}")
            elif op == "fix_map":
                print(f"  {i:3d}. [修正] {uid} {u.get('mistake')} → {u.get('Content')}")
            else:
                print(f"  {i:3d}. [{op}] {uid}")

    def _edit_unit_interactive(self, unit):
        op_type = unit.get("Operation")
        uid = unit.get("id")
        inner = unit.get("data", {})
        print(f"\n编辑 ID: {uid} (类型: {op_type})")
        print("可用字段: 直接回车跳过，输入 'del' 删除该字段")

        fields = ["item_event", "person_list", "points", "recorder", "remark", "date"]
        for field in fields:
            if field == "person_list":
                current = ",".join(inner.get("person_list", []))
            elif field == "points":
                current = unit.get("points") or inner.get("points")
                if current is None:
                    current = ""
                else:
                    current = str(current)
            else:
                current = inner.get(field, "")

            prompt = f"  {field} [{current}]: "
            new_val = input(prompt).strip()
            if new_val == "":
                continue
            if new_val == "del":
                if field == "person_list":
                    inner["person_list"] = []
                elif field == "points":
                    if "points" in unit:
                        del unit["points"]
                    if "points" in inner:
                        del inner["points"]
                    unit["_matched"] = False
                    if "_match_source" in unit:
                        del unit["_match_source"]
                else:
                    inner[field] = ""
                print(f"  ✅ 已删除 {field}")
                continue

            if field == "person_list":
                parts = re.split(r'[ ,，]+', new_val)
                inner["person_list"] = [p.strip() for p in parts if p.strip()]
            elif field == "points":
                try:
                    score = float(new_val)
                    unit["points"] = score
                    inner["points"] = score
                    unit["_matched"] = True
                    unit["_match_source"] = "manual"
                except ValueError:
                    print("  ❌ 请输入有效数字")
            elif field == "item_event":
                # 事件名校验
                if not is_valid_event_name(new_val):
                    print("  ❌ 事件名包含非法字符 (如 []{}()<>/\\|) 或为空，请重新输入")
                    continue
                inner[field] = new_val
                unit["_matched"] = False
                if "_match_source" in unit:
                    del unit["_match_source"]
                if "points" in unit:
                    del unit["points"]
                if "points" in inner:
                    del inner["points"]
            else:
                inner[field] = new_val
            print(f"  ✅ 已更新 {field}")

    # ============================================================
    # 5. 数据管理
    # ============================================================

    def _data_management(self):
        print("\n📁 数据管理")
        print("-" * 40)
        print("  1. 保存数据")
        print("  2. 清空数据")
        print("  3. 撤销上次操作")
        print("  4. 清空全部积分数据（保留 person，测试用）")
        print("  5. 导出编辑指令 JSON")
        choice = input("请选择 (1/2/3/4/5): ").strip()
        if choice == "1":
            self._save_data()
        elif choice == "2":
            self._clear_data()
        elif choice == "3":
            self._undo()
        elif choice == "4":
            self._reset_all_data()
        elif choice == "5":
            self._export_edits()
        else:
            print("❌ 无效选择")

    def _export_edits(self):
        """导出库中编辑指令为 JSON（测试复用，避免重复识别）"""
        from BYu.class_manager.points import points_store as store

        print("\n📤 导出编辑指令 JSON")
        default = f"edits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = input(f"导出路径 (默认: {default}): ").strip() or default
        if not path.endswith('.json'):
            path += '.json'
        n = store.export_edits(path)
        if n:
            print(f"✅ 已导出 {n} 条编辑指令到 {path}")
        else:
            print("⚠️ 库中没有可导出的编辑指令")
        input("按回车继续...")

    def _reset_all_data(self):
        """测试用：清空所有积分数据（points_record + points_edit），保留 person"""
        from BYu.class_manager.points import points_store as store

        print("\n⚠️  此操作将硬删除全部积分记录与编辑请求（不可恢复），person 数据保留")
        confirm = input("确认清空所有积分数据？(y/n): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return
        r = store.reset_all_data()
        print(f"✅ 已清空积分数据 {r['deleted']} 条，保留 person {r['person_count']} 个")
        self._reset_ready_state()

    # ============================================================
    # 6. 待处理工作台（库驱动：纠错 + 应用）
    # ============================================================

    def _pending_workbench(self):
        """库驱动：查看待处理概览 / 纠错积分记录 / 纠错编辑请求 / 应用编辑"""
        from BYu.class_manager.points import points_store as store

        print("\n📋 待处理工作台")
        print("-" * 40)
        print("  1. 查看待处理概览")
        print("  2. 纠错积分记录")
        print("  3. 纠错编辑请求")
        print("  4. 应用编辑请求")
        choice = input("请选择 (1/2/3/4，回车返回): ").strip()
        if choice == "1":
            self._pending_overview()
        elif choice == "2":
            self._review_records()
        elif choice == "3":
            self._review_edits()
        elif choice == "4":
            self._apply_edits()
        else:
            return
        input("按回车继续...")

    def _pending_overview(self):
        """待处理概览：积分记录 + 编辑请求各状态数量"""
        from BYu.class_manager.points import points_store as store

        stats = self.processor.store_summary()
        print(f"\n📊 积分记录: 待纠错 {stats.get('pending_review', 0)} | "
              f"待匹配 {stats.get('pending_match', 0)} | "
              f"已匹配 {stats.get('matched', 0)} | 已上传 {stats.get('uploaded', 0)}")
        for st, label in ((store.STATUS_PENDING_REVIEW, "待纠错"),
                          (store.STATUS_APPROVED, "待应用"),
                          (store.STATUS_APPLIED, "已应用"),
                          (store.STATUS_CANCELLED, "已取消")):
            cnt = len(store.query_edits(status=st))
            print(f"📝 编辑请求 [{label}]: {cnt}")

    # ============================================================
    # 3. 统一纠错（积分记录 + 编辑请求）
    # ============================================================

    def _correct_all(self):
        """统一纠错：积分记录 + 编辑请求（都带预校验推进）"""
        from BYu.class_manager.points import points_store as store

        while True:
            recs = store.query_records(status=store.STATUS_PENDING_REVIEW)
            edits = store.query_edits(status=store.STATUS_PENDING_REVIEW)
            if not recs and not edits:
                print("✅ 没有待纠错的数据")
                return
            print(f"\n🔧 待纠错: 积分记录 {len(recs)} 条, 编辑请求 {len(edits)} 条")
            print("  1. 纠错积分记录")
            print("  2. 纠错编辑请求")
            print("  回车返回")
            choice = input("请选择 (1/2，回车返回): ").strip()
            if choice == "1":
                self._review_records()
            elif choice == "2":
                self._review_edits()
            else:
                return

    # ============================================================
    # 4. 应用并预览（应用编辑 → 校验 → 匹配 → 预览）
    # ============================================================

    def _apply_and_preview(self):
        """应用编辑请求 -> 校验 -> 匹配 -> 预览"""
        from BYu.class_manager.points import points_store as store

        # 1) 应用 approved 编辑
        ra = self.processor.apply_edits_store()
        if ra["applied"] or ra["failed"]:
            print(f"📝 编辑应用: 成功 {ra['applied']} 条, 失败 {ra['failed']} 条")
            if ra["failed"]:
                print("   失败详情在对应编辑的 error_info，请用菜单 3 纠错")
        else:
            print("ℹ️ 没有待应用的编辑请求")

        # 2) 校验 -> 匹配
        v = self.processor.validate_store()
        if v["errors"] > 0:
            print(f"⚠️ 校验发现 {v['errors']} 处错误，请用菜单 3 纠错")
            input("按回车继续...")
            return
        m = self.processor.match_store()
        if m["failed"] > 0:
            print(f"⚠️ {m['failed']} 个事件匹配失败，请用菜单 3 纠错")
            input("按回车继续...")
            return

        # 3) 加载 matched 预览
        self.current_data = self._reload_pending()
        matched = self.processor.load_store_units(status=store.STATUS_MATCHED)
        self.final_events = [{
            "id": u.get("id"),
            "item_event": (u.get("data") or {}).get("item_event", "?"),
            "person_list": (u.get("data") or {}).get("person_list", []),
            "points": float(u.get("points", 0)),
            "_match_source": u.get("_match_source", "store"),
        } for u in matched]
        self.is_ready = True
        self._display_final_preview(self.final_events)
        print(f"\n✅ 已匹配 {len(self.final_events)} 条，状态已就绪，可用菜单 6 上传")
        input("按回车继续...")

    def _review_records(self):
        """纠错积分记录：逐条展示 error_info -> 修正 -> 重新校验推进"""
        from BYu.class_manager.points import points_store as store

        # 先校验推进：无错误的直接 pending_match，只留真正有错的待纠错
        v = self.processor.validate_store()
        if v["errors"] > 0:
            print(f"ℹ️ 预校验: {v['ok']} 条通过，{v['errors']} 条需纠错")
        else:
            if v["checked"] > 0:
                print(f"✅ 全部 {v['checked']} 条积分记录校验通过")

        while True:
            records = store.query_records(status=store.STATUS_PENDING_REVIEW)
            if not records:
                print("✅ 没有待纠错的积分记录")
                return

            print(f"\n🔧 待纠错积分记录 {len(records)} 条")
            for idx, rec in enumerate(records, 1):
                extra = rec.get("extra") or {}
                err = extra.get("error_info") or {}
                unit = store.record_to_unit(rec)
                print(f"\n[{idx}/{len(records)}] ID: {extra.get('id')} | "
                      f"事件: {rec.get('title')} | 人员: {unit['data']['person_list']}")
                if err:
                    print(f"   ❌ {err.get('type')}: {err.get('invalid_values')} | raw: {err.get('raw')}")

                # 按错误类型给出修正提示
                prompt = "  [修正] "
                err_type = err.get("type", "")
                if err_type == store.ERROR_PERSON_NOT_FOUND:
                    prompt += "输入正确人员(逗号分隔)"
                elif err_type in (store.ERROR_EVENT_INVALID,):
                    prompt += "输入正确事件名"
                elif err_type == store.ERROR_DATE_INVALID:
                    prompt += "输入正确日期(YYYY-MM-DD)"
                elif err_type == store.ERROR_RECORDER_NOT_FOUND:
                    prompt += "输入正确记录人"
                elif err_type in (store.ERROR_SCORE_INVALID, "match_failed"):
                    prompt += "输入正确分数"
                else:
                    prompt += "输入新值(逗号分隔为人员/分数)"
                prompt += " [s]跳过 [c]取消 [d]删除: "

                choice = input(prompt).strip()
                if choice.lower() in ("s", "skip", ""):
                    continue
                if choice.lower() in ("c", "cancel"):
                    store.cancel_record(rec["entity_id"])
                    print("  ✅ 已取消该条")
                    continue
                if choice.lower() in ("d", "del", "delete"):
                    store.soft_delete_record(rec["entity_id"])
                    print("  ✅ 已删除该条")
                    continue

                # 按错误类型落库修正
                ok = False
                if err_type == store.ERROR_PERSON_NOT_FOUND:
                    persons = [p.strip() for p in re.split(r'[,，、]', choice) if p.strip()]
                    ok = store.correct_record(rec["entity_id"], persons=persons)
                elif err_type == store.ERROR_EVENT_INVALID:
                    ok = store.correct_record(rec["entity_id"], title=choice)
                elif err_type == store.ERROR_DATE_INVALID:
                    ok = store.correct_record(rec["entity_id"], date=choice)
                elif err_type == store.ERROR_RECORDER_NOT_FOUND:
                    ok = store.correct_record(rec["entity_id"], recorder=choice)
                elif err_type in (store.ERROR_SCORE_INVALID, "match_failed"):
                    try:
                        ok = store.correct_record(rec["entity_id"], score=float(choice))
                    except ValueError:
                        print("  ❌ 分数格式错误")
                        continue
                else:
                    # 通用：尝试按逗号分隔为人员，否则视为事件名
                    parts = [p.strip() for p in re.split(r'[,，、]', choice) if p.strip()]
                    ok = store.correct_record(rec["entity_id"],
                                              persons=parts if len(parts) > 1 else None,
                                              title=choice if len(parts) == 1 else None)
                print("  ✅ 已修正，待重新校验" if ok else "  ❌ 修正失败")

            # 重新校验推进（修正对的 -> pending_match）
            v = self.processor.validate_store()
            print(f"\n🔄 重新校验: 通过 {v['ok']} 条, 仍错误 {v['errors']} 条")
            if v["errors"] == 0:
                return
            again = input("还有错误，继续纠错？(y/n，默认 y): ").strip().lower()
            if again == "n":
                return

    def _review_edits(self):
        """纠错编辑请求：展示 error_info -> 输入修正后整行 -> 重新校验推进"""
        from BYu.class_manager.points import points_store as store

        # 先校验推进：无错误的直接 approved，只留真正有错的待纠错
        v = self.processor.validate_edits_store()
        if v["errors"] > 0:
            print(f"ℹ️ 预校验: {v['ok']} 条通过，{v['errors']} 条需纠错")
        else:
            if v["checked"] > 0:
                print(f"✅ 全部 {v['checked']} 条编辑请求校验通过（approved）")

        while True:
            edits = store.query_edits(status=store.STATUS_PENDING_REVIEW)
            if not edits:
                print("✅ 没有待纠错的编辑请求")
                return

            print(f"\n🔧 待纠错编辑请求 {len(edits)} 条")
            for idx, ent in enumerate(edits, 1):
                extra = ent.get("extra") or {}
                err = extra.get("error_info") or {}
                print(f"\n[{idx}/{len(edits)}] ID: {extra.get('id')} | {ent.get('title')}")
                if err:
                    print(f"   ❌ {err.get('type')}: {err.get('invalid_values')} | raw: {err.get('raw')}")

                choice = input("  [输入] 修正后的完整编辑行 [s]跳过 [c]取消 [d]删除: ").strip()
                if choice.lower() in ("s", "skip", ""):
                    continue
                if choice.lower() in ("c", "cancel"):
                    store.cancel_edit(ent["entity_id"])
                    print("  ✅ 已取消该条")
                    continue
                if choice.lower() in ("d", "del", "delete"):
                    store.soft_delete_record(ent["entity_id"])
                    print("  ✅ 已删除该条")
                    continue
                ok = store.correct_edit(ent["entity_id"], new_line=choice)
                print("  ✅ 已修正，待重新校验" if ok else "  ❌ 修正失败")

            # 重新校验推进（修正对的 -> approved）
            v = self.processor.validate_edits_store()
            print(f"\n🔄 重新校验: 通过 {v['ok']} 条, 仍错误 {v['errors']} 条")
            if v["errors"] == 0:
                return
            again = input("还有错误，继续纠错？(y/n，默认 y): ").strip().lower()
            if again == "n":
                return

    def _apply_edits(self):
        """应用 approved 的编辑请求到目标积分记录"""
        from BYu.class_manager.points import points_store as store

        approved = store.query_edits(status=store.STATUS_APPROVED)
        if not approved:
            print("✅ 没有待应用的编辑请求")
            return
        print(f"共 {len(approved)} 条待应用编辑请求:")
        for ent in approved:
            extra = ent.get("extra") or {}
            print(f"   {extra.get('id')} | {ent.get('title')} | "
                  f"目标: {extra.get('target_seq') or '-'}")
        confirm = input("确认全部应用？(y/n): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return
        r = self.processor.apply_edits_store()
        print(f"✅ 应用成功 {r['applied']} 条，失败 {r['failed']} 条")
        if r["failed"]:
            print("  失败详情已写入对应编辑请求的 error_info，可在纠错中查看")

    # ============================================================
    # 7. 历史数据查询（浏览库中记录 + 统计）
    # ============================================================

    def _history_browser(self):
        """浏览库中积分记录 / 编辑请求 / 上传后统计"""
        from BYu.class_manager.points import points_store as store

        print("\n📊 历史数据查询")
        print("-" * 40)
        print("  1. 浏览积分记录")
        print("  2. 浏览编辑请求")
        print("  3. 积分统计（uploaded）")
        choice = input("请选择 (1/2/3，回车返回): ").strip()
        if choice == "1":
            self._browse_records()
        elif choice == "2":
            self._browse_edits()
        elif choice == "3":
            self._show_statistics()
        else:
            return
        input("按回车继续...")

    def _browse_records(self):
        """按状态/日期浏览库中积分记录"""
        from BYu.class_manager.points import points_store as store

        print("\n📋 浏览积分记录（状态过滤，回车=全部）:")
        status_input = input("  状态 (pending_review/pending_match/matched/uploaded/cancelled，回车全部): ").strip()
        status = status_input if status_input else None
        date = input("  日期 (YYYY-MM-DD，回车全部): ").strip() or None
        records = store.query_records(status=status, date=date, page_size=200)
        if not records:
            print("  📭 没有符合条件的记录")
            return
        print(f"  共 {len(records)} 条:")
        for i, r in enumerate(records, 1):
            extra = r.get("extra") or {}
            err = extra.get("error_info")
            err_str = f" ❌{err.get('type')}" if err else ""
            print(f"  {i:3d}. [{extra.get('entity_status', '?')}] {extra.get('id')} "
                  f"{r.get('title')} 人员:{r.get('content')} 分:{extra.get('score')}{err_str}")

    def _browse_edits(self):
        """按状态浏览库中编辑请求"""
        from BYu.class_manager.points import points_store as store

        print("\n📋 浏览编辑请求（状态过滤，回车=全部）:")
        status_input = input("  状态 (pending_review/approved/applied/cancelled，回车全部): ").strip()
        status = status_input if status_input else None
        edits = store.query_edits(status=status, page_size=200)
        if not edits:
            print("  📭 没有符合条件的编辑请求")
            return
        print(f"  共 {len(edits)} 条:")
        for i, e in enumerate(edits, 1):
            extra = e.get("extra") or {}
            err = extra.get("error_info")
            err_str = f" ❌{err.get('type')}" if err else ""
            print(f"  {i:3d}. [{extra.get('entity_status', '?')}] {extra.get('id')} "
                  f"{e.get('title')} 目标:{extra.get('target_seq') or '-'}{err_str}")

    def _show_statistics(self):
        """uploaded 记录积分统计（按学生/事件/日期）"""
        from BYu.class_manager.points import points_store as store

        print("\n📈 积分统计（仅 uploaded 记录）:")
        date_start = input("  开始日期 (YYYY-MM-DD，回车不限): ").strip() or None
        date_end = input("  结束日期 (YYYY-MM-DD，回车不限): ").strip() or None
        s = store.statistics(date_start=date_start, date_end=date_end)
        print(f"  记录数: {s['record_count']} | 总积分: {s['total_points']}")
        if s["by_student"]:
            print("  ── 按学生 ──")
            for name, pts in sorted(s["by_student"].items(), key=lambda x: -x[1]):
                print(f"    {name:10} {pts:+7.2f}")
        if s["by_event"]:
            print("  ── 按事件 ──")
            for ev, pts in sorted(s["by_event"].items(), key=lambda x: -x[1]):
                print(f"    {ev:14} {pts:+7.2f}")

    def _save_data(self):
        if not self.current_data:
            print("⚠️ 无数据")
            input("按回车继续...")
            return
        default_name = f"points_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path = input(f"保存路径 (默认: {default_name}): ").strip()
        if not path:
            path = default_name
        elif os.path.isdir(path):
            filename = f"points_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            path = os.path.join(path, filename)
        elif not path.endswith('.json'):
            path += '.json'

        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.current_data, f, ensure_ascii=False, indent=2)
            self.data_file = path
            print(f"✅ 已保存到 {path}")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
        input("按回车继续...")

    def _clear_data(self):
        if not self.current_data:
            print("⚠️ 无数据")
            input("按回车继续...")
            return
        confirm = input("⚠️ 确认清空所有数据？(y/n): ").strip().lower()
        if confirm == 'y':
            self._backup()
            self.current_data = []
            self.final_events = []
            self._reset_ready_state()
            self.processor.clear_cache()
            self._record_history("清空", "所有数据")
            print("✅ 已清空")
        else:
            print("已取消")
        input("按回车继续...")

    def _undo(self):
        if not self.backup_data:
            print("⚠️ 没有可撤销的操作")
            input("按回车继续...")
            return
        confirm = input(f"确认撤销？将恢复 {len(self.backup_data)} 条数据 (y/n): ").strip().lower()
        if confirm == 'y':
            self.current_data = self.backup_data
            self.backup_data = []
            self._reset_ready_state()
            self.processor.clear_cache()
            print("✅ 已撤销")
        else:
            print("已取消")
        input("按回车继续...")

    # ============================================================
    # 辅助方法
    # ============================================================

    def _backup(self):
        self.backup_data = copy.deepcopy(self.current_data)

    def _restore_backup(self):
        if self.backup_data is not None:
            self.current_data = self.backup_data
            self.backup_data = []

    def _sync_current_data_to_store(self):
        """
        将 current_data 中带 entity_id 的单体同步写回库。
        用于菜单 4 内存编辑后，把修改持久化（置 pending_review 待重新校验）。
        """
        from BYu.class_manager.points import points_store as store

        synced = 0
        for u in self.current_data:
            eid = u.get("entity_id")
            if not eid:
                continue
            inner = u.get("data", {})
            title = u.get("item_event") or inner.get("item_event")
            persons = u.get("person_list") or inner.get("person_list")
            points = u.get("points")
            if store.correct_record(eid, title=title, persons=persons,
                                    score=points, recorder=inner.get("recorder"),
                                    date=inner.get("date"), remark=inner.get("remark")):
                synced += 1
        if synced:
            print(f"  💾 已同步 {synced} 条修改到数据中枢")

    def _reset_ready_state(self):
        self.is_ready = False
        self.final_events = []
        self.processor.clear_cache()

    def _record_history(self, action: str, detail: str):
        self.history.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "action": action,
            "detail": detail,
            "count": len(self.current_data)
        })

    def _exit(self):
        print("\n👋 再见！")


# ============================================================
# 实际使用入口：直接启动交互式 CLI
# ============================================================
if __name__ == "__main__":
    try:
        cli = InteractivePointsCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n\n已中断")
        sys.exit(0)
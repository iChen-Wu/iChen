#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cli.py - 数据中心 CLI

用法:
    python -m BYu.class_manager.datacenter.cli

功能:
    浏览、查看、新增、修改、删除、搜索、批量操作
"""

import json
import os
import sys
from typing import Optional, List, Dict, Any

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from BYu.class_manager.datacenter.service import DataCenterService
from BYu.class_manager.datacenter.models import DEFAULT_PAGE_SIZE, DEFAULT_ORDER_BY


# ============================================================
# 工具函数
# ============================================================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str):
    print("\n" + "═" * 60)
    print(f"  {title}")
    print("═" * 60)


def print_separator():
    print("─" * 60)


def print_success(msg: str):
    print(f"✅ {msg}")


def print_error(msg: str):
    print(f"❌ {msg}")


def print_warning(msg: str):
    print(f"⚠️  {msg}")


def print_info(msg: str):
    print(f"ℹ️  {msg}")


def print_json(data: dict, indent: int = 2):
    print(json.dumps(data, ensure_ascii=False, indent=indent))


def input_with_default(prompt: str, default: str = "") -> str:
    if default:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    result = input(prompt).strip()
    return result if result else default


def input_yes_no(prompt: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    result = input(f"{prompt} ({default_str}): ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes", "是")


def input_tags(prompt: str = "请输入标签（逗号分隔）") -> List[str]:
    """输入标签列表"""
    raw = input(f"{prompt}: ").strip()
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def input_extra() -> Dict[str, Any]:
    """输入 extra JSON"""
    print("请输入 extra（JSON 格式，空行结束）:")
    lines = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
    raw = "".join(lines)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print_error(f"JSON 格式错误: {e}")
        return {}


# ============================================================
# 主菜单
# ============================================================

def show_main_menu():
    """显示主菜单"""
    clear_screen()

    # 获取统计
    stats = DataCenterService.get_type_stats()

    print_header("📁 数据中心")
    print("\n  当前数据统计:")
    for t, count in stats.items():
        if t != "total":
            print(f"    {t}: {count} 条")
    print(f"    ──────────────────────────")
    print(f"    总计: {stats.get('total', 0)} 条")

    print("  1. 浏览列表")
    print("  2. 查看详情")
    print("  3. 新增记录")
    print("  4. 修改记录")
    print("  5. 删除记录")
    print("  6. 搜索/筛选")
    print("  7. 批量操作")
    print("  8. 管理类型")
    print("  0. 退出")

    print("\n" + "─" * 60)


def main():
    """主入口"""
    while True:
        show_main_menu()
        choice = input("请选择 [1-8]: ").strip()

        if choice == "1":
            cmd_list()
        elif choice == "2":
            cmd_view()
        elif choice == "3":
            cmd_create()
        elif choice == "4":
            cmd_edit()
        elif choice == "5":
            cmd_delete()
        elif choice == "6":
            cmd_search()
        elif choice == "7":
            cmd_batch()

        elif choice == "8":
            cmd_manage_types()

        elif choice == "0":
            print("\n退出程序")
            break
        else:
            print_error("无效选项")


# ============================================================
# 命令实现
# ============================================================

def cmd_list():
    """浏览列表"""
    page = 1
    page_size = DEFAULT_PAGE_SIZE
    type_filter = None

    while True:
        clear_screen()
        print_header("📋 浏览列表")

        if page == 1:
            type_input = input_with_default("按类型筛选（空=全部）", "")
            if type_input:
                type_filter = type_input

        result = DataCenterService.list_entities(
            page=page,
            page_size=page_size,
            order_by=DEFAULT_ORDER_BY,
            type_filter=type_filter,
        )

        total = result["total"]
        items = result["items"]
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        print(f"\n📊 共 {total} 条，第 {page}/{total_pages} 页")
        print_separator()
        print(f"{'序号':<4} {'ID':<16} {'类型':<12} {'标题':<20} {'标签'}")
        print_separator()

        for idx, item in enumerate(items, 1):
            tags_str = ",".join(item.get("tags", []))
            print(f"{idx:<4} {item.get('entity_id', ''):<16} {item.get('type', ''):<12} {item.get('title', '')[:20]:<20} {tags_str}")

        print_separator()

        if total == 0:
            print_info("没有记录")
            input("\n按 Enter 返回...")
            break

        print("\n命令: n=下一页 p=上一页 数字=跳转页码 v=查看详情 q=返回")
        action = input("请输入: ").strip().lower()

        if action == "q":
            break
        elif action == "n":
            if page < total_pages:
                page += 1
            else:
                print_warning("已是最后一页")
        elif action == "p":
            if page > 1:
                page -= 1
            else:
                print_warning("已是第一页")
        elif action.isdigit():
            p = int(action)
            if 1 <= p <= total_pages:
                page = p
            else:
                print_warning(f"页码范围 1-{total_pages}")
        elif action == "v":
            idx_input = input("请输入要查看的序号: ").strip()
            if idx_input.isdigit():
                idx = int(idx_input) - 1
                if 0 <= idx < len(items):
                    entity_id = items[idx].get("entity_id")
                    print(f"DEBUG: 从 items 获取的 entity_id = {entity_id}")
                    if entity_id:
                        cmd_view(entity_id=entity_id)
                    else:
                        print_error("该条记录没有 entity_id")
                else:
                    print_error("序号无效")
            else:
                print_error("请输入数字")
        else:
            print_warning(f"未知命令: {action}")


def cmd_view(entity_id: Optional[str] = None):
    input(">>> DEBUG: cmd_view 被调用了，按 Enter 继续...")
    clear_screen()
    print_header("🔍 查看详情")

    print(f"DEBUG: cmd_view 收到的 entity_id = {entity_id}")

    if not entity_id:
        entity_id = input("请输入 entity_id: ").strip()
        if not entity_id:
            print_warning("未输入 entity_id")
            input("\n按 Enter 返回...")
            return

    entity = DataCenterService.get_entity(entity_id)
    if entity is None:
        print_error(f"记录不存在: {entity_id}")
        input("\n按 Enter 返回...")
        return

    print(f"\n📄 记录详情")
    print_separator()
    print(f"entity_id:   {entity.get('entity_id')}")
    print(f"type:        {entity.get('type')}")
    print(f"title:       {entity.get('title')}")
    print(f"content:     {entity.get('content', '')}")
    print(f"tags:        {', '.join(entity.get('tags', []))}")
    print(f"created_at:  {entity.get('created_at')}")
    print(f"updated_at:  {entity.get('updated_at')}")
    print_separator()
    print("\n📦 extra:")
    print_json(entity.get("extra", {}))

    print_separator()
    print("\n命令: e=编辑 d=删除 q=返回")
    action = input("请输入: ").strip().lower()

    if action == "e":
        cmd_edit(entity_id=entity_id)
    elif action == "d":
        cmd_delete(entity_id=entity_id)

def cmd_create():
    """新增记录"""
    clear_screen()
    print_header("➕ 新增记录")

    type_ = input("请输入 type: ").strip()
    if not type_:
        print_error("type 不能为空")
        input("\n按 Enter 返回...")
        return

    title = input("请输入 title: ").strip()
    if not title:
        print_error("title 不能为空")
        input("\n按 Enter 返回...")
        return

    content = input("请输入 content（可选）: ").strip()
    tags = input_tags()
    extra = input_extra()

    print("\n📝 确认创建:")
    print(f"  type:    {type_}")
    print(f"  title:   {title}")
    print(f"  content: {content}")
    print(f"  tags:    {tags}")
    print(f"  extra:   {extra}")

    if not input_yes_no("\n确认创建？", default=True):
        print_info("已取消")
        input("\n按 Enter 返回...")
        return

    entity_id = DataCenterService.create_entity(type_, title, content, tags, extra)
    if entity_id:
        print_success(f"已创建: {entity_id}")
    else:
        print_error("创建失败")

    input("\n按 Enter 返回...")


def cmd_edit(entity_id: Optional[str] = None):
    """修改记录"""
    clear_screen()
    print_header("✏️  修改记录")

    if not entity_id:
        entity_id = input("请输入 entity_id: ").strip()
        if not entity_id:
            return

    entity = DataCenterService.get_entity(entity_id)
    if entity is None:
        print_error(f"记录不存在: {entity_id}")
        input("\n按 Enter 返回...")
        return

    print(f"\n当前记录: {entity_id}")
    print(f"  title:   {entity.get('title')}")
    print(f"  content: {entity.get('content', '')}")
    print(f"  tags:    {', '.join(entity.get('tags', []))}")
    print(f"  extra:   {entity.get('extra', {})}")
    print_separator()

    # 选择修改字段
    print("\n要修改的字段（选择后输入新值，留空表示不修改）:")
    title = input_with_default("title", entity.get("title", ""))
    content = input_with_default("content", entity.get("content", ""))
    tags_raw = input_with_default("tags（逗号分隔）", ", ".join(entity.get("tags", [])))
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else None

    print("\n是否修改 extra？（输入完整 JSON，留空表示不修改）")
    extra_raw = input("extra: ").strip()
    extra = None
    if extra_raw:
        try:
            extra = json.loads(extra_raw)
        except json.JSONDecodeError as e:
            print_error(f"JSON 格式错误: {e}")
            input("\n按 Enter 返回...")
            return

    # 检查是否有修改
    if (title == entity.get("title") and
        content == entity.get("content") and
        (tags is None or tags == entity.get("tags", [])) and
        extra is None):
        print_info("没有修改任何字段")
        input("\n按 Enter 返回...")
        return

    # 构建更新数据
    updates = {}
    if title != entity.get("title"):
        updates["title"] = title
    if content != entity.get("content"):
        updates["content"] = content
    if tags is not None:
        updates["tags"] = tags
    if extra is not None:
        updates["extra"] = extra

    print("\n📝 将执行以下修改:")
    for k, v in updates.items():
        print(f"  {k}: {v}")

    if not input_yes_no("\n确认修改？", default=True):
        print_info("已取消")
        input("\n按 Enter 返回...")
        return

    success = DataCenterService.update_entity(entity_id, **updates)
    if success:
        print_success("修改成功")
    else:
        print_error("修改失败")

    input("\n按 Enter 返回...")


def cmd_delete(entity_id: Optional[str] = None):
    """删除记录"""
    clear_screen()
    print_header("🗑️  删除记录")

    if not entity_id:
        entity_id = input("请输入 entity_id: ").strip()
        if not entity_id:
            return

    entity = DataCenterService.get_entity(entity_id)
    if entity is None:
        print_error(f"记录不存在: {entity_id}")
        input("\n按 Enter 返回...")
        return

    print(f"\n⚠️  即将删除:")
    print(f"  entity_id: {entity_id}")
    print(f"  type:      {entity.get('type')}")
    print(f"  title:     {entity.get('title')}")
    print("\n此操作不可恢复！")

    if not input_yes_no("确认删除？", default=False):
        print_info("已取消")
        input("\n按 Enter 返回...")
        return

    success = DataCenterService.delete_entity(entity_id)
    if success:
        print_success("已删除")
    else:
        print_error("删除失败")

    input("\n按 Enter 返回...")


def cmd_search():
    """搜索/筛选"""
    clear_screen()
    print_header("🔎 搜索/筛选")

    print("\n输入搜索条件（留空则跳过）:")
    type_filter = input_with_default("按类型筛选（如 person, class_log）", "")
    tag_filter = input_with_default("按标签筛选（如 学生, 班务日志）", "")
    title_keyword = input_with_default("标题关键词", "")
    extra_field = input_with_default("extra 字段名（如 score, event, gender）", "")
    extra_value = input_with_default("extra 字段值（支持包含匹配）", "")
    limit_input = input_with_default("最大返回数", "50")
    limit = int(limit_input) if limit_input.isdigit() else 50

    # 关键检查：填了 extra_value 但没填 extra_field
    if extra_value and not extra_field:
        print_warning("填写了 extra 值但未填写 extra 字段名")
        print_info("提示：按性别搜索请填 extra_field = gender")
        if input_yes_no("是否继续？(选否将重新输入)", default=False):
            return

    print("\n🔍 搜索中...")
    print("\n📋 搜索条件:")
    print(f"  类型: {type_filter if type_filter else '(全部)'}")
    print(f"  标签: {tag_filter if tag_filter else '(全部)'}")
    print(f"  标题: {title_keyword if title_keyword else '(全部)'}")
    print(f"  extra.{extra_field}: {extra_value if extra_value else '(全部)'}")
    print(f"  返回上限: {limit} 条")

    results = DataCenterService.search_entities(
        type_filter=type_filter if type_filter else None,
        tag_filter=tag_filter if tag_filter else None,
        title_keyword=title_keyword if title_keyword else None,
        extra_field=extra_field if extra_field else None,
        extra_value=extra_value if extra_value else None,
        limit=limit,
    )

    if not results:
        print("\n📭 没有匹配的记录")
        input("\n按 Enter 返回...")
        return

    print(f"\n📊 找到 {len(results)} 条记录")
    print_separator()
    print(f"{'序号':<4} {'ID':<16} {'类型':<12} {'标题':<20} {'标签'}")
    print_separator()

    for idx, item in enumerate(results, 1):
        tags_str = ",".join(item.get("tags", []))
        print(f"{idx:<4} {item.get('entity_id', ''):<16} {item.get('type', ''):<12} {item.get('title', '')[:20]:<20} {tags_str}")

    print_separator()

    if input_yes_no("\n是否查看某条记录详情？", default=False):
        idx_input = input("请输入序号: ").strip()
        if idx_input.isdigit():
            idx = int(idx_input) - 1
            if 0 <= idx < len(results):
                entity_id = results[idx].get("entity_id")
                if entity_id:
                    cmd_view(entity_id=entity_id)
                else:
                    print_error("该条记录没有 entity_id")
            else:
                print_error("序号无效")
        else:
            print_error("请输入数字")

    input("\n按 Enter 返回...")


def cmd_batch():
    """批量操作"""
    clear_screen()
    print_header("📦 批量操作")

    print("先筛选出要操作的数据:")
    type_filter = input_with_default("按类型筛选", "")
    tag_filter = input_with_default("按标签筛选", "")
    title_keyword = input_with_default("标题关键词", "")

    print("\n🔍 搜索中...")
    results = DataCenterService.search_entities(
        type_filter=type_filter if type_filter else None,
        tag_filter=tag_filter if tag_filter else None,
        title_keyword=title_keyword if title_keyword else None,
        limit=1000,
    )

    if not results:
        print_warning("没有匹配的记录")
        input("\n按 Enter 返回...")
        return

    entity_ids = [r["entity_id"] for r in results]
    print(f"\n📊 匹配 {len(entity_ids)} 条记录")

    if not input_yes_no("是否对这些记录执行批量操作？", default=False):
        print_info("已取消")
        input("\n按 Enter 返回...")
        return

    print("\n批量操作:")
    print("  1. 批量删除")
    print("  2. 批量修改 tags")
    choice = input("请选择 [1/2]: ").strip()

    if choice == "1":
        if input_yes_no(f"\n⚠️  确认删除 {len(entity_ids)} 条记录？", default=False):
            count = DataCenterService.batch_delete(entity_ids)
            print_success(f"已删除 {count} 条")
        else:
            print_info("已取消")

    elif choice == "2":
        tags = input_tags("请输入新标签（逗号分隔）")
        if not tags:
            print_error("标签不能为空")
            input("\n按 Enter 返回...")
            return

        print("  a. 覆盖")
        print("  b. 追加")
        print("  c. 移除")
        mode_choice = input("请选择 [a/b/c]: ").strip().lower()
        mode_map = {"a": "overwrite", "b": "append", "c": "remove"}
        mode = mode_map.get(mode_choice, "overwrite")

        if input_yes_no(f"\n确认 {mode} 标签到 {len(entity_ids)} 条记录？", default=True):
            count = DataCenterService.batch_update_tags(entity_ids, tags, mode)
            print_success(f"已修改 {count} 条")
        else:
            print_info("已取消")

    else:
        print_error("无效选项")

    input("\n按 Enter 返回...")

def cmd_manage_types():
    """管理类型白名单"""
    clear_screen()
    print_header("⚙️  管理类型")

    allowed = DataCenterService.get_allowed_types()
    print(f"\n📋 当前白名单 ({len(allowed)} 个类型):")
    for i, t in enumerate(allowed, 1):
        print(f"  {i}. {t}")

    print("\n操作:")
    print("  1. 添加类型")
    print("  2. 删除类型")
    print("  3. 返回")
    choice = input("请选择 [1-3]: ").strip()

    if choice == "1":
        type_name = input("请输入要添加的类型名称: ").strip()
        if not type_name:
            print_error("类型名称不能为空")
        else:
            if DataCenterService.add_allowed_type(type_name):
                print_success(f"已添加: {type_name}")
            else:
                print_error("添加失败")
        input("\n按 Enter 继续...")

    elif choice == "2":
        if len(allowed) <= 1:
            print_warning("至少保留一个类型，不能删除")
            input("\n按 Enter 继续...")
            return
        idx_str = input("请输入要删除的序号: ").strip()
        if idx_str.isdigit():
            idx = int(idx_str) - 1
            if 0 <= idx < len(allowed):
                type_name = allowed[idx]
                if input_yes_no(f"确认删除 '{type_name}'？", default=False):
                    if DataCenterService.remove_allowed_type(type_name):
                        print_success(f"已删除: {type_name}")
                    else:
                        print_error("删除失败")
            else:
                print_error("序号无效")
        else:
            print_error("请输入数字")
        input("\n按 Enter 继续...")



# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已中断，再见！")
        sys.exit(0)
    except Exception as e:
        print_error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
        input("\n按 Enter 退出...")
        sys.exit(1)
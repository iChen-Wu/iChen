#!/usr/bin/env python3
"""
GYun Data 管理控制台 - 交互式全功能管理工具
运行：python -m GYun.data.admin

数据持久化在项目 runtime/ 目录，不会自动清理。
"""

import os
import sys
import json
from datetime import datetime

from GYun.data.client import GyunClient
from GYun.data.utils.exceptions import (
    EntityNotFoundError,
    ParameterError,
    DatabaseError,
    FileIOError,
)

# ========== 全局客户端 ==========
client = GyunClient(enable_history=True)

# ========== 辅助函数 ==========
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header(title):
    print("\n" + "=" * 55)
    print(f"  {title}")
    print("=" * 55)

def current_source_label():
    """当前应用上下文显示（None = 全局模式）"""
    return client.source if client.source else "全局"
def print_entity(entity, indent=0):
    """格式化打印实体"""
    prefix = "  " * indent
    print(f"{prefix}ID: {entity['entity_id']}")
    print(f"{prefix}类型: {entity['type']}")
    print(f"{prefix}标题: {entity['title']}")
    if entity.get('content'):
        print(f"{prefix}内容: {(entity.get('content') or '')[:80]}...")
    print(f"{prefix}优先级: {entity.get('priority', 0)}")
    print(f"{prefix}应用: {entity.get('source', '-')}")
    if entity.get('tags'):
        print(f"{prefix}标签: {', '.join(entity['tags'])}")
    if entity.get('extra'):
        print(f"{prefix}扩展: {json.dumps(entity['extra'], ensure_ascii=False)}")
    print(f"{prefix}创建时间: {datetime.fromtimestamp(entity['create_time']/1000)}")
    print(f"{prefix}更新时间: {datetime.fromtimestamp(entity['update_time']/1000)}")
    print(f"{prefix}已删除: {'是' if entity.get('is_deleted') else '否'}")

def input_int(prompt, default=None):
    """读取整数输入"""
    while True:
        val = input(prompt)
        if not val and default is not None:
            return default
        try:
            return int(val)
        except ValueError:
            print("请输入有效数字")

def input_str(prompt, default=None):
    val = input(prompt).strip()
    return val if val else default

def input_yes_no(prompt, default='n'):
    val = input(prompt + " (y/N): ").strip().lower()
    if val == 'y':
        return True
    return False

def wait_enter():
    input("\n按 Enter 继续...")

# ========== 菜单功能 ==========

def menu_create():
    """创建实体"""
    print_header("创建实体")
    data = {}
    data['type'] = input_str("类型 (必填): ")
    if not data['type']:
        print("❌ 类型不能为空")
        return
    data['title'] = input_str("标题 (必填): ")
    if not data['title']:
        print("❌ 标题不能为空")
        return
    data['content'] = input_str("内容 (可选): ")
    data['priority'] = input_int("优先级 (0-10, 默认0): ", default=0)
    # V3.0 应用标识：应用模式下自动注入，仅全局模式手动输入（__null__ 表示无归属）
    if client.source is None:
        source = input_str("应用标识 (可选, __null__ 表示无归属): ")
        if source:
            data['source'] = None if source == '__null__' else source
    tags_str = input_str("标签 (逗号分隔, 可选): ")
    if tags_str:
        data['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
    
    # ✅ 改进：extra JSON 解析失败时让用户重试或跳过
    while True:
        extra_str = input_str("扩展字段 (JSON格式, 可选): ")
        if not extra_str:
            break
        try:
            data['extra'] = json.loads(extra_str)
            break
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON格式错误: {e}")
            retry = input_str("重新输入 (r) / 跳过 (s): ").strip().lower()
            if retry == 's':
                break
            # 否则继续循环，让用户重新输入
    
    try:
        eid = client.create_entity(data)
        print(f"✅ 创建成功! ID: {eid}")
    except Exception as e:
        print(f"❌ 创建失败: {e}")

def menu_get():
    """获取实体"""
    print_header("获取实体详情")
    eid = input_str("实体ID: ")
    if not eid:
        return
    try:
        entity = client.get_entity(eid)
        print_entity(entity)
    except EntityNotFoundError:
        print("❌ 实体不存在")
    except Exception as e:
        print(f"❌ 错误: {e}")

def menu_update():
    """更新实体"""
    print_header("更新实体")
    eid = input_str("实体ID: ")
    if not eid:
        return
    try:
        old = client.get_entity(eid)
    except EntityNotFoundError:
        print("❌ 实体不存在")
        return
    print("当前值 (留空则不修改):")
    print(f"  标题: {old['title']}")
    print(f"  内容: {old.get('content','')[:50]}...")
    print(f"  优先级: {old.get('priority',0)}")
    print(f"  应用: {old.get('source','-')}")
    update = {}
    title = input_str("新标题: ")
    if title:
        update['title'] = title
    content = input_str("新内容: ")
    if content:
        update['content'] = content
    priority = input_str("新优先级: ")
    if priority:
        update['priority'] = int(priority)
    source = input_str("新应用标识 (__null__ 清除归属, 留空不修改): ")
    if source:
        update['source'] = None if source == '__null__' else source
    tags_str = input_str("新标签 (逗号分隔, 留空不修改): ")
    if tags_str:
        update['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
    
    # ✅ 改进：extra JSON 解析失败时让用户重试或跳过
    while True:
        extra_str = input_str("新extra (JSON, 留空不修改): ")
        if not extra_str:
            break
        try:
            update['extra'] = json.loads(extra_str)
            break
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON格式错误: {e}")
            retry = input_str("重新输入 (r) / 跳过 (s): ").strip().lower()
            if retry == 's':
                break
            # 否则继续循环，让用户重新输入
    
    if not update:
        print("未做任何修改")
        return
    try:
        client.update_entity(eid, update)
        print("✅ 更新成功")
    except Exception as e:
        print(f"❌ 更新失败: {e}")

def menu_delete():
    """删除实体"""
    print_header("删除实体")
    eid = input_str("实体ID: ")
    if not eid:
        return
    try:
        entity = client.get_entity(eid)
        print(f"即将删除: {entity['title']}")
        hard = input_yes_no("硬删除 (彻底清除)? ", default='n')
        cascade = True
        if hard:
            cascade = input_yes_no("同时删除附件? ", default='y')
        if input_yes_no(f"确认{'硬' if hard else '软'}删除? ", default='n'):
            client.delete_entity(eid, hard=hard, cascade_resource=cascade)
            print("✅ 删除成功")
    except EntityNotFoundError:
        print("❌ 实体不存在")
    except Exception as e:
        print(f"❌ 删除失败: {e}")

def menu_restore():
    """恢复实体"""
    print_header("恢复软删除实体")
    eid = input_str("实体ID: ")
    if not eid:
        return
    try:
        client.restore_entity(eid)
        print("✅ 恢复成功")
    except EntityNotFoundError:
        print("❌ 实体不存在")
    except Exception as e:
        print(f"❌ 恢复失败: {e}")

def menu_list_all():
    """列出全部实体（分页）"""
    print_header("列出全部实体")
    page = input_int("页码 (默认1): ", default=1)
    page_size = input_int("每页条数 (默认10): ", default=10)
    try:
        result = client.query_entities({}, order_by='create_time', order='desc', page=page, page_size=page_size)
        print(f"\n共 {result['total']} 条, 当前第 {result['page']} 页, 每页 {result['page_size']} 条")
        if result['list']:
            for i, ent in enumerate(result['list'], 1):
                print(f"\n--- [{i}] ---")
                print_entity(ent, indent=1)
        else:
            print("无结果")
    except Exception as e:
        print(f"❌ 查询失败: {e}")

def menu_query():
    """多条件查询"""
    print_header("多条件查询")
    filters = {}
    print("输入过滤条件 (留空跳过):")
    type_val = input_str("类型: ")
    if type_val:
        filters['type'] = type_val
    tags_str = input_str("标签 (逗号分隔): ")
    if tags_str:
        filters['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
        mode = input_str("标签模式 (all/any, 默认any): ") or 'any'
        filters['tags_mode'] = mode
    priority_min = input_str("最低优先级: ")
    if priority_min:
        filters['priority_min'] = int(priority_min)
    priority_max = input_str("最高优先级: ")
    if priority_max:
        filters['priority_max'] = int(priority_max)
    # V3.0 应用标识：应用模式下自动限定，仅全局模式手动输入（__null__ 表示无归属）
    if client.source is None:
        source = input_str("应用标识 (__null__ 表示无归属, 留空不限): ")
        if source:
            filters['source'] = None if source == '__null__' else source
    else:
        print(f"  (应用上下文已限定: {client.source})")
    keyword = input_str("标题模糊匹配: ")
    if keyword:
        filters['keyword_title'] = keyword
    extra_key = input_str("extra字段过滤 (格式 key=value): ")
    if extra_key:
        if '=' in extra_key:
            k, v = extra_key.split('=', 1)
            filters[f'extra_{k.strip()}'] = v.strip()
    show_deleted = input_yes_no("包含已删除? ", default='n')
    if show_deleted:
        filters['is_deleted'] = 1
    order_by = input_str("排序字段 (create_time/update_time/priority/title, 默认create_time): ") or 'create_time'
    order = input_str("排序方向 (asc/desc, 默认desc): ") or 'desc'
    page = input_int("页码 (默认1): ", default=1)
    page_size = input_int("每页条数 (默认10): ", default=10)
    try:
        result = client.query_entities(filters, order_by=order_by, order=order, page=page, page_size=page_size)
        print(f"\n共 {result['total']} 条, 当前第 {result['page']} 页, 每页 {result['page_size']} 条")
        if result['list']:
            for i, ent in enumerate(result['list'], 1):
                print(f"\n--- [{i}] ---")
                print_entity(ent, indent=1)
        else:
            print("无结果")
    except Exception as e:
        print(f"❌ 查询失败: {e}")

def menu_search():
    """全文搜索"""
    print_header("全文检索")
    keyword = input_str("搜索关键词: ")
    if not keyword:
        return
    filters = {}
    type_val = input_str("限定类型 (可选): ")
    if type_val:
        filters['type'] = type_val
    page = input_int("页码 (默认1): ", default=1)
    page_size = input_int("每页条数 (默认10): ", default=10)
    try:
        result = client.fulltext_search(keyword, filters=filters, page=page, page_size=page_size)
        print(f"\n共 {result['total']} 条, 当前第 {result['page']} 页")
        if result['list']:
            for i, ent in enumerate(result['list'], 1):
                print(f"\n--- [{i}] ---")
                print_entity(ent, indent=1)
        else:
            print("无结果")
    except Exception as e:
        print(f"❌ 搜索失败: {e}")

def menu_batch_create():
    """批量创建"""
    print_header("批量创建实体")
    print("输入实体数据，每行一个JSON，空行结束:")
    lines = []
    while True:
        line = input()
        if not line:
            break
        lines.append(line)
    if not lines:
        print("未输入数据")
        return
    data_list = []
    for i, line in enumerate(lines, 1):
        try:
            data_list.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"⚠️ 第{i}行JSON格式错误，跳过")
    if not data_list:
        return
    on_error = input_str("错误处理模式 (rollback/skip, 默认rollback): ") or 'rollback'
    try:
        ids = client.batch_create_entities(data_list, on_error=on_error)
        print(f"✅ 成功创建 {len(ids)} 条")
        print("IDs:", ids)
    except Exception as e:
        print(f"❌ 批量创建失败: {e}")

def menu_stats():
    """统计信息"""
    print_header("统计信息")
    try:
        total = client.count_entities()
        print(f"总实体数: {total}")
        groups = client.group_count('type')
        if groups:
            print("按类型分布:")
            for g in groups:
                print(f"  {g['type']}: {g['cnt']}")
    except Exception as e:
        print(f"❌ 统计失败: {e}")


def menu_app_context():
    """应用上下文管理：切换 / 列表 / 一键删除"""
    while True:
        clear_screen()
        print_header(f"应用上下文管理 (当前: {current_source_label()})")
        print("1. 切换应用")
        print("2. 列出所有应用")
        print("3. 一键删除当前应用")
        print("0. 返回主菜单")
        choice = input_str("请选择: ")
        if choice == '1':
            hint = f"输入应用标识 (当前: {current_source_label()}, 留空=全局模式): "
            new_source = input_str(hint)
            try:
                client.set_source(new_source or None)
                print(f"✅ 已切换: {current_source_label()}")
            except Exception as e:
                print(f"❌ 切换失败: {e}")
        elif choice == '2':
            print_header("全部应用 (按实体数统计)")
            try:
                groups = client.group_count('source')
                if groups:
                    for g in groups:
                        label = g['type'] if g['type'] is not None else '(无归属/旧数据)'
                        print(f"  {label}: {g['cnt']}")
                else:
                    print("  (无数据)")
            except Exception as e:
                print(f"❌ 查询失败: {e}")
        elif choice == '3':
            if client.source is None:
                print("⚠️  当前为全局模式，请先切换到要删除的应用")
            else:
                total = client.count_entities({'is_deleted': None})  # 含软删记录的全量
                print(f"⚠️  即将彻底删除应用「{client.source}」的全部 {total} 条实体及其附件目录!")
                confirm = input(f"请输入应用标识 {client.source} 以确认: ").strip()
                if confirm != client.source:
                    print("取消操作")
                else:
                    try:
                        deleted = client.delete_application(client.source)
                        client.set_source(None)
                        print(f"✅ 已删除应用 {deleted} 条实体 (级联向量/边/标签 + 附件目录)")
                    except Exception as e:
                        print(f"❌ 删除失败: {e}")
        elif choice == '0':
            break
        wait_enter()


def menu_batch_delete():
    """批量删除实体"""
    print_header("批量删除实体")
    print("输入过滤条件（留空表示全部实体）：")
    filters = {}
    type_val = input_str("类型（可选）: ")
    if type_val:
        filters['type'] = type_val
    tags_str = input_str("标签（逗号分隔，可选）: ")
    if tags_str:
        filters['tags'] = [t.strip() for t in tags_str.split(',') if t.strip()]
        mode = input_str("标签模式 (all/any, 默认any): ") or 'any'
        filters['tags_mode'] = mode
    # 预览数量
    try:
        total = client.count_entities(filters)
        if total == 0:
            print("没有符合条件的实体")
            return
        print(f"将删除 {total} 个实体")
        hard = input_yes_no("硬删除（彻底清除）? ", default='n')
        confirm = input(f"请输入 DELETE 确认删除这 {total} 个实体: ").strip()
        if confirm != 'DELETE':
            print("取消操作")
            return
        # 执行删除
        deleted = 0
        for entity in client.iter_all_entities(filters, batch_size=100):
            eid = entity['entity_id']
            client.delete_entity(eid, hard=hard, cascade_resource=True)
            deleted += 1
            if deleted % 10 == 0:
                print(f"已删除 {deleted}/{total}")
        print(f"✅ 成功删除 {deleted} 个实体")
    except Exception as e:
        print(f"❌ 批量删除失败: {e}")



def menu_maintenance():
    """运维菜单"""
    while True:
        clear_screen()
        print_header("运维工具")
        print("1. 备份数据库")
        print("2. 恢复数据库")
        print("3. VACUUM (压缩)")
        print("4. 完整性检查")
        print("5. 垃圾回收 (GC)")
        print("0. 返回主菜单")
        choice = input_str("请选择: ")
        if choice == '1':
            try:
                path = client.backup()
                print(f"✅ 备份成功: {path}")
            except Exception as e:
                print(f"❌ 备份失败: {e}")
        elif choice == '2':
            path = input_str("备份文件路径: ")
            if path:
                try:
                    client.restore(path)
                    print("✅ 恢复成功，客户端已重新连接")
                except Exception as e:
                    print(f"❌ 恢复失败: {e}")
        elif choice == '3':
            try:
                client.vacuum()
                print("✅ VACUUM 完成")
            except Exception as e:
                print(f"❌ VACUUM 失败: {e}")
        elif choice == '4':
            result = client.integrity_check()
            print(f"状态: {'✅ 通过' if result['ok'] else '❌ 失败'}")
            if not result['ok']:
                print("详细信息:")
                for d in result['details']:
                    print(f"  {d}")
        elif choice == '5':
            execute = input_yes_no("实际删除孤立文件? (否则仅预览): ", default='n')
            try:
                orphans = client.gc(execute=execute)
                if orphans:
                    print(f"发现 {len(orphans)} 个孤立文件:")
                    for o in orphans:
                        print(f"  {o}")
                else:
                    print("没有孤立文件")
            except Exception as e:
                print(f"❌ GC 失败: {e}")
        elif choice == '0':
            break
        wait_enter()

# ========== 主菜单 ==========
def main_menu():
    while True:
        clear_screen()
        print_header(f"GYun Data 管理控制台 (当前应用: {current_source_label()})")
        print("1. 创建实体")
        print("2. 查看实体")
        print("3. 更新实体")
        print("4. 删除实体")
        print("5. 恢复实体")
        print("6. 列出全部实体")
        print("7. 多条件查询")
        print("8. 全文检索")
        print("9. 批量创建")
        print("10. 统计信息")
        print("11. 运维工具")
        print("12. 批量删除")
        print("13. 应用上下文管理")
        print("0. 退出")
        choice = input_str("\n请选择: ")
        if choice == '1':
            menu_create()
        elif choice == '2':
            menu_get()
        elif choice == '3':
            menu_update()
        elif choice == '4':
            menu_delete()
        elif choice == '5':
            menu_restore()
        elif choice == '6':
            menu_list_all()
        elif choice == '7':
            menu_query()
        elif choice == '8':
            menu_search()
        elif choice == '9':
            menu_batch_create()
        elif choice == '10':
            menu_stats()
        elif choice == '11':          # ✅ 修复：11 对应运维工具
            menu_maintenance()
        elif choice == '12':          # ✅ 修复：12 对应批量删除
            menu_batch_delete()
        elif choice == '13':          # ✅ V3.0：应用上下文管理
            menu_app_context()
        elif choice == '0':
            print("再见!")
            client.close()
            break
        else:
            print("无效选项")
        if choice != '0':
            wait_enter()

if __name__ == '__main__':
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n退出程序")
        client.close()
    except Exception as e:
        print(f"\n❌ 程序异常: {e}")
        client.close()
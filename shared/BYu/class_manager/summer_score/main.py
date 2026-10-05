#!/usr/bin/env python3
"""
暑期积分管理系统 - 日常交互程序
"""
from BYu.class_manager.summer_score.exporter import export_full_summary
from GYun.data.client import GyunClient
from BYu.class_manager.summer_score.pipeline import run_daily_pipeline, clear_all_ledger_data, export_scores_json
from BYu.class_manager.summer_score.ledger import load_score_ledger, load_student_group_map, get_student_day_record, update_student_ledger, save_score_ledger
from BYu.class_manager.summer_score.config import NAME_LIST, EXEMPT_NAMES, NAME_ALIAS
import pyperclip
from datetime import datetime, date
import json

def safe_input(prompt: str) -> str:
    user_input = input(prompt).strip()
    if user_input.lower() == 'quit':
        print("👋 已退出。")
        exit(0)
    return user_input

def load_multiline(prompt: str) -> str:
    print(prompt)
    print("（直接粘贴文本，完成后连续按两次回车（输入两个空行）结束）")
    lines = []
    empty_count = 0
    while True:
        line = input()
        if line.strip() == '':
            empty_count += 1
            if empty_count >= 2:
                break
            else:
                lines.append(line)
                continue
        else:
            empty_count = 0
            lines.append(line)
    return '\n'.join(lines)

def run_daily(client: GyunClient) -> None:
    print("\n=== 每日流水线 ===")
    print("\n⚠️ 注意输入规则：")
    print("   - 上午接龙：早起【名单】+1分，迟到【名单】-1分，其余不变")
    print("   - 下午接龙：粘贴【已完成】的学生名单")
    print("   - 打卡（上午/下午）：粘贴【未完成】的学生名单")
    print("   - 作业接龙：固定格式（小组汇报）")
    print("-" * 40)

    date_input = input("请输入日期（MM-DD），直接回车使用今天：").strip()
    if date_input:
        try:
            year = datetime.now().year
            target_date = f"{year}-{date_input}"
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式错误，请使用 MM-DD 格式。")
            return
    else:
        target_date = date.today().isoformat()

    morning_early = load_multiline("▸ 上午接龙-早起【名单】：")
    morning_late = load_multiline("▸ 上午接龙-迟到【名单】：")
    afternoon_chain = load_multiline("▸ 下午接龙【已完成名单】：")
    morning_checkin = load_multiline("▸ 上午打卡【未完成名单】：")
    afternoon_checkin = load_multiline("▸ 下午打卡【未完成名单】：")
    homework = load_multiline("▸ 作业接龙（固定格式）：")

    print("⏳ 正在处理...")
    try:
        summary = run_daily_pipeline(
            morning_early_text=morning_early,
            morning_late_text=morning_late,
            afternoon_chain_text=afternoon_chain,
            morning_checkin_text=morning_checkin,
            afternoon_checkin_text=afternoon_checkin,
            homework_text=homework,
            ledger_client=client,
            target_date=target_date
        )
        print("\n" + "=" * 40)
        print(summary)
        print("=" * 40)
        try:
            pyperclip.copy(summary)
            print("📋 总结已自动复制到剪贴板！")
        except:
            pass
    except Exception as e:
        print(f"❌ 运行出错：{e}")

def view_student_ledger(client: GyunClient) -> None:
    """查看指定学生台账（新格式）"""
    ledger = load_score_ledger(client)
    if not ledger:
        print("⚠️ 台账为空。")
        return
    print("\n已录入的学生：")
    names = sorted(ledger.keys())
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")
    name = safe_input("请输入要查看的学生姓名：")
    if name in NAME_ALIAS:
        name = NAME_ALIAS[name]
    if name not in ledger:
        print(f"❌ 未找到学生 '{name}'。")
        return
    records = ledger[name]['records']
    if not records:
        print(f"📭 {name} 暂无记录。")
        return
    print(f"\n📋 {name} 的台账：")
    print("-" * 50)
    total = 0
    for rec in sorted(records, key=lambda r: r['date']):
        d = rec['date']
        score = rec['final_score']
        total += score
        flags = []
        if rec.get('is_leave', False):
            flags.append("请假")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        mc = rec.get('morning_late_deduct', 0)  # 上午接龙迟到扣分
        ac = rec.get('afternoon_chain_deduct', 0)
        mch = rec.get('morning_checkin_deduct', 0)
        ach = rec.get('afternoon_checkin_deduct', 0)
        print(f"{d} | 接龙:上{mc}下{ac} 打卡:上{mch}下{ach} | 考勤扣{rec.get('attendance_deduct', 0)} 作业扣{rec.get('homework_deduct', 0)} | 当日{score:+.1f} | 累计{total:+.1f}{flag_str}")
        if rec.get('missing_subjects'):
            print(f"       缺科：{'、'.join(rec['missing_subjects'])}")
    print("-" * 50)
    print(f"📊 当前总分：{total:+.1f}")

def view_all_scores(client: GyunClient) -> None:
    ledger = load_score_ledger(client)
    if not ledger:
        print("⚠️ 台账为空。")
        return
    scores = {}
    for name, info in ledger.items():
        total = sum(rec['final_score'] for rec in info['records'])
        scores[name] = total
    print("\n📊 全体学生总分排名：")
    print("-" * 30)
    for i, (name, score) in enumerate(sorted(scores.items(), key=lambda x: x[1], reverse=True), 1):
        print(f"{i:2}. {name:　<5} {score:+.1f}")
    print("-" * 30)

def view_group_map(client: GyunClient) -> None:
    group_map = load_student_group_map(client)
    if not group_map:
        print("⚠️ 分组映射为空。")
        return
    print("\n📋 学生分组映射：")
    groups = {}
    for name, group in group_map.items():
        groups.setdefault(group, []).append(name)
    for group in sorted(groups.keys()):
        print(f"  {group}（{len(groups[group])}人）：{'、'.join(groups[group])}")

def clear_data(client: GyunClient) -> None:
    confirm = safe_input("⚠️ 确认清空所有暑期积分数据？输入 y 继续：")
    if confirm.lower() == 'y':
        clear_all_ledger_data(client)
        print("✅ 已清空所有台账数据。")
    else:
        print("操作已取消。")

def export_scores(client: GyunClient) -> None:
    path = safe_input("请输入导出文件路径（例如 scores.json）：")
    try:
        export_scores_json(client, path)
    except Exception as e:
        print(f"❌ 导出失败：{e}")

def show_summary_stats(client: GyunClient) -> None:
    """打印每位学生缺勤次数（按四项统计）和缺交科目数（展示）"""
    ledger = load_score_ledger(client)
    if not ledger:
        print("⚠️ 台账为空。")
        return
    lines = []
    for name, info in ledger.items():
        absence_cnt = 0
        hw_missing_cnt = 0
        for rec in info['records']:
            if rec.get('is_leave', False):
                continue
            # 扣分值大于0表示未完成
            if rec.get('morning_late_deduct', 0) > 0:
                absence_cnt += 1
            if rec.get('afternoon_chain_deduct', 0) > 0:
                absence_cnt += 1
            if rec.get('morning_checkin_deduct', 0) > 0:
                absence_cnt += 1
            if rec.get('afternoon_checkin_deduct', 0) > 0:
                absence_cnt += 1
            hw_missing_cnt += len(rec.get('missing_subjects', []))
        lines.append(f"{name}：缺勤{absence_cnt}次　缺交{hw_missing_cnt}次")
    lines.sort(key=lambda s: (
        -int(s.split('缺勤')[1].split('次')[0]),
        -int(s.split('缺交')[1].split('次')[0]),
        s.split('：')[0]
    ))
    print("\n📊 汇总统计（缺勤次数 / 缺交科目数）")
    print("-" * 50)
    for line in lines:
        print(line)
    print("-" * 50)

def export_all_data(client: GyunClient) -> None:
    ledger = load_score_ledger(client)
    group_map = load_student_group_map(client)
    if not ledger and not group_map:
        print("⚠️ 没有任何数据可导出。")
        return
    path = safe_input("请输入导出文件路径（例如 full_backup.json）：")
    try:
        data = {"ledger": ledger, "group_map": group_map}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        total_records = sum(len(info['records']) for info in ledger.values())
        print(f"✅ 已导出全部数据：{len(ledger)} 名学生，共 {total_records} 条日记录。")
    except Exception as e:
        print(f"❌ 导出失败：{e}")

def modify_student_data(client: GyunClient) -> None:
    """手动逐项修改（单个学生），直接修改扣分值"""
    ledger = load_score_ledger(client)
    if not ledger:
        print("⚠️ 台账为空，请先运行每日流水线。")
        return
    print("\n已录入的学生：")
    names = sorted(ledger.keys())
    for i, name in enumerate(names, 1):
        print(f"  {i}. {name}")
    name = safe_input("请输入学生姓名：")
    if name in NAME_ALIAS:
        name = NAME_ALIAS[name]
    if name not in ledger:
        print(f"❌ 未找到学生 '{name}'。")
        return
    records = ledger[name]['records']
    if not records:
        print(f"📭 {name} 暂无记录。")
        return
    print(f"\n{name} 已有记录的日期：")
    dates = sorted([rec['date'] for rec in records])
    for d in dates:
        print(f"  {d}")
    date_str = safe_input("请输入要修改的日期（YYYY-MM-DD）：")
    if date_str not in dates:
        print("❌ 该日期无记录。")
        return
    rec = get_student_day_record(ledger, name, date_str)
    if not rec:
        print("❌ 记录不存在。")
        return

    print("\n当前记录：")
    print(f"早起加分: {rec.get('morning_early_bonus', 0)}")
    print(f"上午接龙迟到扣分: {rec.get('morning_late_deduct', 0)}")
    print(f"下午接龙扣分: {rec.get('afternoon_chain_deduct', 0)}")
    print(f"上午打卡扣分: {rec.get('morning_checkin_deduct', 0)}")
    print(f"下午打卡扣分: {rec.get('afternoon_checkin_deduct', 0)}")
    print(f"请假: {'是' if rec.get('is_leave', False) else '否'}")
    print(f"考勤扣分总和: {rec.get('attendance_deduct', 0)}")
    print(f"作业扣分: {rec.get('homework_deduct', 0)}")
    print(f"最终得分: {rec.get('final_score', 0):+.1f}")

    print("\n直接输入新扣分值（0=不扣，回车跳过）：")
    val = input(f"早起加分 当前={rec.get('morning_early_bonus', 0)}，新值：").strip()
    if val:
        rec['morning_early_bonus'] = int(val)
    val = input(f"上午接龙迟到 当前={rec.get('morning_late_deduct', 0)}，新值：").strip()
    if val:
        rec['morning_late_deduct'] = int(val)
    val = input(f"下午接龙 当前={rec.get('afternoon_chain_deduct', 0)}，新值：").strip()
    if val:
        rec['afternoon_chain_deduct'] = int(val)
    val = input(f"上午打卡 当前={rec.get('morning_checkin_deduct', 0)}，新值：").strip()
    if val:
        rec['morning_checkin_deduct'] = int(val)
    val = input(f"下午打卡 当前={rec.get('afternoon_checkin_deduct', 0)}，新值：").strip()
    if val:
        rec['afternoon_checkin_deduct'] = int(val)

    ans = input(f"请假 当前={'是' if rec.get('is_leave', False) else '否'}，修改？(y/n): ").strip().lower()
    if ans == 'y':
        val = input("是否请假 (0=否, 1=是): ").strip()
        if val in ('0', '1'):
            rec['is_leave'] = bool(int(val))

    # 重新计算
    attendance_deduct = (
        rec.get('morning_late_deduct', 0) +
        rec.get('afternoon_chain_deduct', 0) +
        rec.get('morning_checkin_deduct', 0) +
        rec.get('afternoon_checkin_deduct', 0)
    )
    homework_deduct = len(rec.get('missing_subjects', []))
    if rec.get('is_leave', False):
        rec['final_score'] = 0
        rec['attendance_deduct'] = 0
        rec['homework_deduct'] = 0
    else:
        rec['attendance_deduct'] = attendance_deduct
        rec['homework_deduct'] = homework_deduct
        rec['final_score'] = -(attendance_deduct + homework_deduct) + rec.get('homework_bonus', 0) + rec.get('morning_early_bonus', 0)

    update_student_ledger(ledger, name, rec)
    save_score_ledger(ledger, client)
    print(f"✅ {name} 的 {date_str} 记录已更新，新积分为 {rec['final_score']:+.1f}")

def batch_modify_students(client: GyunClient) -> None:
    """
    批量快捷修改：格式为 "姓名 字段:扣分值 字段:扣分值 ..."
    字段：1=上午接龙迟到, 2=下午接龙, 3=上午打卡, 4=下午打卡, 5=作业缺科数
    扣分值：整数（0=不扣，1=扣1分，5=扣5分）
    示例：陈熠庭 1:5 2:1 3:1 4:1
    """
    from BYu.class_manager.summer_score.ledger import (
        load_score_ledger, save_score_ledger,
        get_student_day_record, update_student_ledger
    )
    from BYu.class_manager.summer_score.scoring import build_day_record
    from BYu.class_manager.summer_score.config import NAME_ALIAS

    print("\n" + "=" * 50)
    print("📋 批量快捷修改")
    print("=" * 50)
    print("格式：姓名 字段:扣分值 字段:扣分值 ...")
    print("字段说明：")
    print("  1=上午接龙迟到  2=下午接龙  3=上午打卡  4=下午打卡  5=作业缺科数")
    print("扣分值：整数（0=不扣，1=扣1分，5=扣5分）")
    print("示例：陈熠庭 1:5 2:1 3:1 4:1")
    print("-" * 50)

    date_input = input("请输入要修改的日期（MM-DD）：").strip()
    if not date_input:
        print("❌ 日期不能为空。")
        return
    try:
        year = datetime.now().year
        full_date = f"{year}-{date_input}"
        datetime.strptime(full_date, "%Y-%m-%d")
    except ValueError:
        print("❌ 日期格式错误，请使用 MM-DD 格式。")
        return

    print("\n请输入修改指令（每行一条，空行结束）：")
    lines = []
    while True:
        line = input().strip()
        if not line:
            break
        line = line.replace('：', ':')
        lines.append(line)

    if not lines:
        print("⚠️ 未输入任何数据。")
        return

    ledger = load_score_ledger(client)
    commands = []
    errors = []

    for idx, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) < 2:
            errors.append(f"第{idx}行：格式错误（至少需要姓名和1个字段）")
            continue

        name = parts[0]
        if name in NAME_ALIAS:
            name = NAME_ALIAS[name]

        if name not in ledger:
            errors.append(f"第{idx}行：未找到学生 '{name}'")
            continue

        rec = get_student_day_record(ledger, name, full_date)
        if not rec:
            errors.append(f"第{idx}行：{name} 在 {full_date} 无记录")
            continue

        updates = {}
        for part in parts[1:]:
            if ':' not in part:
                errors.append(f"第{idx}行：字段格式错误（缺少:）：{part}")
                continue
            field_str, value_str = part.split(':', 1)
            try:
                field = int(field_str)
            except ValueError:
                errors.append(f"第{idx}行：字段编号必须是数字：{field_str}")
                continue

            if field not in [1, 2, 3, 4, 5]:
                errors.append(f"第{idx}行：无效字段编号 {field}，有效值 1-5")
                continue

            try:
                value = int(value_str)
            except ValueError:
                errors.append(f"第{idx}行：字段{field} 的值必须是整数：{value_str}")
                continue


            updates[field] = value

        if errors:
            continue

        commands.append({
            'name': name,
            'rec': rec,
            'updates': updates
        })

    if errors:
        print("\n❌ 发现以下错误，全部操作已取消：")
        for err in errors:
            print(f"  {err}")
        return

    print("\n📋 即将执行以下修改：")
    print("-" * 60)
    field_names = {1: '上午接龙迟到', 2: '下午接龙', 3: '上午打卡', 4: '下午打卡', 5: '作业缺科'}
    for cmd in commands:
        desc = []
        for f, v in sorted(cmd['updates'].items()):
            if f == 5:
                desc.append(f"作业缺科→{v}科")
            else:
                desc.append(f"{field_names[f]}→扣{v}分")
        print(f"  {cmd['name']} {full_date[5:]}: {' '.join(desc)}")
    print("-" * 60)

    confirm = input("确认执行？(y/n): ").strip().lower()
    if confirm != 'y':
        print("操作已取消。")
        return

    success_count = 0
    for cmd in commands:
        old = cmd['rec']
        mc_deduct = 0
        mc_late_deduct = old.get('morning_late_deduct', 0)
        ac_deduct = old.get('afternoon_chain_deduct', 0)
        mch_deduct = old.get('morning_checkin_deduct', 0)
        ach_deduct = old.get('afternoon_checkin_deduct', 0)
        missing_subjects = old.get('missing_subjects', [])

        if 1 in cmd['updates']:
            mc_late_deduct = cmd['updates'][1]
        if 2 in cmd['updates']:
            ac_deduct = cmd['updates'][2]
        if 3 in cmd['updates']:
            mch_deduct = cmd['updates'][3]
        if 4 in cmd['updates']:
            ach_deduct = cmd['updates'][4]
        if 5 in cmd['updates']:
            count = cmd['updates'][5]
            old_subjects = old.get('missing_subjects', [])
            if len(old_subjects) >= count:
                missing_subjects = old_subjects[:count]
            else:
                missing_subjects = old_subjects + ["待补"] * (count - len(old_subjects))

        new_rec = build_day_record(
            date=full_date,
            morning_chain_deduct=mc_deduct,
            afternoon_chain_deduct=ac_deduct,
            morning_checkin_deduct=mch_deduct,
            afternoon_checkin_deduct=ach_deduct,
            is_leave=old.get('is_leave', False),
            missing_subjects=missing_subjects,
            morning_early_bonus=old.get('morning_early_bonus', 0),
            morning_late_deduct=mc_late_deduct
        )
        update_student_ledger(ledger, cmd['name'], new_rec)
        success_count += 1
        print(f"  ✅ {cmd['name']} 已更新")

    save_score_ledger(ledger, client)
    print(f"\n✅ 批量修改完成：成功 {success_count} 条。")

def export_daily(client: GyunClient) -> None:
    """导出当天明细（含小组排名）"""
    from BYu.class_manager.summer_score.exporter import export_daily_report
    import os
    from datetime import datetime, date

    # 选择日期
    date_input = input("请输入日期（MM-DD），直接回车使用今天：").strip()
    if date_input:
        try:
            year = datetime.now().year
            target_date = f"{year}-{date_input}"
            datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式错误，请使用 MM-DD 格式。")
            return
    else:
        target_date = date.today().isoformat()

    save_dir = "D:/data/xlsx"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    date_str = target_date[5:].replace('-', '.')
    path = os.path.join(save_dir, f"{date_str}单日积分.xlsx")
    try:
        export_daily_report(client, path, target_date)
        print(f"✅ 单日明细报表已生成：{path}")
    except Exception as e:
        print(f"❌ 导出失败：{e}")

def export_full(client: GyunClient) -> None:
    """导出全部汇总（矩阵式），支持选择时间区段"""
    import os
    from datetime import datetime, date

    # 询问是否指定时间区段
    print("\n📅 导出全部汇总，可选择时间区段")
    print("直接回车将导出所有数据")
    choice = input("是否指定日期范围？(y/n，直接回车=全部): ").strip().lower()
    
    start_date = None
    end_date = None
    year = datetime.now().year

    if choice == 'y':
        start_input = input("请输入起始日期（MM-DD）：").strip()
        if start_input:
            try:
                start_date = f"{year}-{start_input}"
                datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                print("❌ 起始日期格式错误，将导出全部数据。")
                start_date = None

        end_input = input("请输入结束日期（MM-DD）：").strip()
        if end_input:
            try:
                end_date = f"{year}-{end_input}"
                datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                print("❌ 结束日期格式错误，将导出全部数据。")
                end_date = None

    save_dir = "D:/data/xlsx"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    
    # 文件名体现范围
    if start_date and end_date:
        s = start_date[5:].replace('-', '.')
        e = end_date[5:].replace('-', '.')
        filename = f"累积积分汇总_{s}-{e}.xlsx"
    elif start_date:
        s = start_date[5:].replace('-', '.')
        filename = f"累积积分汇总_从{s}开始.xlsx"
    elif end_date:
        e = end_date[5:].replace('-', '.')
        filename = f"累积积分汇总_到{e}结束.xlsx"
    else:
        filename = "累积积分汇总.xlsx"
    
    path = os.path.join(save_dir, filename)
    try:
        export_full_summary(client, path, start_date, end_date)
        print(f"✅ 全部汇总报表已生成：{path}")
    except ValueError as ve:
        print(f"❌ {ve}")
    except Exception as e:
        print(f"❌ 导出失败：{e}")


def print_menu() -> None:
    print("\n" + "=" * 50)
    print("  暑期积分管理系统（新规则）")
    print("=" * 50)
    print("1. 运行每日流水线（5项输入）")
    print("2. 查看学生台账")
    print("3. 查看全班总分排名")
    print("4. 查看分组映射")
    print("5. 清空所有数据")
    print("6. 导出总分 JSON")
    print("7. 显示汇总统计（缺勤/缺交）")
    print("8. 保存全部数据（备份）")
    print("9. 修改学生某日数据（逐项）")
    print("a. 查询未接龙名单（临时）")
    print("b. 查询未打卡名单（临时）")
    print("c. 导出当天明细（含小组排名）")
    print("d. 导出全部汇总（矩阵式）")
    print("e. 批量快捷修改（格式：姓名 字段:新值）")
    print("0. 退出")
    print("-" * 50)

def main():
    client = GyunClient()
    print("初始化数据...")
    _ = load_student_group_map(client)
    while True:
        print_menu()
        choice = safe_input("请输入选项 (0-9,a-e)：")
        if choice == '1':
            run_daily(client)
        elif choice == '2':
            view_student_ledger(client)
        elif choice == '3':
            view_all_scores(client)
        elif choice == '4':
            view_group_map(client)
        elif choice == '5':
            clear_data(client)
        elif choice == '6':
            export_scores(client)
        elif choice == '7':
            show_summary_stats(client)
        elif choice == '8':
            export_all_data(client)
        elif choice == '9':
            modify_student_data(client)
        elif choice.lower() == 'a':
            query_missing(client, 'chain')
        elif choice.lower() == 'b':
            query_missing(client, 'checkin')
        elif choice.lower() == 'c':
            export_daily(client)
        elif choice.lower() == 'd':
            export_full(client)
        elif choice.lower() == 'e':
            batch_modify_students(client)
        elif choice == '0':
            break
        else:
            print("❌ 无效选项，请重新输入。")
    client.close()
    print("👋 再见。")

# ---- 辅助查询功能 ----
def query_missing(client: GyunClient, mode: str) -> None:
    """
    mode: 'chain' 或 'checkin'
    从粘贴文本中提取姓名，输出通知文本。
    """
    from BYu.class_manager.summer_score.parser import parse_free_checkin
    print(f"请粘贴要查询的名单（{mode}），连续按两次回车结束：")
    raw = load_multiline("▸ 粘贴名单：")
    all_students = NAME_LIST
    names_set = parse_free_checkin(raw, all_students)
    if not names_set:
        print("⚠️ 未识别到任何学生姓名。")
        return
    exempt_set = set(EXEMPT_NAMES)
    missing = sorted([name for name in all_students if name not in names_set and name not in exempt_set])
    if not missing:
        print("✅ 所有学生均已打卡/接龙")
        return
    now = datetime.now().strftime("%H:%M")
    if mode == 'chain':
        msg = f"截止至 {now}，未接龙同学：{'、'.join(missing)}"
    else:
        msg = f"截止至 {now}，未打卡同学：{'、'.join(missing)}"
    print("\n" + msg)
    try:
        pyperclip.copy(msg)
        print("📋 已复制到剪贴板！")
    except:
        pass

def query_chain() -> str:
    """临时查询未接龙名单（自动读取剪贴板），返回结果提示文本。"""
    from BYu.class_manager.summer_score.parser import parse_free_checkin
    from BYu.class_manager.summer_score.config import NAME_LIST, EXEMPT_NAMES

    print("\n📋 正在读取剪贴板内容...")
    try:
        raw = pyperclip.paste().strip()
    except Exception as e:
        tip = f"❌ 读取剪贴板失败：{e}"
        print(tip)
        return tip

    if not raw:
        tip = "⚠️ 剪贴板为空，请先复制【已接龙】名单。"
        print(tip)
        return tip

    print(f"📝 已读取 {len(raw)} 个字符")
    all_students = NAME_LIST
    done_set = parse_free_checkin(raw, all_students)
    if not done_set:
        tip = "⚠️ 未识别到任何学生姓名。"
        print(tip)
        return tip
    exempt_set = set(EXEMPT_NAMES)
    missing = sorted([name for name in all_students if name not in done_set and name not in exempt_set])
    now = datetime.now().strftime("%H:%M")
    if not missing:
        tip = f"截止至{now}，所有学生均已接龙"
        try:
            pyperclip.copy(tip)
        except:
            pass
        print(tip)
        return tip
    msg = f"截止至 {now}，共{len(missing)}人未接龙：{'、'.join(missing)}"
    print("\n" + msg)
    try:
        pyperclip.copy(msg)
        print("📋 结果已复制到剪贴板！")
    except:
        pass
    return msg


def query_checkin() -> None:
    """临时查询未打卡名单（自动读取剪贴板）"""
    from BYu.class_manager.summer_score.parser import parse_free_checkin
    from BYu.class_manager.summer_score.config import NAME_LIST, EXEMPT_NAMES

    print("\n📋 正在读取剪贴板内容...")
    try:
        raw = pyperclip.paste().strip()
    except Exception as e:
        print(f"❌ 读取剪贴板失败：{e}")
        return

    if not raw:
        print("⚠️ 剪贴板为空，请先复制【已打卡】名单。")
        return

    print(f"📝 已读取 {len(raw)} 个字符")
    all_students = NAME_LIST
    done_set = parse_free_checkin(raw, all_students)
    if not done_set:
        print("⚠️ 未识别到任何学生姓名。")
        return
    exempt_set = set(EXEMPT_NAMES)
    missing = sorted([name for name in all_students if name not in done_set and name not in exempt_set])
    if not missing:
        print("✅ 所有学生均已打卡（豁免学生自动忽略）")
        return
    now = datetime.now().strftime("%H:%M")
    msg = f"截止至 {now}，未打卡同学：{'、'.join(missing)}"
    print("\n" + msg)
    try:
        pyperclip.copy(msg)
        print("📋 结果已复制到剪贴板！")
    except:
        pass

if __name__ == '__main__':
    main()
    #m = query_chain()
    #print(m)
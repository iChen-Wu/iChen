"""晚间总结文本生成（含早起/迟到、缺勤、作业缺科展示、最优最差小组）"""

def chinese_to_arabic(chinese_num):
    map = {'一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9}
    return map.get(chinese_num, 0)

def build_evening_summary(target_date: str,
                          morning_early_list: list,
                          morning_late_list: list,
                          afternoon_chain_missing: list,
                          morning_checkin_missing: list,
                          afternoon_checkin_missing: list,
                          leave_stat: dict,
                          group_incomplete: dict,
                          group_daily_score: dict = None) -> str:
    lines = [f"{target_date} 学习总结", ""]

    # 1. 早起
    lines.append("1.早起")
    lines.append('、'.join(morning_early_list) if morning_early_list else "无")
    lines.append("")

    # 2. 迟到
    lines.append("2.迟到")
    lines.append('、'.join(morning_late_list) if morning_late_list else "无")
    lines.append("")

    # 3. 下午接龙缺勤
    lines.append("3.下午接龙缺勤")
    lines.append('、'.join(afternoon_chain_missing) if afternoon_chain_missing else "无")
    lines.append("")

    # 4. 上午打卡缺勤
    lines.append("4.上午打卡缺勤")
    lines.append('、'.join(morning_checkin_missing) if morning_checkin_missing else "无")
    lines.append("")

    # 5. 下午打卡缺勤
    lines.append("5.下午打卡缺勤")
    lines.append('、'.join(afternoon_checkin_missing) if afternoon_checkin_missing else "无")
    lines.append("")

    # 6. 作业缺科情况
    lines.append("6.作业缺科情况")
    if group_incomplete:
        group_order = sorted(group_incomplete.keys(),
                             key=lambda x: chinese_to_arabic(x.rstrip('组')))
        for group in group_order:
            students = group_incomplete[group]
            lines.append(f"{group}：")
            for name, subjects in students.items():
                lines.append(f"  {name} {' '.join(subjects)} 未完成")
    else:
        lines.append("全部完成")
    lines.append("")

    # 7. 请假人员
    lines.append("7.请假人员")
    if leave_stat:
        for group, names in leave_stat.items():
            lines.append(f"{group}：{'、'.join(names)}")
    else:
        lines.append("无请假")
    lines.append("")

    # 8. 小组排名（最优和最差）
    if group_daily_score:
        sorted_groups = sorted(group_daily_score.items(), key=lambda x: (-x[1], x[0]))
        best_group = sorted_groups[0]
        best_score = best_group[1]
        worst_group = sorted_groups[-1]
        worst_score = worst_group[1]
        best_groups = [g for g, s in group_daily_score.items() if s == best_score]
        worst_groups = [g for g, s in group_daily_score.items() if s == worst_score]

        if best_score == 0:
            lines.append(f"  最优小组：{'、'.join(best_groups)}（零违纪）")
        else:
            lines.append(f"  最优小组：{'、'.join(best_groups)}（扣分最少）")
        lines.append(f"  最差小组：{'、'.join(worst_groups)}")
    else:
        lines.append("  暂无小组数据")

    return '\n'.join(lines)
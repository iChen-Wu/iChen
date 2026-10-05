"""小组状态管理"""
def init_daily_group_status(group_map: dict) -> dict:
    groups = set(group_map.values())
    return {g: {"submit_on_time": True, "has_lie_report": False, "lie_students": []} for g in groups}

def mark_group_false_report(group_status: dict, homework_list: list, group_map: dict) -> None:
    for hw in homework_list:
        if hw['is_false_report']:
            name = hw['student_name']
            group = group_map.get(name)
            if group and group in group_status:
                group_status[group]['has_lie_report'] = True
                group_status[group]['lie_students'].append(name)

def mark_group_overdue(group_status: dict, overdue_group_names: list) -> None:
    for g in overdue_group_names:
        if g in group_status:
            group_status[g]['submit_on_time'] = False

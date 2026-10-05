"""统计汇总函数"""
from collections import defaultdict

def stat_morning_overview(ledger: dict, target_date: str) -> dict:
    total = 0
    leave_count = 0
    checkin_count = 0
    not_checkin_list = []
    for name, info in ledger.items():
        for rec in info['records']:
            if rec['date'] == target_date:
                total += 1
                if rec['is_leave']:
                    leave_count += 1
                elif rec['morning_check_in']:
                    checkin_count += 1
                else:
                    not_checkin_list.append(name)
                break
    return {
        'total': total,
        'leave_count': leave_count,
        'checkin_count': checkin_count,
        'not_checkin_list': not_checkin_list
    }

def stat_leave_by_group(ledger: dict, target_date: str, group_map: dict) -> dict:
    leave_stat = defaultdict(list)
    for name, info in ledger.items():
        for rec in info['records']:
            if rec['date'] == target_date and rec['is_leave']:
                group = group_map.get(name, '未分组')
                leave_stat[group].append(name)
                break
    return dict(leave_stat)

def stat_group_submit_status(group_status: dict) -> dict:
    on_time = []
    overdue = []
    lie = []
    for g, status in group_status.items():
        if status['has_lie_report']:
            lie.append(g)
        if not status['submit_on_time']:
            overdue.append(g)
        else:
            on_time.append(g)
    return {
        'on_time_groups': on_time,
        'overdue_groups': overdue,
        'lie_report_groups': lie
    }

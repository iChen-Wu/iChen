"""顶层调度（每日流水线，5项输入，新积分规则）"""
from datetime import date
from GYun.data.client import GyunClient
from BYu.class_manager.summer_score.parser import parse_homework_chain, parse_free_checkin
from BYu.class_manager.summer_score.ledger import (
    load_score_ledger, save_score_ledger,
    get_student_day_record, update_student_ledger,
    load_student_group_map
)
from BYu.class_manager.summer_score.scoring import build_day_record
from BYu.class_manager.summer_score.config import EXEMPT_NAMES
from BYu.class_manager.summer_score.summary import build_evening_summary

def run_daily_pipeline(
    morning_early_text: str,
    morning_late_text: str,
    afternoon_chain_text: str,
    morning_checkin_text: str,
    afternoon_checkin_text: str,
    homework_text: str,
    ledger_client: GyunClient,
    target_date: str = None
) -> str:
    """
    执行每日流水线，6项输入。
    上午接龙拆分为早起/迟到：早起名单+1分，迟到名单-1分，其余不变。
    下午接龙列出【已完成】名单，打卡文本列出【未完成】名单。
    """
    if target_date is None:
        target_date = date.today().isoformat()

    ledger = load_score_ledger(ledger_client)
    group_map = load_student_group_map(ledger_client)
    all_students = list(group_map.keys())
    exempt_set = set(EXEMPT_NAMES)

    # 解析上午接龙（早起/迟到名单）+ 下午接龙（已完成）
    morning_early_set = parse_free_checkin(morning_early_text, all_students)
    morning_late_set = parse_free_checkin(morning_late_text, all_students)
    afternoon_chain_done_set = parse_free_checkin(afternoon_chain_text, all_students)
    # 解析打卡（未完成）
    morning_checkin_missing_set = parse_free_checkin(morning_checkin_text, all_students)
    afternoon_checkin_missing_set = parse_free_checkin(afternoon_checkin_text, all_students)

    # 解析作业接龙
    hw_dict, group_order, appeared_groups = parse_homework_chain(homework_text, target_date, group_map)

    for name in all_students:
        if name in exempt_set:
            mc_early_bonus = 0
            mc_late_deduct = 0
            mc_deduct = 0
            ac_deduct = 0
            mch_deduct = 0
            ach_deduct = 0
            hw_info = hw_dict.get(name, {})
            is_leave = hw_info.get('is_leave', False)
            missing_subjects = hw_info.get('missing_subjects', [])
            if is_leave:
                mc_early_bonus = 0
                mc_late_deduct = 0
                mc_deduct = 0
                ac_deduct = 0
                mch_deduct = 0
                ach_deduct = 0
                missing_subjects = []
        else:
            hw_info = hw_dict.get(name, {})
            is_leave = hw_info.get('is_leave', False)
            missing_subjects = hw_info.get('missing_subjects', [])
            if is_leave:
                mc_early_bonus = 0
                mc_late_deduct = 0
                mc_deduct = 0
                ac_deduct = 0
                mch_deduct = 0
                ach_deduct = 0
                missing_subjects = []
            else:
                # 上午接龙：早起名单+1分，迟到名单-1分，其余不变
                mc_early_bonus = 1 if name in morning_early_set else 0
                mc_late_deduct = 1 if name in morning_late_set else 0
                mc_deduct = 0
                # 下午接龙：在列表中=已完成(扣0)，不在=未完成(扣1)
                ac_deduct = 0 if name in afternoon_chain_done_set else 1
                # 打卡：在列表中=未完成(扣1)，不在=已完成(扣0)
                mch_deduct = 1 if name in morning_checkin_missing_set else 0
                ach_deduct = 1 if name in afternoon_checkin_missing_set else 0

        day_record = build_day_record(
            date=target_date,
            morning_chain_deduct=mc_deduct,
            afternoon_chain_deduct=ac_deduct,
            morning_checkin_deduct=mch_deduct,
            afternoon_checkin_deduct=ach_deduct,
            is_leave=is_leave,
            missing_subjects=missing_subjects,
            morning_early_bonus=mc_early_bonus,
            morning_late_deduct=mc_late_deduct
        )
        # 保留人工作业加分（作业订正结算的"优+1"），避免流水线重建当日记录时被覆盖
        old_rec = get_student_day_record(ledger, name, target_date)
        if old_rec and not day_record.get('is_leave'):
            bonus = old_rec.get('homework_bonus', 0)
            if bonus:
                day_record['homework_bonus'] = bonus
                day_record['final_score'] = day_record.get('final_score', 0) + bonus
        update_student_ledger(ledger, name, day_record)

    save_score_ledger(ledger, ledger_client)

    # ---- 生成晚间总结 ----
    def get_missing(condition_func):
        missing = []
        for name in all_students:
            if name in exempt_set:
                continue
            rec = get_student_day_record(ledger, name, target_date)
            if rec and not rec['is_leave']:
                if condition_func(name):
                    missing.append(name)
        return sorted(missing)

    morning_early_list = get_missing(lambda n: n in morning_early_set)
    morning_late_list = get_missing(lambda n: n in morning_late_set)
    afternoon_chain_missing = get_missing(lambda n: n not in afternoon_chain_done_set)
    morning_checkin_missing = get_missing(lambda n: n in morning_checkin_missing_set)
    afternoon_checkin_missing = get_missing(lambda n: n in afternoon_checkin_missing_set)

    leave_stat = {}
    for name in all_students:
        rec = get_student_day_record(ledger, name, target_date)
        if rec and rec['is_leave']:
            group = group_map.get(name, '未分组')
            leave_stat.setdefault(group, []).append(name)

    # ---- 统计作业缺科（不跳过豁免名单，只跳过请假） ----
    group_incomplete = {}
    for name in all_students:
        rec = get_student_day_record(ledger, name, target_date)
        if rec and not rec['is_leave']:
            group = group_map.get(name, '未分组')
            missing = rec.get('missing_subjects', [])
            if missing:
                group_incomplete.setdefault(group, {})[name] = missing

    group_daily_score = {}
    for name in all_students:
        rec = get_student_day_record(ledger, name, target_date)
        if rec:
            group = group_map.get(name, '未分组')
            group_daily_score[group] = group_daily_score.get(group, 0) + rec['final_score']

    summary = build_evening_summary(
        target_date=target_date,
        morning_early_list=morning_early_list,
        morning_late_list=morning_late_list,
        afternoon_chain_missing=afternoon_chain_missing,
        morning_checkin_missing=morning_checkin_missing,
        afternoon_checkin_missing=afternoon_checkin_missing,
        leave_stat=leave_stat,
        group_incomplete=group_incomplete,
        group_daily_score=group_daily_score
    )
    return summary

def clear_all_ledger_data(client: GyunClient) -> None:
    from BYu.class_manager.summer_score.ledger import _fetch_all_entities
    entities = _fetch_all_entities(client)
    for ent in entities:
        if ent.get('type') in ['student_ledger', 'config']:
            client.delete_entity(ent.get('entity_id'), hard=False)

def export_scores_json(ledger_client: GyunClient, output_path: str) -> None:
    from BYu.class_manager.summer_score.ledger import load_score_ledger
    import json
    ledger = load_score_ledger(ledger_client)
    data = []
    for name, info in ledger.items():
        total = sum(rec['final_score'] for rec in info['records'])
        data.append({"name": name, "score": total})
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已导出 {len(data)} 名学生分数到 {output_path}")
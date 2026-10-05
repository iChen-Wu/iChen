"""积分核算：考勤扣分 + 作业扣分 + 早起加分，所有字段均为整数分值"""
def build_day_record(date: str,
                     morning_chain_deduct: int,
                     afternoon_chain_deduct: int,
                     morning_checkin_deduct: int,
                     afternoon_checkin_deduct: int,
                     is_leave: bool,
                     missing_subjects: list,
                     morning_early_bonus: int = 0,
                     morning_late_deduct: int = 0) -> dict:
    """
    构造日记录
    - 考勤字段：整数扣分值（0=已完成，1=未完成扣1分，5=扣5分等）
    - 上午接龙拆分为早起/迟到：早起+1分（morning_early_bonus），迟到-1分（morning_late_deduct），其余0分
    - 作业扣分 = len(missing_subjects)
    - 最终得分 = -(考勤扣分总和 + 作业扣分总和) + 早起加分
    """
    if is_leave:
        return {
            'date': date,
            'morning_chain_deduct': 0,
            'afternoon_chain_deduct': 0,
            'morning_checkin_deduct': 0,
            'afternoon_checkin_deduct': 0,
            'morning_early_bonus': 0,
            'morning_late_deduct': 0,
            'is_leave': True,
            'missing_subjects': [],
            'attendance_deduct': 0,
            'homework_deduct': 0,
            'final_score': 0
        }

    attendance_deduct = (
        morning_chain_deduct +
        morning_late_deduct +
        afternoon_chain_deduct +
        morning_checkin_deduct +
        afternoon_checkin_deduct
    )
    homework_deduct = len(missing_subjects)
    final_score = -(attendance_deduct + homework_deduct) + morning_early_bonus

    return {
        'date': date,
        'morning_chain_deduct': morning_chain_deduct,
        'afternoon_chain_deduct': afternoon_chain_deduct,
        'morning_checkin_deduct': morning_checkin_deduct,
        'afternoon_checkin_deduct': afternoon_checkin_deduct,
        'morning_early_bonus': morning_early_bonus,
        'morning_late_deduct': morning_late_deduct,
        'is_leave': is_leave,
        'missing_subjects': missing_subjects,
        'attendance_deduct': attendance_deduct,
        'homework_deduct': homework_deduct,
        'final_score': final_score
    }

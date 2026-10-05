"""接龙文本解析（保留原作业解析，新增自由打卡解析）"""
import re
from BYu.class_manager.summer_score.config import SUBJECT_MAP, NAME_LIST, NAME_ALIAS

def _split_subjects(raw: str) -> list[str]:
    """按最长匹配拆分科目字符串，支持多字科目名"""
    subjects = []
    s = raw.strip()
    keys = sorted(SUBJECT_MAP.keys(), key=lambda k: len(k), reverse=True)
    i = 0
    while i < len(s):
        matched = False
        for key in keys:
            if s.startswith(key, i):
                subj = SUBJECT_MAP[key]
                if subj not in subjects:
                    subjects.append(subj)
                i += len(key)
                matched = True
                break
        if not matched:
            i += 1
    return subjects

def parse_homework_chain(raw_text: str, target_date: str, group_map: dict) -> tuple[dict, dict, set]:
    """
    解析作业接龙（格式固定）
    返回: (hw_dict, group_order, appeared_groups)
    """
    lines = raw_text.split('\n')
    entries = []
    pattern = re.compile(r'^\d+\.\s*(.+)$')
    for line in lines:
        line = line.strip()
        m = pattern.match(line)
        if m:
            entries.append(m.group(1).strip())

    student_records = {}
    for name, group in group_map.items():
        student_records[name] = {
            'student_name': name,
            'date': target_date,
            'group': group,
            'is_leave': False,
            'missing_subjects': [],
            'has_bracket': False,
            'appeared': False,
            'raw_line': ''
        }

    group_order = {}
    appeared_groups = set()

    for entry in entries:
        group_match = re.match(r'^([一二三四五六七八九]组)\s*(.*)$', entry)
        if not group_match:
            continue
        group_name = group_match.group(1)
        appeared_groups.add(group_name)
        rest = group_match.group(2).strip()

        group_students = []

        if rest == '全部完成':
            for name, g in group_map.items():
                if g == group_name:
                    student_records[name]['appeared'] = True
                    student_records[name]['has_bracket'] = True
                    student_records[name]['missing_subjects'] = []
                    if name not in group_students:
                        group_students.append(name)
        else:
            normalized = rest.replace('(', '（').replace(')', '）')
            parts = re.findall(r'([\u4e00-\u9fa5]+)\s*（\s*([^）]*?)\s*）|([\u4e00-\u9fa5]+)', normalized)
            for match in parts:
                name = match[0] or match[2]
                bracket = match[1] if match[1] else None
                if not name:
                    continue
                # 别名映射
                if name in NAME_ALIAS:
                    name = NAME_ALIAS[name]
                if name not in student_records:
                    continue
                if name not in group_students:
                    group_students.append(name)

                student_records[name]['appeared'] = True

                if bracket is not None:
                    student_records[name]['has_bracket'] = True
                    content = bracket.strip()
                    if content in ('假', '请假'):
                        student_records[name]['is_leave'] = True
                        student_records[name]['missing_subjects'] = []
                    else:
                        missing = _split_subjects(content)
                        student_records[name]['missing_subjects'] = missing
                else:
                    # 无括号：has_bracket=False，missing为空
                    pass

        if group_name not in group_order:
            group_order[group_name] = []
        for name in group_students:
            if name not in group_order[group_name]:
                group_order[group_name].append(name)

    # 后处理：组内复制缺科
    for group, ordered_names in group_order.items():
        last_valid = None
        for name in reversed(ordered_names):
            if name not in student_records:
                continue
            info = student_records[name]
            if info['is_leave']:
                continue
            if info['has_bracket']:
                last_valid = info
                break
        if last_valid:
            default_missing = last_valid['missing_subjects']
            for name in ordered_names:
                if name not in student_records:
                    continue
                info = student_records[name]
                if info['is_leave']:
                    continue
                if not info['has_bracket']:
                    info['has_bracket'] = True
                    info['missing_subjects'] = default_missing.copy()

    hw_dict = {}
    for name, rec in student_records.items():
        hw_dict[name] = {
            'student_name': name,
            'date': target_date,
            'is_leave': rec['is_leave'],
            'missing_subjects': rec['missing_subjects'],
            'has_bracket': rec['has_bracket'],
            'appeared': rec['appeared']
        }
    return hw_dict, group_order, appeared_groups

def clean_student_name(raw: str, student_list: list) -> str | None:
    """清洗姓名：去除数字、空格、家长后缀，并尝试匹配"""
    cleaned = re.sub(r'[\d\s]+', '', raw)
    for suffix in ['妈妈', '爸爸', '爷爷', '奶奶', '同学', '家长']:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    if cleaned in student_list:
        return cleaned
    for name in student_list:
        if name in raw:
            return name
    return None

def parse_free_checkin(raw_text: str, student_list: list) -> set:
    """
    解析自由格式的打卡/接龙文本，提取标准名单中的人名
    支持分隔符：中文逗号、英文逗号、顿号、空格、换行、数字序号
    支持家长后缀（妈妈、爸爸等）
    """
    lines = raw_text.split('\n')
    all_parts = []
    for line in lines:
        # 移除行首的数字序号 (如 "1. ", "2、")
        line = re.sub(r'^\d+[\.、\s]+', '', line.strip())
        # 移除行尾的电话号码（纯数字）
        line = re.sub(r'\d{7,15}$', '', line.strip())
        if line:
            # 再按分隔符切分
            parts = re.split(r'[，,、\s]+', line)
            all_parts.extend(parts)

    result = set()
    for part in all_parts:
        part = part.strip()
        if not part:
            continue
        # 精确匹配
        if part in student_list:
            result.add(part)
            continue
        # 使用 clean_student_name 清洗（处理家长后缀）
        cleaned = clean_student_name(part, student_list)
        if cleaned:
            result.add(cleaned)
    return result
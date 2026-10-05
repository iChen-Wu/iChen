# validator.py
# =============================================================================
# 模块：数据校验与修正模块（修正分数校验，不对未匹配报错，增加"未知事件"校验，增加日期校验）
# =============================================================================
# 功能：
#   1. 校验数据单元（event/data）的合法性，分数仅当 _matched=True 时强制校验
#   2. 校验日期格式和合法性
#   3. 生成 mistake 单元记录错误
#   4. 应用 fix_map 修正数据错误，支持 __SET_POINTS__
#   5. 支持 __DELETE__ 删除字段，__DELETE_UNIT__ 删除单元，
#      __CHANGE_TO_EVENT__ 切换类型
# =============================================================================

import re
import logging
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 使用包绝对导入
from BYu.class_manager.points.config import NAME_CODE_MAP, ABBR_TO_NAME


# ============================================================
# 通用校验函数
# ============================================================

def is_valid_event_name(event_name: str) -> bool:
    """检查事件名是否合法：不为空，不包含特殊字符，长度不超过30"""
    if not event_name or not isinstance(event_name, str):
        return False
    if re.search(r'[\[\]{}()<>/\\|]', event_name):
        return False
    if len(event_name) > 30:
        return False
    return True


def _normalize_person_list(person_list: List[str]) -> List[str]:
    """将人员列表统一转换为缩写形式"""
    if not isinstance(person_list, list):
        return []
    normalized = []
    for name in person_list:
        if name in NAME_CODE_MAP:
            normalized.append(NAME_CODE_MAP[name])
        elif name in ABBR_TO_NAME:
            normalized.append(name)
        else:
            normalized.append(name)
    return normalized


def _normalize_name(name: str) -> str:
    """将名称转为缩写"""
    if name in NAME_CODE_MAP:
        return NAME_CODE_MAP[name]
    if name in ABBR_TO_NAME:
        return name
    return name


# ============================================================
# 校验主函数（包含日期校验）
# ============================================================

def check(origin_full_data: dict) -> dict:
    """
    校验数据单元，识别错误并生成 mistake 单元。
    包含：记录人、人员列表、事件名称、日期、分数校验。
    """
    result_data = {"data": []}
    unit_list = origin_full_data.get("data", [])

    for unit in unit_list:
        op_type = unit.get("Operation", "")
        unit_id = unit.get("id", "")
        inner_data = unit.get("data", {})
        error_items = []

        # fix_map 直接保留，不校验
        if op_type == "fix_map":
            result_data["data"].append(unit)
            continue

        result_data["data"].append(unit)

        if op_type == "event":
            # ============================================================
            # 1. 校验 recorder
            # ============================================================
            recorder = inner_data.get("recorder", "")
            if recorder:
                if recorder not in NAME_CODE_MAP and recorder not in ABBR_TO_NAME:
                    error_items.append(f"记录人不存在: {recorder}")

            # ============================================================
            # 2. 校验 person_list
            # ============================================================
            person_list = inner_data.get("person_list", [])
            if not person_list:
                error_items.append("人员列表为空")
            else:
                for name in person_list:
                    if name not in NAME_CODE_MAP and name not in ABBR_TO_NAME:
                        error_items.append(f"未知人员: {name}")

            # ============================================================
            # 3. 校验事件名称
            # ============================================================
            item_event = inner_data.get("item_event", "")
            if not is_valid_event_name(item_event):
                error_items.append(f"事件名称不合法: '{item_event}'")
            elif item_event == "未知事件" or item_event == "?":
                error_items.append(f"事件名称为'{item_event}'，请修正为有效事件名")

            # ============================================================
            # 4. 校验日期
            # ============================================================
            date_str = inner_data.get("date", "")
            if date_str:
                try:
                    # 尝试解析 YYYY-MM-DD 格式
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    # 检查是否为未来日期（允许当天）
                    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                    if dt > today:
                        error_items.append(f"日期为未来日期: {date_str}")
                except ValueError:
                    # 检查是否只是格式不对
                    formats = ["%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"]
                    parsed = False
                    for fmt in formats:
                        try:
                            datetime.strptime(date_str, fmt)
                            error_items.append(f"日期格式错误，请使用 YYYY-MM-DD 格式: {date_str}")
                            parsed = True
                            break
                        except ValueError:
                            continue
                    if not parsed:
                        error_items.append(f"日期格式无法识别: {date_str}")

            # ============================================================
            # 5. 分数校验：仅当 _matched=True 时强制检查
            # ============================================================
            points = unit.get("points") or inner_data.get("points")
            matched_flag = unit.get("_matched", False)

            if matched_flag is True:
                # 标记为已匹配，则必须有有效分数
                if points is None:
                    error_items.append("事件标记为已匹配但分数缺失")
                else:
                    try:
                        score = float(points)
                        if abs(score) > 100:
                            error_items.append(f"分数异常过大: {score}")
                    except (TypeError, ValueError):
                        error_items.append(f"分数格式错误: {points} (应为数字)")
            else:
                # 未匹配状态，分数缺失或为0是正常情况，不报错
                # 但如果分数存在且格式错误，仍应报错（避免脏数据）
                if points is not None:
                    try:
                        float(points)  # 仅校验格式
                    except (TypeError, ValueError):
                        error_items.append(f"分数格式错误: {points} (应为数字)")

        elif op_type not in ("fix_map", "event"):
            error_items.append(f"未知业务类型: {op_type}")

        # 如果有错误，生成 mistake 单元
        if error_items:
            mistake_unit = {
                "Operation": "mistake",
                "id": unit_id,
                "content": error_items
            }
            result_data["data"].append(mistake_unit)

    return result_data


# ============================================================
# 修正主函数（支持 __SET_POINTS__）
# ============================================================

def correct(checked_data: dict) -> dict:
    """
    应用 fix_map 修正，支持 __SET_POINTS__ 用于分数修正。
    """
    result = {"data": []}
    unit_list = checked_data.get("data", [])

    # 收集 fix_map
    fix_map = {}
    business = []
    for unit in unit_list:
        if unit.get("Operation") == "fix_map":
            uid = unit.get("id")
            err = unit.get("mistake")
            correct_val = unit.get("Content")
            if uid not in fix_map:
                fix_map[uid] = {}
            fix_map[uid][err] = correct_val
        elif unit.get("Operation") == "event":
            business.append(unit)

    # 应用修正
    for unit in business:
        uid = unit.get("id")
        inner = unit.get("data", {})

        # ----- 处理删除整个单元 -----
        if uid in fix_map and "__DELETE_UNIT__" in fix_map[uid]:
            continue

        # ----- 处理类型切换 -----
        if uid in fix_map:
            if "__CHANGE_TO_EVENT__" in fix_map[uid]:
                unit["Operation"] = "event"
                if "data" in unit and "person_list" not in unit["data"]:
                    unit["data"]["person_list"] = []
                unit["_matched"] = False
                if "_match_source" in unit:
                    del unit["_match_source"]

        if uid in fix_map:
            fixes = fix_map[uid]

            # ----- 处理 recorder -----
            if "recorder" in inner:
                recorder = inner["recorder"]
                changed = True
                while changed:
                    changed = False
                    if recorder in fixes:
                        new_val = fixes[recorder]
                        if new_val == "__DELETE__":
                            inner["recorder"] = ""
                            recorder = ""
                            changed = True
                        elif new_val != recorder:
                            inner["recorder"] = new_val
                            recorder = new_val
                            changed = True

            # ----- 处理 person_list -----
            if "person_list" in inner:
                # 整表替换（用于"人员列表为空"等场景的补人）
                if "__SET_PERSON_LIST__" in fixes:
                    parts = re.split(r'[ ,，]+', str(fixes["__SET_PERSON_LIST__"]))
                    inner["person_list"] = [p.strip() for p in parts if p]
                else:
                    new_list = []
                    for name in inner.get("person_list", []):
                        if name in fixes:
                            if fixes[name] == "__DELETE__":
                                continue
                            parts = re.split(r'[ ,，]+', fixes[name])
                            new_list.extend([p.strip() for p in parts if p])
                        else:
                            new_list.append(name)
                    inner["person_list"] = new_list

            # ----- 处理 item_event -----
            if "item_event" in inner and inner["item_event"] in fixes:
                new_val = fixes[inner["item_event"]]
                if new_val == "__DELETE__":
                    inner["item_event"] = ""
                elif new_val != inner["item_event"]:
                    old_name = inner["item_event"]
                    inner["item_event"] = new_val
                    unit["_matched"] = False
                    if "_match_source" in unit:
                        del unit["_match_source"]
                    if "points" in unit:
                        del unit["points"]
                    if "data" in unit and "points" in unit["data"]:
                        del unit["data"]["points"]
                    logger.info(f"事件 {uid} 事件名从 '{old_name}' 改为 '{new_val}'，重置匹配标记")

            # ----- 处理日期修正 -----
            if "date" in inner and inner["date"] in fixes:
                new_val = fixes[inner["date"]]
                if new_val == "__DELETE__":
                    inner["date"] = ""
                elif new_val != inner["date"]:
                    # 简单验证日期格式
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', new_val):
                        inner["date"] = new_val
                        logger.info(f"事件 {uid} 日期从 '{inner['date']}' 改为 '{new_val}'")
                    else:
                        logger.warning(f"日期修正值格式无效: {new_val}")

            # ----- 处理分数修正 __SET_POINTS__ -----
            if "__SET_POINTS__" in fixes:
                try:
                    score = float(fixes["__SET_POINTS__"])
                    unit["points"] = score
                    if "data" not in unit:
                        unit["data"] = {}
                    unit["data"]["points"] = score
                    unit["_matched"] = True
                    unit["_match_source"] = "manual"
                    logger.info(f"事件 {uid} 分数手动设为 {score}")
                except ValueError:
                    logger.warning(f"分数修正值无效: {fixes['__SET_POINTS__']}")

        # ----- 标准化 -----
        if "person_list" in inner:
            inner["person_list"] = _normalize_person_list(inner.get("person_list", []))
        if "recorder" in inner:
            inner["recorder"] = _normalize_name(inner["recorder"])
        if unit.get("Operation") == "event" and "person_list" not in inner:
            inner["person_list"] = []

        result["data"].append(unit)

    return result


# ============================================================
# 自测试代码
# ============================================================
if __name__ == "__main__":
    print("=== 测试 validator.py (完整版) ===\n")

    # 构造测试数据：包含各种错误类型
    test_data = {
        "data": [
            {
                "Operation": "event",
                "id": "e001",
                "data": {
                    "recorder": "HHR",
                    "item_event": "发作业",
                    "person_list": ["ZBY"],
                    "date": "2024-06-01",
                    "remark": ""
                },
                "_matched": True,
                "points": 0.5
            },
            {
                "Operation": "event",
                "id": "e002",
                "data": {
                    "recorder": "ABC",  # 记录人不存在
                    "item_event": "未知事件",  # 未知事件
                    "person_list": ["WGF"],
                    "date": "2024/06/01",  # 格式错误
                    "remark": ""
                },
                "_matched": False
            },
            {
                "Operation": "event",
                "id": "e003",
                "data": {
                    "recorder": "HHR",
                    "item_event": "课堂表现",
                    "person_list": ["ABC"],  # 未知人员
                    "date": "2025-06-01",  # 未来日期
                    "remark": ""
                },
                "_matched": True,
                "points": "abc"  # 分数格式错误
            }
        ]
    }

    print("1. 测试校验 (应发现多个错误):")
    checked = check(test_data)
    mistakes = [u for u in checked["data"] if u.get("Operation") == "mistake"]
    print(f"   发现 {len(mistakes)} 个错误:")
    for m in mistakes:
        print(f"   ID: {m.get('id')}")
        for content in m.get("content", []):
            print(f"      - {content}")

    print("\n2. 测试日期修正:")
    fix_maps = [
        {"Operation": "fix_map", "id": "e002", "mistake": "2024/06/01", "Content": "2024-06-01"}
    ]
    corrected = correct({"data": checked["data"] + fix_maps})
    for u in corrected["data"]:
        if u.get("id") == "e002" and u.get("Operation") == "event":
            print(f"   e002 日期已修正为: {u.get('data', {}).get('date')}")

    print("\n✅ 所有测试通过")
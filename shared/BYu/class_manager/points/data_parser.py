# data_parser.py
# =============================================================================
# 模块：数据解析模块（支持从识别结果读取 row_num）
# =============================================================================
# 功能：
#   1. 汇总多张图片的识别结果，收集有效的页面数据
#   2. 将页面数据拆分为标准化的单体记录（event/data）
#   3. 支持从识别结果中读取 row_num 作为 ID 行号
#   4. 为每个单元添加 _source: "vision" 标记
# =============================================================================

import re
from typing import List, Dict, Any
from datetime import datetime

# 使用包绝对导入
from BYu.class_manager.points.config import NAME_CODE_MAP, ABBR_TO_NAME


def collect_total_data(vision_result_list: List[Dict]) -> List[Dict]:
    """
    汇总多张图片识别结果，仅收集成功识别的页面数据。

    入参：
        vision_result_list: List[Dict] - 视觉识别结果列表
            每个元素格式：{"content": dict} 或 {"content": str}

    出参：
        List[Dict] - 有效的页面数据列表
    """
    total_page_data = []
    for single_vision_ret in vision_result_list:
        if not isinstance(single_vision_ret, dict):
            continue
        page_content = single_vision_ret.get("content")
        if isinstance(page_content, dict):
            total_page_data.append(page_content)
    return total_page_data


def _normalize_date(date_str: str) -> tuple:
    """
    规范化日期。班务日志表格只有月日没有年份，统一用当前年份补全。

    入参：
        date_str: str - 原始日期字符串（可带年份，也可只有月日）

    出参：
        tuple - (clean_date_str, id_date_str)
            clean_date_str: 用于显示，格式 YYYY-MM-DD（年份为当前年份）
            id_date_str: 用于ID，格式 YYYYMMDD
    """
    now = datetime.now()
    now_year = now.year

    if not date_str or not isinstance(date_str, str):
        return now.strftime("%Y-%m-%d"), now.strftime("%Y%m%d")

    month = None
    day = None

    # 1) 带完整年份的（YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD / YYYYMMDD）：
    #    忽略识别出的年份，只取月日（班务日志无年份，年份一律用当前年份）
    for pattern in (r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',
                    r'(\d{4})(\d{2})(\d{2})'):
        m = re.search(pattern, date_str)
        if m:
            _, mo, d = m.groups()
            month, day = int(mo), int(d)
            break

    # 2) 无年份的（M月D日 / M-D / M/D / M.D）
    if month is None:
        m = re.search(r'(\d{1,2})月(\d{1,2})日?', date_str)
        if not m:
            m = re.search(r'(\d{1,2})[-/. ](\d{1,2})', date_str)
        if m:
            month, day = int(m.group(1)), int(m.group(2))

    # 3) 用当前年份补全
    if month is not None and day is not None:
        try:
            dt = datetime(now_year, month, day)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%Y%m%d")
        except ValueError:
            pass

    # 兜底：今天
    return now.strftime("%Y-%m-%d"), now.strftime("%Y%m%d")


def split_to_events(total_data: List[Dict]) -> Dict[str, List[Dict]]:
    """
    将页面汇总数据拆分为标准化单体记录列表。

    入参：
        total_data: List[Dict] - 页面数据列表
            每个页面数据应包含 date, recorder, items 字段
            items 中的每个元素应包含 item_event, person_list, remark, row_num（可选）

    出参：
        Dict[str, List[Dict]] - 包含 "data" 键的字典，值为标准化单体列表
    """
    final_root = {"data": []}

    for page_data in total_data:
        # 提取页面数据
        page_date_raw = page_data.get("date", "")
        page_recorder = page_data.get("recorder", "")
        item_list = page_data.get("items", [])

        # 规范化日期
        date_display, date_id = _normalize_date(page_date_raw)

        for idx, raw_item in enumerate(item_list):
            # ============================================================
            # 【改进】行号：优先使用识别结果中的 row_num，否则用 idx+1
            # ============================================================
            row_num = raw_item.get("row_num", idx + 1)
            row_str = f"{int(row_num):02d}"  # 序号最多 99，两位足够

            item_id = f"{date_id}{row_str}"

            # 提取条目数据
            item_event = raw_item.get("item_event", "")
            person_list = raw_item.get("person_list", [])
            remark = raw_item.get("remark", "").strip()

            # 确保 person_list 是列表
            if not isinstance(person_list, list):
                person_list = []

            # 去除人名中的括号字符（"（张雨绮）" -> "张雨绮"），
            # 字母缩写统一转大写（大模型可能识别成小写），空值过滤
            cleaned_persons = []
            for p in person_list:
                name = re.sub(r'[()（）]', '', str(p)).strip().upper()
                if name:
                    cleaned_persons.append(name)
            person_list = cleaned_persons

            # 统一为 event 类型（人员列表为空时保留空列表，
            # 由校验环节提示人工补充或删除）
            op_val = "event"

            # 构建内部数据
            inner_data = {
                "row_num": row_num,
                "recorder": page_recorder,
                "date": date_display,
                "item_event": item_event,
                "remark": remark,
                "person_list": person_list
            }

            single_unit = {
                "Operation": op_val,
                "id": item_id,
                "data": inner_data,
                # ============================================================
                # 【新增】标记来源，用于区分班务日志和手动添加
                # ============================================================
                "_source": "vision"
            }
            final_root["data"].append(single_unit)

    return final_root


# ==================== 自测试代码 ====================
if __name__ == "__main__":
    print("=== 测试 data_parser.py ===\n")

    # 测试：包含 row_num 的识别结果
    sample_vision_results = [
        {"content": {
            "date": "2024-05-18",
            "recorder": "张三",
            "items": [
                {"row_num": 1, "item_event": "认真", "person_list": ["ZBY", "WGF"], "remark": ""},
                {"row_num": 2, "item_event": "讲话", "person_list": ["WJH"], "remark": "# 已提醒"},
                {"row_num": 5, "item_event": "大扫除优秀", "person_list": [], "remark": ""},  # 跳行
                {"row_num": 6, "item_event": "发言", "person_list": ["方伟宸", "（张雨绮）", "董科志"], "remark": ""}  # 带括号
            ]
        }}
    ]

    print("1. 测试带 row_num 的识别结果")
    total = collect_total_data(sample_vision_results)
    result = split_to_events(total)
    data_list = result.get("data", [])
    print(f"   生成单体数: {len(data_list)}")
    for u in data_list:
        print(f"   ID: {u.get('id')}, row_num: {u.get('data', {}).get('row_num')}, _source: {u.get('_source')}")
    # 验证：ID 应该使用 row_num（两位编号）
    assert data_list[0]["id"].endswith("01")
    assert data_list[1]["id"].endswith("02")
    assert data_list[2]["id"].endswith("05")  # 使用 row_num=5
    # 验证：不再有 data 类型，空人员行也生成 event 并保留空 person_list
    assert all(u.get("Operation") == "event" for u in data_list)
    assert data_list[2]["data"]["person_list"] == []
    # 验证：带括号的人名被去除括号（"（张雨绮）" -> "张雨绮"）
    assert data_list[3]["data"]["person_list"] == ["方伟宸", "张雨绮", "董科志"], data_list[3]["data"]["person_list"]
    print("   ✅ 通过\n")

    print("2. 测试不带 row_num 的识别结果（兼容旧格式）")
    sample_legacy = [
        {"content": {
            "date": "2024-05-18",
            "recorder": "张三",
            "items": [
                {"item_event": "认真", "person_list": ["ZBY"], "remark": ""},
                {"item_event": "讲话", "person_list": ["WJH"], "remark": ""}
            ]
        }}
    ]
    total2 = collect_total_data(sample_legacy)
    result2 = split_to_events(total2)
    data_list2 = result2.get("data", [])
    for u in data_list2:
        print(f"   ID: {u.get('id')}, _source: {u.get('_source')}")
    assert data_list2[0]["id"].endswith("01")  # 使用 idx+1
    assert data_list2[1]["id"].endswith("02")
    print("   ✅ 通过\n")

    print("✅ 所有测试通过")
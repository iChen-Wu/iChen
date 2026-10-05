# matcher.py
# =============================================================================
# 模块：分数匹配与人员修正模块（新增 AI 人员模糊匹配）
# =============================================================================
# 功能：
#   1. 首先进行人员修正：将识别错误的名字通过 AI 匹配到正确的学生缩写
#   2. 然后进行分数匹配：remark提取 → 本地配置 → AI批量匹配
#   3. 支持增量匹配，已匹配的跳过
#   4. 匹配后标记 _matched=True，记录匹配来源
#   5. 修正：AI 匹配后同时设置 matched 和 _matched，确保状态一致
# =============================================================================

import json
import re
import logging
from typing import Dict, List, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 使用包绝对导入
from BYu.class_manager.points.config import EVENT_SCORE_CFG, NAME_CODE_MAP, ABBR_TO_NAME

# 导入 AI 客户端
try:
    from GYun.LLM import chat
    logger.info("成功导入 GYun.LLM.chat")
except ImportError as e:
    chat = None
    logger.warning(f"无法导入 GYun.LLM.chat: {e}，AI 匹配功能不可用")


# ============================================================
# 原有辅助函数
# ============================================================

def _parse_remark_to_points(remark: str) -> Optional[float]:
    if not isinstance(remark, str) or not remark.strip():
        return None
    pattern = r"[-+]?\d+(?:\.\d+)?"
    match_res = re.search(pattern, remark)
    if not match_res:
        return None
    try:
        return float(match_res.group())
    except ValueError:
        return None


def _match_by_local_config(event_name: str) -> Optional[float]:
    score = EVENT_SCORE_CFG.get(event_name)
    if score is not None:
        return float(score)
    return None


# ============================================================
# 新增 AI 人员修正函数（包含完整姓名映射）
# ============================================================

def _batch_ai_correct_names(suspect_names: set, verbose: bool = False) -> dict:
    """
    批量修正可疑名字，通过 AI 匹配到最接近的学生缩写。
    支持中文全名和错误缩写。

    入参：
        suspect_names: set - 可疑名字集合（可能是全名或错误缩写）
        verbose: bool - 是否打印调试信息

    出参：
        dict - 映射 {原名字: 修正后的缩写}，若无法修正则保留原名字
    """
    if not suspect_names:
        return {}

    if chat is None:
        logger.warning("AI 客户端不可用，无法进行人员修正")
        return {name: name for name in suspect_names}

    # 构建姓名映射描述（全名 -> 缩写）
    name_mapping = {}
    for full_name, code in NAME_CODE_MAP.items():
        name_mapping[full_name] = code
    # 也包括缩写到全名的映射，让 AI 知道缩写对应谁
    name_mapping.update({code: full_name for code, full_name in ABBR_TO_NAME.items()})

    # 构建提示词
    suspect_list = list(suspect_names)
    prompt = f"""
你是学生姓名纠错助手。现有学生姓名对照表（格式：全名 -> 缩写）：
{json.dumps(name_mapping, ensure_ascii=False, indent=2)}

以下是识别出的可疑名字列表（可能是学生的缩写、全名、或识别错误的字符串）：
{suspect_list}

任务：
- 为每个可疑名字匹配最接近的学生**缩写**（即姓名代码，通常为3-4位大写字母）。
- 如果某个名字明显无法匹配（如明显不是学生姓名），则保留原样。
- 输出必须是一个纯 JSON 对象，键为原名字，值为匹配到的缩写（或原名字本身）。

示例：
输入可疑名字：["ZBY1", "张博宇", "WGF"]
输出：{{"ZBY1": "ZBY", "张博宇": "ZBY", "WGF": "WGF"}}

请严格按照上述格式输出，不要有任何额外文字。
"""
    if verbose:
        print("\n[AI人员修正] 请求 Prompt:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)

    try:
        resp = chat(prompt, model="glm")
        raw_content = resp.content if hasattr(resp, 'content') else str(resp)

        if verbose:
            print("[AI人员修正] 原始返回:")
            print("-" * 50)
            print(raw_content)
            print("-" * 50)

        # 提取 JSON
        clean_content = raw_content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_content = '\n'.join(lines).strip()

        mapping = json.loads(clean_content)

        # 验证映射是否有效
        valid_mapping = {}
        for original, corrected in mapping.items():
            # 如果修正后的值在 ABBR_TO_NAME 中，说明是有效缩写
            if corrected in ABBR_TO_NAME:
                valid_mapping[original] = corrected
            elif corrected in NAME_CODE_MAP:
                # 可能是全名，反向查找缩写
                valid_mapping[original] = NAME_CODE_MAP[corrected]
            else:
                # 无法匹配，保留原样
                logger.warning(f"AI 返回的修正值无效: {original} -> {corrected}，保留原样")
                valid_mapping[original] = original

        logger.info(f"人员修正完成，共处理 {len(suspect_names)} 个可疑名字，修正 {len([v for v in valid_mapping.values() if v != original])} 个")
        return valid_mapping

    except json.JSONDecodeError as e:
        logger.error(f"AI 人员修正 JSON 解析失败: {e}")
        if verbose:
            print(f"[AI人员修正错误] JSON解析失败: {e}")
        return {name: name for name in suspect_names}
    except Exception as e:
        logger.error(f"AI 人员修正异常: {e}", exc_info=True)
        if verbose:
            print(f"[AI人员修正错误] {e}")
        return {name: name for name in suspect_names}


# ============================================================
# 分数匹配 AI 函数（保持不变）
# ============================================================

def _batch_ai_query(fail_list: list, verbose: bool = False) -> list:
    if not fail_list:
        return fail_list

    if chat is None:
        logger.warning("AI 客户端不可用，跳过 AI 匹配")
        for item in fail_list:
            item["points"] = 0.0
            item["matched"] = True
            item["_matched"] = True
            item["_match_source"] = "ai_unavailable"
        return fail_list

    query_items = [
        {
            "id": item.get("id", ""),
            "item_event": item.get("item_event", "")
        }
        for item in fail_list
    ]

    prompt = f"""
根据以下学生积分规则配置，为每个事件匹配分数。

规则：
{json.dumps(EVENT_SCORE_CFG, ensure_ascii=False, indent=2)}

待匹配事件列表（JSON数组）：
{json.dumps(query_items, ensure_ascii=False)}

要求：
- 严格按已有规则匹配；规则中没有的事件，根据校园常规奖惩逻辑给出合理分数（可正可负，支持小数）。
- 输出必须是纯 JSON 对象，格式严格如下，不要有任何额外文字、注释、代码块标记：
{{"result": [{{"id": "事件id", "points": 分数}}, ...]}}
- 分数必须是数字（整数或小数），不要加引号。
- 如果某个事件确实无法判断，给 points 设为 0。
"""

    if verbose:
        print("\n[AI请求] 发送给大模型的 prompt:")
        print("-" * 50)
        print(prompt)
        print("-" * 50)

    try:
        resp = chat(prompt, model="glm")
        raw_content = resp.content if hasattr(resp, 'content') else str(resp)

        if verbose:
            print("[AI响应] 原始返回内容:")
            print("-" * 50)
            print(raw_content)
            print("-" * 50)

        clean_content = raw_content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.split('\n')
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_content = '\n'.join(lines).strip()

        if verbose:
            print("[AI响应] 清理后 JSON 字符串:")
            print("-" * 50)
            print(clean_content)
            print("-" * 50)

        ai_result = json.loads(clean_content)
        result_list = ai_result.get("result", [])

        id_to_score = {}
        for res in result_list:
            if "id" in res and "points" in res:
                try:
                    points = float(res["points"])
                    if abs(points) > 100:
                        logger.warning(f"AI 返回的分数过大: {res['id']} -> {points}，限制为 ±100")
                        points = max(-100, min(100, points))
                    id_to_score[res["id"]] = points
                except (TypeError, ValueError):
                    logger.warning(f"AI 返回的分数无效: {res.get('id')} -> {res.get('points')}")

        for item in fail_list:
            item_id = item.get("id")
            if item_id in id_to_score:
                item["points"] = id_to_score[item_id]
                item["matched"] = True
                item["_matched"] = True
                item["_match_source"] = "ai"
                logger.debug(f"AI 匹配成功: {item_id} -> {id_to_score[item_id]}")
            else:
                logger.warning(f"AI 未返回 {item_id} 的分数，设为 0")
                item["points"] = 0.0
                item["matched"] = True
                item["_matched"] = True
                item["_match_source"] = "ai_default"

        return fail_list

    except json.JSONDecodeError as e:
        logger.error(f"AI 返回的 JSON 解析失败: {e}")
        if verbose:
            print(f"[AI错误] JSON解析失败: {e}")
        for item in fail_list:
            item["points"] = 0.0
            item["matched"] = True
            item["_matched"] = True
            item["_match_source"] = "ai_error"
        return fail_list

    except Exception as e:
        logger.error(f"AI 调用异常: {e}", exc_info=True)
        if verbose:
            print(f"[AI错误] {e}")
        for item in fail_list:
            item["points"] = 0.0
            item["matched"] = True
            item["_matched"] = True
            item["_match_source"] = "ai_error"
        return fail_list


# ============================================================
# 主匹配函数（整合人员修正）
# ============================================================

def match(input_data: dict) -> dict:
    """
    分数匹配主入口 - 先修正人员，再匹配分数。
    """
    def _gen_mistake_unit(unit_id: str, event_name: str) -> dict:
        return {
            "Operation": "mistake",
            "id": unit_id,
            "content": [f"事件 '{event_name}' 未匹配到有效分数"]
        }

    origin_units = input_data.get("data", [])
    if not origin_units:
        return {"data": []}

    # ============================================================
    # 第一步：人员修正（识别所有不在映射中的名字，用 AI 修正）
    # ============================================================
    all_names = set()
    for unit in origin_units:
        if unit.get("Operation") == "event":
            inner = unit.get("data", {})
            person_list = inner.get("person_list", [])
            if not person_list:
                person_list = unit.get("person_list", [])
            all_names.update(person_list)

    all_names = {n for n in all_names if n}

    # 找出所有不在映射中的名字（无论是中文全名还是错误缩写）
    suspect_names = set()
    for name in all_names:
        if name not in NAME_CODE_MAP and name not in ABBR_TO_NAME:
            suspect_names.add(name)

    if suspect_names:
        logger.info(f"发现 {len(suspect_names)} 个可疑名字，尝试 AI 修正: {suspect_names}")
        correction_mapping = _batch_ai_correct_names(suspect_names, verbose=False)
        # 应用修正到所有事件
        for unit in origin_units:
            if unit.get("Operation") == "event":
                inner = unit.get("data", {})
                person_list = inner.get("person_list", [])
                if not person_list:
                    person_list = unit.get("person_list", [])
                corrected_list = []
                for name in person_list:
                    if name in correction_mapping:
                        new_name = correction_mapping[name]
                        if new_name != name:
                            logger.info(f"修正名字: {name} -> {new_name}")
                        corrected_list.append(new_name)
                    else:
                        corrected_list.append(name)
                if "data" in unit and "person_list" in unit["data"]:
                    unit["data"]["person_list"] = corrected_list
                elif "person_list" in unit:
                    unit["person_list"] = corrected_list
                else:
                    if "data" not in unit:
                        unit["data"] = {}
                    unit["data"]["person_list"] = corrected_list
                unit["_name_corrected"] = True
    else:
        logger.info("没有可疑名字，跳过人员修正")

    # ============================================================
    # 第二步：分数匹配（原有逻辑）
    # ============================================================
    output_list = []
    event_status = []
    need_ai = []

    for unit in origin_units:
        op_type = unit.get("Operation")
        if op_type != "event":
            output_list.append(unit)
            continue

        unit_id = unit.get("id", "")
        inner_data = unit.get("data", {})
        item_event = inner_data.get("item_event", "")
        person_list = inner_data.get("person_list", [])
        remark = inner_data.get("remark", "")

        if unit.get("_matched") is True or unit.get("matched") is True:
            output_list.append(unit)
            logger.debug(f"事件 {unit_id} 已匹配，跳过")
            continue

        existing_points = unit.get("points") or inner_data.get("points")
        if existing_points is not None:
            try:
                points = float(existing_points)
                unit["_matched"] = True
                unit["matched"] = True
                unit["_match_source"] = "manual"
                output_list.append(unit)
                logger.debug(f"事件 {unit_id} 已有手动分数 {points}")
                continue
            except (TypeError, ValueError):
                pass

        event_status.append({
            "unit": unit,
            "id": unit_id,
            "item_event": item_event,
            "person_list": person_list,
            "remark": remark,
            "points": None,
            "matched": False,
            "_matched": False
        })

    if not event_status:
        logger.info("所有事件已匹配，无需调用 AI")
        return {"data": output_list}

    for status in event_status:
        score = _parse_remark_to_points(status["remark"])
        if score is not None:
            status["points"] = score
            status["matched"] = True
            status["_matched"] = True
            status["match_source"] = "remark"
            logger.debug(f"从 remark 提取分数: {status['item_event']} -> {score}")
            continue

        cfg_score = _match_by_local_config(status["item_event"])
        if cfg_score is not None:
            status["points"] = cfg_score
            status["matched"] = True
            status["_matched"] = True
            status["match_source"] = "config"
            logger.debug(f"本地配置匹配: {status['item_event']} -> {cfg_score}")
            continue

        need_ai.append(status)
        logger.debug(f"加入 AI 队列: {status['item_event']}")

    if need_ai:
        logger.info(f"需要 AI 匹配 {len(need_ai)} 个事件")
        _batch_ai_query(need_ai, verbose=False)

    for status in event_status:
        unit = status["unit"]

        if not status.get("matched", False):
            logger.warning(f"事件 {status['id']} 匹配状态异常，强制设为已匹配，分数 0")
            status["points"] = 0.0
            status["matched"] = True
            status["_matched"] = True
            status["match_source"] = "force"

        if status["matched"] and status["points"] is not None:
            points_val = float(status["points"])
            unit["points"] = points_val
            unit["_matched"] = True
            unit["matched"] = True
            unit["_match_source"] = status.get("match_source", "unknown")

            if "data" in unit:
                unit["data"]["points"] = points_val

            output_list.append(unit)
        else:
            output_list.append(_gen_mistake_unit(status["id"], status["item_event"]))

    matched_count = sum(1 for u in output_list if u.get("_matched") is True or u.get("matched") is True)
    logger.info(f"匹配完成: {matched_count} 个事件已匹配")

    return {"data": output_list}


# ============================================================
# 自测试代码
# ============================================================
if __name__ == "__main__":
    print("=== 测试 matcher.py (含人员修正) ===\n")
    test_data = {
        "data": [
            {
                "Operation": "event",
                "id": "e001",
                "data": {
                    "recorder": "HHR",
                    "item_event": "发作业",
                    "person_list": ["伊相嘉"],  # 中文全名
                    "remark": ""
                }
            },
            {
                "Operation": "event",
                "id": "e002",
                "data": {
                    "recorder": "HHR",
                    "item_event": "课堂表现",
                    "person_list": ["CS"],  # 错误缩写
                    "remark": ""
                }
            }
        ]
    }
    print("输入数据:")
    print(json.dumps(test_data, ensure_ascii=False, indent=2))
    result = match(test_data)
    print("\n输出数据:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n✅ 测试完成")
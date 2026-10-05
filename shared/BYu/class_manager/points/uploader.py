# uploader.py
# =============================================================================
# 模块：积分汇总与上传模块（事件名附加短ID）
# =============================================================================
# 功能：
#   1. 将事件列表转换为 scmAPI.set_points 需要的格式
#   2. 调用 scmAPI.set_points 上传
#   3. 返回上传结果
#
# 入参/出参说明：
#   update(calc_data: dict) -> dict
#       入参：包含 "data" 键的字典，值为数据单元列表（event 类型）
#       出参：scmAPI.set_points 的返回结果
#
#   set_points 接口格式：
#       入参：[{"names": ["姓名"], "event": "事件名", "points": 分数}, ...]
#       出参：{"code": 0, "message": "...", "data": {...}}
# =============================================================================

import json
import logging
import re
from typing import Dict, List, Any, Optional

# 配置日志
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 使用包绝对导入
from BYu.class_manager.points.config import NAME_CODE_MAP, ABBR_TO_NAME

# 导入 scmAPI（可能不存在，用 try 防御）
try:
    from GYun.scmAPI import set_points
    logger.info("成功导入 GYun.scmAPI.set_points")
except ImportError as e:
    set_points = None
    logger.warning(f"无法导入 GYun.scmAPI.set_points: {e}，上传功能不可用")


def _normalize_name(name: str) -> Optional[str]:
    """将名称转为全名，支持缩写和全名输入"""
    if not name:
        return None
    if name in NAME_CODE_MAP:
        return name
    if name in ABBR_TO_NAME:
        return ABBR_TO_NAME[name]
    return None


def _extract_short_id(event_id: str) -> str:
    """
    从完整ID中提取短ID（去掉年份，保留月日+序号）
    例如 "20240601001" -> "0601001"
    """
    if not event_id:
        return ""
    # 匹配格式：4位年份 + 月日 + 2位序号
    match = re.match(r'^(\d{4})(\d{4}\d{2})$', event_id)
    if match:
        return match.group(2)  # 返回去掉年份的部分
    # 如果已经是短ID格式，直接返回
    return event_id


def update(calc_data: dict) -> dict:
    """
    将事件列表转换为 set_points 格式并上传。
    事件名后附加短ID（去掉年份）。
    """
    data_list = calc_data.get("data", [])

    if not data_list:
        logger.warning("没有数据需要上传")
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": "没有数据",
            "error": "没有数据",
            "api_response": None
        }

    if set_points is None:
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": "scmAPI.set_points 未导入",
            "error": "scmAPI.set_points 未导入，请检查依赖",
            "api_response": None
        }

    # 检查是否有 mistake 单元
    mistake_units = [u for u in data_list if u.get("Operation") == "mistake"]
    if mistake_units:
        mistake_details = []
        for mu in mistake_units:
            mistake_details.append({
                "id": mu.get("id", "unknown"),
                "content": mu.get("content", [])
            })
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": f"存在 {len(mistake_units)} 个未修复的错误数据",
            "error": f"存在 {len(mistake_units)} 个未修复的错误数据",
            "error_detail": mistake_details,
            "api_response": None
        }

    # ============================================================
    # 转换为 set_points 格式，事件名附加短ID
    # ============================================================
    events_data = []

    for unit in data_list:
        if unit.get("Operation") != "event":
            continue

        # 提取事件信息（支持两种格式）
        if "item_event" in unit and "person_list" in unit and "points" in unit:
            # 扁平格式
            item_event = unit.get("item_event", "")
            person_list = unit.get("person_list", [])
            points = unit.get("points", 0.0)
            event_id = unit.get("id", "")
        elif unit.get("data") and isinstance(unit.get("data"), dict):
            # 嵌套格式
            inner = unit.get("data", {})
            item_event = inner.get("item_event", "")
            person_list = inner.get("person_list", [])
            points = inner.get("points", 0.0)
            event_id = unit.get("id", "")
        else:
            continue

        # 转换人员列表：缩写 -> 全名
        names = []
        for name in person_list:
            full_name = _normalize_name(name)
            if full_name:
                names.append(full_name)

        if not names:
            continue

        # 确保 points 是 float
        try:
            points = float(points)
        except (TypeError, ValueError):
            continue

        # ============================================================
        # 【修改】事件名附加短ID（去掉年份）
        # ============================================================
        short_id = _extract_short_id(event_id)
        if short_id:
            event_with_id = f"{item_event}"
        else:
            event_with_id = item_event

        events_data.append({
            "names": names,
            "event": event_with_id,
            "points": points
        })

    if not events_data:
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": "没有有效的事件数据",
            "error": "没有有效的事件数据",
            "api_response": None
        }

    # ============================================================
    # 打印上传数据（调试用）
    # ============================================================
    print("\n" + "=" * 60)
    print("【上传数据】即将发送给 scmAPI.set_points：")
    print("=" * 60)
    print(json.dumps(events_data, ensure_ascii=False, indent=2))
    print("=" * 60 + "\n")

    # ============================================================
    # 调用 set_points
    # ============================================================
    try:
        logger.info(f"调用 scmAPI.set_points，共 {len(events_data)} 个事件")
        api_result = set_points(events_data)

        print("\n" + "=" * 60)
        print("【API 返回】scmAPI.set_points 返回结果：")
        print("=" * 60)
        print(json.dumps(api_result, ensure_ascii=False, indent=2) if api_result else str(api_result))
        print("=" * 60 + "\n")

        # ============================================================
        # 适配新格式：{"code": 0, "message": "...", "data": {...}}
        # ============================================================
        if api_result is None:
            return {
                "upload_success": False,
                "upload_count": 0,
                "message": "API 返回 None",
                "error": "API 返回 None",
                "api_response": None
            }

        # ✅ 新格式：有 code 字段
        if isinstance(api_result, dict) and "code" in api_result:
            if api_result.get("code") == 0:
                data = api_result.get("data", {})
                upload_count = data.get("updated_count", len(events_data))
                logger.info(f"✅ 上传成功: {api_result.get('message')}")
                return {
                    "upload_success": True,
                    "upload_count": upload_count,
                    "message": api_result.get("message", "上传成功"),
                    "api_response": api_result,
                    "data": data
                }
            else:
                logger.error(f"❌ 上传失败: {api_result.get('message')}")
                return {
                    "upload_success": False,
                    "upload_count": 0,
                    "message": api_result.get("message", "API 返回错误"),
                    "error": api_result.get("message", "API 返回错误"),
                    "api_response": api_result
                }

        # ✅ 旧格式兼容：有 success 字段
        if isinstance(api_result, dict) and "success" in api_result:
            if api_result.get("success"):
                return {
                    "upload_success": True,
                    "upload_count": len(events_data),
                    "message": api_result.get("message", "上传成功"),
                    "api_response": api_result
                }
            else:
                return {
                    "upload_success": False,
                    "upload_count": 0,
                    "message": api_result.get("message", "API 返回失败"),
                    "error": api_result.get("message", "API 返回失败"),
                    "api_response": api_result
                }

        # ✅ 空字典视为成功（兼容旧版）
        if isinstance(api_result, dict) and not api_result:
            logger.warning("API 返回空字典，视为成功（兼容旧版）")
            return {
                "upload_success": True,
                "upload_count": len(events_data),
                "message": "上传成功（API返回空）",
                "api_response": api_result
            }

        # ✅ 有数据就算成功
        if api_result:
            return {
                "upload_success": True,
                "upload_count": len(events_data),
                "message": "上传成功",
                "api_response": api_result
            }

        # ✅ 默认：失败
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": "未知响应格式",
            "error": "未知响应格式",
            "api_response": api_result
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"scmAPI.set_points 调用异常: {error_msg}", exc_info=True)
        return {
            "upload_success": False,
            "upload_count": 0,
            "message": f"调用异常: {error_msg}",
            "error": f"scmAPI.set_points 调用异常: {error_msg}",
            "api_response": None,
            "error_detail": {
                "exception_type": type(e).__name__,
                "exception_message": error_msg
            }
        }


# ==================== 自测试代码 ====================
if __name__ == "__main__":
    print("=== 测试 uploader.py ===")
    # 测试短ID提取
    test_ids = ["20240601001", "20240615010", "20241231005"]
    for tid in test_ids:
        short = _extract_short_id(tid)
        print(f"{tid} -> {short}")
    print("✅ 测试完成")
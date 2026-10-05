# vision.py
# =============================================================================
# 模块：图片识别适配层（基于 GYun.LLM 视觉模型，不再依赖 GYun.vision）
# =============================================================================
# 功能：
#   1. 调用 GYun.LLM.chat_with_image 识别图片，默认模型 Qwen3-VL-8B-Instruct
#   2. 内置识别类型 prompt（班务日志），类型可扩展
#   3. 从 LLM 返回文本提取 JSON，统一为 {"content": dict} / {"content": str}
#
# 入参/出参说明：
#   vision(image_arg: str, type: str = "班务日志", print_raw: bool = False,
#          model: str = None) -> dict
#       入参：
#           image_arg: str - 图片路径或 base64 字符串
#           type: str - 识别类型，默认 "班务日志"
#           print_raw: bool - 是否打印 LLM 原始返回
#           model: str - 模型名，默认 siliconflow/Qwen/Qwen3-VL-8B-Instruct
#       出参：
#           成功：{"content": dict}
#           失败：{"content": str}
#
#   list_types() -> list[str]
#       列出所有可用的识别类型
# =============================================================================

import os
import re
import json
import base64
import logging

from GYun.LLM import chat_with_image

logger = logging.getLogger(__name__)

# ============================================================
# 默认视觉模型（Qwen3-VL-8B-Instruct，经硅基流动 SiliconFlow 调用）
# ============================================================
DEFAULT_MODEL = "siliconflow/Qwen/Qwen3-VL-8B-Instruct"

# ============================================================
# 识别类型 -> 提示词
# ============================================================
PROMPTS = {
    "班务日志": (
        "请从图片中的班务日志表格提取信息，仅返回标准JSON，不要额外文字。\n"
        "输出必须包含 \"items\" 数组，即使没有识别到任何区块也要输出 \"items\": []。\n"
        "\n"
        "【表格结构】\n"
        "- A列：事件名称（前 1~11 行为预填事件，12~22 行为空待填）\n"
        "- B列：序号（1~22）\n"
        "- C~F列：学生姓名区（事件当事人，可能填了 1~4 个姓名，姓名间没有分隔线，需要逐个识别）\n"
        "- G列：备注（可空）\n"
        "- 页面顶部有记录人（可能是姓名，也可能是数字编号）\n"
        "\n"
        "【输出格式】\n"
        "{\n"
        "  \"date\": \"MM-DD（表格只有月日没有年份，如 08-01，程序会用当前年份补全）\",\n"
        "  \"recorder\": \"记录人（姓名或数字编号）\",\n"
        "  \"items\": [\n"
        "    {\n"
        "      \"row_num\": 对应B列序号,\n"
        "      \"item_event\": \"对应A列事件名称\",\n"
        "      \"person_list\": [\"学生1\", \"学生2\", ...],\n"
        "      \"remark\": \"对应G列备注，没有则为空字符串\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "\n"
        "【识别要点】\n"
        "1. row_num 直接对齐 B 列序号（1~22），不要重新编号\n"
        "2. item_event 对齐 A 列事件名称，如：讲话、早读认真、发作业、迟到、大扫除优秀等\n"
        "3. person_list 从 C~F 区域提取所有学生姓名（可能 1~4 个，全部列出，一个都不能漏）；"
        "姓名可能是中文也可能是 3-4 位大写字母缩写（如 ZBY、WJH）；"
        "姓名带括号也原样输出（如 \"（张雨绮）\"），程序会自动去除括号\n"
        "4. remark 从 G 列提取，没有则为空字符串\n"
        "5. recorder 原样输出，可能是姓名也可能是数字编号\n"
        "6. 事件行若确实没有填写任何学生，person_list 输出空数组 []\n"
        "7. 只输出有内容的行；空行、看不清的行直接跳过\n"
        "8. 日期只有月日没有年份，输出 MM-DD 格式（如 08-01）\n"
        "\n"
        "请严格按照以上格式输出JSON，确保 items 数组包含所有识别到的区块。"
    ),
    "修改单": (
        "请从图片中的积分修改单逐行提取编辑指令，仅返回标准JSON，不要额外文字。\n"
        "输出格式必须为：{\"lines\": [\"原始行1\", \"原始行2\", ...]}\n"
        "保持每行的原始写法，不要改写、不要合并、不要拆分。\n"
        "\n"
        "修改单每行的格式（日期为8位数字，如 20260809）：\n"
        "1. 新增事件：日期+编号(从22开始)+A+<事件><人员逗号分隔><备注可选>\n"
        "   如 2026080923A<积极><ZBY,CWXC><+1>\n"
        "2. 给原事件加人：日期+原编号+A+<人员>\n"
        "   如 2026073112A<ZBY>\n"
        "3. 删除整个事件：日期+原编号+D+<事件>\n"
        "   如 2026073112D<事件>\n"
        "4. 删除人员：日期+原编号+D+<人员逗号分隔>\n"
        "   如 2026073112D<ZBY,CWXC>\n"
        "5. 修改事件或分数：日期+原编号+C+<事件/分数><内容>\n"
        "   如 2026073112C<事件><积极> 或 2026073112C<分数><+1>\n"
        "\n"
        "要求：\n"
        "- 逐行识别，人员缩写通常为 3-4 位大写字母（如 ZBY、WGF），也可能是中文姓名\n"
        "- 人员带括号也原样输出（如 <（张雨绮）,方伟宸>），程序会自动去除括号\n"
        "- 只输出有内容的行；空行、看不清的行直接跳过，不要输出\n"
        "- 无法看清的行直接跳过，不要编造\n"
        "- 如果图片中没有修改单内容，输出 {\"lines\": []}\n"
        "请严格按照以上格式输出JSON。"
    ),
}


def list_types() -> list:
    """列出所有可用的识别类型"""
    return list(PROMPTS.keys())


def _get_prompt(type: str) -> str:
    """获取指定识别类型的提示词"""
    prompt = PROMPTS.get(type)
    if not prompt:
        raise ValueError(f"未找到识别类型: {type}，可用类型: {list_types()}")
    return prompt


# ============================================================
# 工具函数（内联，避免依赖 GYun.vision）
# ============================================================

def _load_image(data: str) -> str:
    """加载图片并转换为 base64（支持路径或 base64 字符串）"""
    if not data or not str(data).strip():
        raise ValueError("图片数据不能为空")

    data = str(data).strip()

    # 文件路径 -> base64
    if os.path.isfile(data):
        try:
            with open(data, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            raise ValueError(f"读取图片文件失败: {e}")

    # 视为 base64 字符串，简单校验
    if not all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in data):
        raise ValueError("传入字符串不是有效的 Base64 编码，且不是存在的文件路径")
    return data


def _extract_json(text: str) -> dict:
    """从 LLM 返回文本中提取 JSON 对象"""
    text = text.strip()

    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # markdown 代码块
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("无法从响应中提取 JSON，请检查大模型返回内容")


# ============================================================
# 识别主函数
# ============================================================

def vision(image_arg: str, type: str = "班务日志", print_raw: bool = False,
           model: str = None) -> dict:
    """
    图片识别（GYun.LLM 视觉模型）。

    入参：
        image_arg: 图片路径或 base64 字符串
        type: 识别类型，默认 "班务日志"
        print_raw: 是否打印 LLM 原始返回
        model: 模型名，默认 siliconflow/Qwen/Qwen3-VL-8B-Instruct

    出参：
        dict - {"content": dict} 或 {"content": str}
    """
    try:
        prompt = _get_prompt(type)
    except ValueError as e:
        return {"content": str(e)}

    # 图片 -> base64
    try:
        img_b64 = _load_image(image_arg)
    except ValueError as e:
        return {"content": str(e)}

    # 调用 GYun.LLM 视觉模型
    model_name = model or DEFAULT_MODEL
    try:
        resp = chat_with_image(prompt, img_b64, model=model_name, timeout=360)
        raw_text = resp.content if hasattr(resp, 'content') else str(resp)

        if print_raw:
            print("\n" + "=" * 60)
            print(f"[DEBUG] GYun.LLM 识别返回 (model={model_name}, type={type}):")
            print("=" * 60)
            print(raw_text)
            print("=" * 60 + "\n")

        result = _extract_json(raw_text)
        return {"content": result}
    except ValueError as e:
        logger.error(f"识别 JSON 解析失败: {e}")
        return {"content": f"识别解析失败: {e}"}
    except Exception as e:
        logger.error(f"识别异常: {e}", exc_info=True)
        return {"content": f"识别异常: {str(e)}"}


# ==================== 自测试 ====================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("=== 测试 vision.py (GYun.LLM 识别) ===")
    print("=" * 60)

    print(f"\n默认模型: {DEFAULT_MODEL}")
    print(f"可用识别类型: {list_types()}")

    test_path = input("\n请输入图片路径（回车跳过）: ").strip()
    if test_path and os.path.exists(test_path):
        result = vision(test_path, type="班务日志", print_raw=True)
        if isinstance(result.get("content"), dict):
            print(f"\n✅ 识别成功，data 字段: {list(result['content'].keys())}")
        else:
            print(f"\n❌ 失败: {result.get('content')}")
    else:
        print("跳过测试")

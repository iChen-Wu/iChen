"""
通用工具：数据格式转换、步骤校验、日志辅助
"""
from typing import Dict, List


def entity_to_flow(entity: Dict) -> Dict:
    """将 GYun.Data 实体转换为标准流程格式"""
    return {
        "flow_name": entity["title"],
        "steps": entity["extra"].get("steps", [])
    }


def flow_to_entity_data(flow_name: str, steps: List[Dict], source: str = "manual") -> Dict:
    """将标准流程转换为 GYun.Data 可入库的实体数据"""
    return {
        "type": "auto_click_flow",
        "title": flow_name,
        "tags": [source, "自动化流程"],
        "extra": {
            "steps": steps,
            "source": source
        }
    }


def validate_step(step: Dict) -> bool:
    """校验单步必填字段，返回是否合法"""
    if "type" not in step:
        return False
    step_type = step["type"]

    if step_type == "pixel":
        action = step.get("action", "left_click")
        if action == "drag":
            return all(k in step for k in ["start_x", "start_y", "end_x", "end_y"])
        if action == "scroll":
            return "delta" in step
        return "x" in step and "y" in step

    if step_type == "sleep":
        return "duration" in step

    if step_type == "func":
        return "func_name" in step

    if step_type in ("image", "ocr"):
        return True

    return False


def print_step_log(index: int, step: Dict, status: str = "执行中"):
    """统一打印步骤日志"""
    name = step.get("name", f"步骤{index}")
    print(f"[{index}] {name} [{step['type']}] - {status}")
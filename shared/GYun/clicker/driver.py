"""
流程执行器
从 GYun.Data 加载流程，按顺序执行所有步骤
支持 pixel / sleep / func 三类操作，image/ocr 预留占位
"""
import time
from typing import Dict, List
from GYun.data.client import GyunClient
from GYun.clicker import mouse
from GYun.clicker import actions
from GYun.clicker.utils import entity_to_flow, validate_step, print_step_log
from GYun.clicker.visual.image_click import ImageClick
from GYun.clicker.visual.ocr_click import OcrClick


class ClickDriver:
    def __init__(self):
        self.data_client = GyunClient()
        self.image_click = ImageClick()
        self.ocr_click = None  # 需外部传入 OCR 配置后启用

    def run_flow_by_name(self, flow_title: str):
        """按名称从数据库查询流程并执行"""
        result = self.data_client.query_entities({
            "type": "auto_click_flow",
            "keyword_title": flow_title
        })
        if not result["list"]:
            raise ValueError(f"未找到流程：{flow_title}")

        flow = entity_to_flow(result["list"][0])
        self.run_flow(flow)

    def run_flow(self, flow: Dict):
        """执行单条完整流程"""
        flow_name = flow["flow_name"]
        steps = flow["steps"]
        print(f"\n===== 开始执行流程：{flow_name} =====")
        print(f"共 {len(steps)} 步\n")

        for idx, step in enumerate(steps, 1):
            if not validate_step(step):
                print_step_log(idx, step, "跳过：字段不合法")
                continue

            # 前置等待
            wait_before = step.get("wait_before", 0)
            if wait_before > 0:
                time.sleep(wait_before)

            print_step_log(idx, step)
            try:
                self._run_step(step)
                print_step_log(idx, step, "完成")
            except Exception as e:
                print_step_log(idx, step, f"失败：{str(e)}")

        print(f"\n===== 流程 {flow_name} 执行结束 =====\n")

    def _run_step(self, step: Dict):
        """单步执行分发"""
        step_type = step["type"]

        if step_type == "pixel":
            self._run_pixel(step)
        elif step_type == "sleep":
            time.sleep(step["duration"])
        elif step_type == "func":
            self._run_func(step)
        elif step_type == "image":
            self.image_click.click_by_template(
                step.get("template", ""),
                confidence=step.get("confidence", 0.8)
            )
        elif step_type == "ocr":
            if not self.ocr_click:
                raise NotImplementedError("OCR 功能未配置，暂不可用")
            self.ocr_click.click_by_text(
                step.get("text", ""),
                match_mode=step.get("match_mode", "contain")
            )
        else:
            raise ValueError(f"未知操作类型：{step_type}")

    def _run_pixel(self, step: Dict):
        """执行像素级鼠标操作，支持重试"""
        action = step.get("action", "left_click")
        retry = step.get("retry", 1)
        duration = step.get("duration", 0.1)

        last_error = None
        for _ in range(retry):
            try:
                if action == "left_click":
                    mouse.left_click(step["x"], step["y"], clicks=step.get("clicks", 1), duration=duration)
                elif action == "right_click":
                    mouse.right_click(step["x"], step["y"], duration=duration)
                elif action == "double_click":
                    mouse.double_click(step["x"], step["y"], duration=duration)
                elif action == "move":
                    mouse.move_to(step["x"], step["y"], duration=duration)
                elif action == "drag":
                    mouse.drag(step["start_x"], step["start_y"], step["end_x"], step["end_y"], duration=duration)
                elif action == "scroll":
                    mouse.scroll(step["delta"])
                else:
                    raise ValueError(f"未知鼠标动作：{action}")
                return
            except Exception as e:
                last_error = e
                time.sleep(0.2)
        raise last_error

    def _run_func(self, step: Dict):
        """执行自定义函数，支持 args 传参"""
        func_name = step["func_name"]
        args = step.get("args", {})

        if not hasattr(actions, func_name):
            raise AttributeError(f"actions.py 中不存在函数：{func_name}")

        func = getattr(actions, func_name)
        func(**args)

    def close(self):
        """关闭数据库连接"""
        self.data_client.close()
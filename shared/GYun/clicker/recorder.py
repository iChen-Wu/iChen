"""
FlowCapture 操作录制器
快捷键：
  F1 - 记录左键点击
  F2 - 记录右键点击
  F3 - 插入自定义函数占位（录制结束后回填）
  ESC - 结束录制，自动存入 GYun.Data
"""
import time
import json
from pynput import keyboard
from GYun.data.client import GyunClient
from GYun.clicker import mouse
from GYun.clicker import actions
from GYun.clicker.utils import flow_to_entity_data


class FlowCapture:
    def __init__(self, flow_name: str):
        self.flow_name = flow_name
        self.steps = []
        self.last_time = None
        self.client = GyunClient()
        self.listener = None

    def start(self):
        """启动录制，阻塞主线程"""
        print(f"===== FlowCapture 录制启动 =====")
        print(f"流程名称：{self.flow_name}")
        print("F1=记录左键 | F2=记录右键 | F3=插入函数 | ESC=结束保存")
        print("================================\n")

        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        )
        self.listener.start()
        self.listener.join()

    def _on_press(self, key):
        try:
            if key == keyboard.Key.f1:
                self._record_click("left_click")
            elif key == keyboard.Key.f2:
                self._record_click("right_click")
            elif key == keyboard.Key.f3:
                self._insert_func_placeholder()
        except Exception as e:
            print(f"录制异常：{e}")

    def _on_release(self, key):
        if key == keyboard.Key.esc:
            self._finish_recording()
            return False  # 停止监听

    def _record_click(self, action: str):
        """记录鼠标点击步骤"""
        x, y = mouse.get_position()
        now = time.time()
        wait_before = round(now - self.last_time, 3) if self.last_time else 0.0
        self.last_time = now

        step = {
            "type": "pixel",
            "action": action,
            "x": x,
            "y": y,
            "wait_before": wait_before
        }
        self.steps.append(step)
        print(f"✅ 已记录 #{len(self.steps)} ({x},{y}) {action} 前置等待:{wait_before}s")

    def _insert_func_placeholder(self):
        """插入自定义函数占位步骤"""
        step = {
            "type": "func",
            "func_name": "TO_FILL",
            "args": {}
        }
        self.steps.append(step)
        print(f"⚠️  已插入函数占位步骤 #{len(self.steps)}，结束录制后填写")
        # 插入函数也更新时间，避免后续点击等待时间计算错误
        self.last_time = time.time()

    def _finish_recording(self):
        """结束录制，回填函数，保存入库"""
        print("\n===== 录制结束，开始处理 =====")
        print(f"共记录 {len(self.steps)} 步")

        # 回填函数
        self._fill_func_steps()

        # 保存到数据库
        entity_id = self._save_to_db()

        print(f"\n🎉 流程「{self.flow_name}」已保存到数据库")
        print(f"实体ID：{entity_id}")
        self.client.close()

    def _fill_func_steps(self):
        """交互式回填所有占位函数"""
        placeholders = [i for i, s in enumerate(self.steps) if s.get("func_name") == "TO_FILL"]
        if not placeholders:
            return

        print(f"\n发现 {len(placeholders)} 个待填充函数步骤，按顺序填写：")
        for idx, step_idx in enumerate(placeholders, 1):
            print(f"\n--- 第 {idx} 个函数（步骤 #{step_idx + 1}）---")
            func_name = input("请输入函数名（直接回车删除该步骤）：").strip()

            if not func_name:
                del self.steps[step_idx]
                print("已删除该步骤")
                continue

            if not hasattr(actions, func_name):
                print(f"⚠️  警告：actions.py 中未找到函数 {func_name}，仍将保存")

            args_str = input("请输入参数字典（JSON格式，无参数直接回车）：").strip()
            args = {}
            if args_str:
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    print("⚠️  JSON 格式错误，参数置空")

            self.steps[step_idx]["func_name"] = func_name
            self.steps[step_idx]["args"] = args
            print(f"已填充：{func_name} {args}")

    def _save_to_db(self) -> str:
        """保存流程到 GYun.Data"""
        entity_data = flow_to_entity_data(
            flow_name=self.flow_name,
            steps=self.steps,
            source="flow_capture"
        )
        return self.client.create_entity(entity_data)
"""
GYun.Clicker 自动化点击与录制模块
- ClickDriver：流程执行器
- FlowCapture：操作录制器
"""

from GYun.clicker.driver import ClickDriver
from GYun.clicker.recorder import FlowCapture

__all__ = ["ClickDriver", "FlowCapture"]
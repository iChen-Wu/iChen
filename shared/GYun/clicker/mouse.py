"""
底层像素级鼠标操作封装
所有屏幕鼠标操作统一通过此模块执行，上层不直接依赖 pyautogui
"""
import pyautogui

# 全局安全设置：鼠标移到左上角可强制中断
pyautogui.FAILSAFE = True
# 默认操作间隔，防止过快
pyautogui.PAUSE = 0.05


def left_click(x: int, y: int, clicks: int = 1, duration: float = 0.1):
    """左键单击/连击"""
    pyautogui.click(x, y, clicks=clicks, duration=duration)


def right_click(x: int, y: int, duration: float = 0.1):
    """右键单击"""
    pyautogui.rightClick(x, y, duration=duration)


def double_click(x: int, y: int, duration: float = 0.1):
    """左键双击"""
    pyautogui.doubleClick(x, y, duration=duration)


def move_to(x: int, y: int, duration: float = 0.2):
    """仅移动鼠标，不点击"""
    pyautogui.moveTo(x, y, duration=duration)


def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
    """按住左键从起点拖拽到终点"""
    pyautogui.moveTo(start_x, start_y)
    pyautogui.dragTo(end_x, end_y, duration=duration, button="left")


def scroll(delta: int):
    """滚轮滚动，正数向上，负数向下"""
    pyautogui.scroll(delta)


def get_position():
    """获取当前鼠标坐标"""
    return pyautogui.position()
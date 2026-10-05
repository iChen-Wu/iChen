"""
可被流程调用的自定义动作函数库
json 流程中 func 类型的 func_name 对应此处函数名
新增动作只需在此文件添加函数，无需修改执行器
"""
import time
import pyautogui
from GYun.data.client import GyunClient
pyautogui.FAILSAFE = True



def refresh_data_cache(full_scan: bool = False):
    """刷新数据中枢缓存"""
    client = GyunClient()
    print(f"执行数据缓存刷新，全量扫描: {full_scan}")
    # 可在此补充实际缓存逻辑
    client.close()


def sleep_custom(duration: float = 1.0):
    """自定义等待，比 sleep 步骤更灵活"""
    time.sleep(duration)
    print(f"自定义等待 {duration}s 完成")


def switch_window(title_keyword: str):
    """切换到包含指定关键词的窗口"""
    try:
        import pygetwindow as gw
        wins = gw.getWindowsWithTitle(title_keyword)
        if wins:
            wins[0].activate()
            print(f"已切换到窗口: {wins[0].title}")
        else:
            print(f"未找到包含关键词的窗口: {title_keyword}")
    except ImportError:
        print("未安装 pygetwindow，无法切换窗口")


def print_message(message: str = "执行完成"):
    """打印提示信息，用于调试流程"""
    print(f"[流程提示] {message}")

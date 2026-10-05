"""时间工具，统一毫秒时间戳"""
import time

def get_current_ms() -> int:
    return int(time.time() * 1000)

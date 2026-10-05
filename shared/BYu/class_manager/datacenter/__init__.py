"""
数据中心 - 班级通用数据管理

提供对班级管理范围内所有数据的增删改查能力，
不绑定具体业务类型（积分、歌单、值日表等通用）。
"""

from .service import DataCenterService
from .cli import main

__all__ = ["DataCenterService", "main"]
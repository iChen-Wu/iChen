# -*- coding: utf-8 -*-
"""
百屿系统 - 班级管理核心模块
========================================
本模块提供班级管理全流程功能：
1. 班务日志自动解析
2. 学生积分批量计算与上传
3. 数据校验、异常处理、结果反馈

统一对外接口：
- update_points: 班务日志积分上传核心处理函数

使用方式：
    from src.BYu.class_manager import update_points
"""

__version__ = "1.0.0"
__author__ = "百屿系统"
__status__ = "Production"


def update_points(*args, **kwargs):
    """延迟导入，仅在调用时加载 points 模块"""
    from .points import update_points as _update_points
    return _update_points(*args, **kwargs)


__all__ = [
    "update_points",
    "__version__",
    "__author__"
]
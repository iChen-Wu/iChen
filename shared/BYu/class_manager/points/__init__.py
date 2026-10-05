# points/__init__.py
import sys
import os

# 将项目根目录添加到 sys.path
_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .points_core import update_points
__all__ = ["update_points"]
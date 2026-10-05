"""生命周期钩子管理器"""
import threading
from collections import defaultdict
from typing import Callable, Dict, Any
from GYun.data.utils.exceptions import HookReentryError

class HookManager:
    def __init__(self):
        self._hooks = defaultdict(list)
        self._local = threading.local()

    def register(self, hook_type: str, func: Callable):
        valid_types = ['before_create', 'after_create',
                       'before_update', 'after_update',
                       'before_delete', 'after_delete']
        if hook_type not in valid_types:
            raise ValueError(f"无效钩子类型: {hook_type}")
        self._hooks[hook_type].append(func)

    def run_before(self, action: str, data: Any) -> Any:
        hook_type = f'before_{action}'
        if self._check_reentry(hook_type):
            raise HookReentryError(f"钩子 {hook_type} 重入检测")
        self._set_reentry(hook_type, True)
        try:
            for func in self._hooks.get(hook_type, []):
                data = func(data)
            return data
        finally:
            self._set_reentry(hook_type, False)

    def run_after(self, action: str, data: Any):
        hook_type = f'after_{action}'
        if self._check_reentry(hook_type):
            raise HookReentryError(f"钩子 {hook_type} 重入检测")
        self._set_reentry(hook_type, True)
        try:
            for func in self._hooks.get(hook_type, []):
                func(data)
        finally:
            self._set_reentry(hook_type, False)

    def _check_reentry(self, hook_type: str) -> bool:
        if not hasattr(self._local, 'reentry'):
            self._local.reentry = set()
        return hook_type in self._local.reentry

    def _set_reentry(self, hook_type: str, value: bool):
        if not hasattr(self._local, 'reentry'):
            self._local.reentry = set()
        if value:
            self._local.reentry.add(hook_type)
        else:
            self._local.reentry.discard(hook_type)

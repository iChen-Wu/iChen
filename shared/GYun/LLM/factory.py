import importlib
import threading
from GYun.LLM._config import get_config
from GYun.LLM.base import BaseAdapter

class ModelFactory:
    _instances = {}
    _lock = threading.RLock()

    @classmethod
    def get_adapter(cls, model_name: str) -> BaseAdapter:
        with cls._lock:
            if model_name in cls._instances: return cls._instances[model_name]
            config = get_config()
            module_path, class_name, real_model = config.get_model_info(model_name)
            module = importlib.import_module(f"GYun.LLM.{module_path}")
            adapter = getattr(module, class_name)(real_model)
            cls._instances[model_name] = adapter
            return adapter

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            for adapter in cls._instances.values():
                try:
                    if hasattr(adapter, 'close'):
                        adapter.close()
                except Exception:
                    pass
            cls._instances.clear()
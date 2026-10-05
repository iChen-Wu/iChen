"""设置模块：系统信息 / 本地配置持久化（控制台 → 设置）

- get_system_info    系统信息（版本 + 服务状态摘要）
- get_local_config   读取本地配置（data/local_config.json）
- save_local_config  保存本地配置（与原配置合并，不覆盖其它键）
"""
import json
from pathlib import Path

from system.kernel.base import APP_VERSION

try:
    from common.paths import DATA_DIR
except Exception:  # 极端情况下退回相对定位
    DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

CONFIG_FILE = DATA_DIR / "local_config.json"


class SettingsMixin:
    def get_system_info(self) -> dict:
        """系统信息：版本 + App 总数。

        V3.0.0 · P4 起，「服务」类别已废除——原服务改为 App，
        中枢不再提供服务状态摘要；运行中的 App 实例由「后台」面板展示。
        """
        return {
            "version": APP_VERSION,
        }

    def get_local_config(self) -> dict:
        """读取本地配置（data/local_config.json），不存在/损坏时返回空对象"""
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_local_config(self, config: dict) -> dict:
        """保存本地配置：与现有配置合并（不覆盖其它键）"""
        try:
            merged = self.get_local_config()
            if isinstance(config, dict):
                merged.update(config)
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(merged, f, ensure_ascii=False, indent=2)
            return {"status": "ok"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

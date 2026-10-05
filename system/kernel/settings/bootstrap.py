"""默认配置基线：内核首次启动时，把 `data/config/` 里**缺失**的配置从 `defaults/` 补齐。

规则（V3.0.0 · P2）：
- `defaults/` 是**基线**，提交入库；`data/config/` 是运行时配置，**不入库**。
- 只补**缺失**的文件，**不覆盖**用户改过的值。
- 补完即止，不做合并、不做迁移。
"""
import shutil
from pathlib import Path
from typing import List

try:
    from common.paths import CONFIG_DIR
except Exception:  # 极端情况下退回相对定位
    CONFIG_DIR = Path(__file__).resolve().parents[3] / "data" / "config"

DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"


def list_defaults() -> List[str]:
    """基线里有哪些文件。"""
    if not DEFAULTS_DIR.is_dir():
        return []
    return sorted(p.name for p in DEFAULTS_DIR.iterdir()
                  if p.is_file() and not p.name.startswith("."))


def ensure_config() -> List[str]:
    """把基线里缺失的配置补到 `CONFIG_DIR`，返回本次补齐的文件名列表。"""
    created: List[str] = []
    if not DEFAULTS_DIR.is_dir():
        return created
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    for src in sorted(DEFAULTS_DIR.iterdir()):
        if not src.is_file() or src.name.startswith("."):
            continue
        dst = CONFIG_DIR / src.name
        if dst.exists():
            continue          # 用户已有这份配置 → 一个字都不动
        shutil.copy2(src, dst)
        created.append(src.name)
    return created

"""GYun 路径常量 —— 已上移到 `shared/common/paths.py`（唯一来源）。

本模块保留为**转发**，使既有写法继续可用：

    from GYun.core.constants import PROJECT_ROOT

下个版本可删（届时所有引用改为 `from common.paths import ...`）。
"""
from common.paths import (  # noqa: F401
    PROJECT_ROOT,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    TEMP_DIR,
    TOOLS_DIR,
    ENV_FILE,
    GYUN_ROOT,
    GYUN_DATA_ROOT,
    GYUN_DB_PATH,
    GYUN_RESOURCES_DIR,
    GYUN_BACKUPS_DIR,
)

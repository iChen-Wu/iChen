"""iChen 路径常量 —— 唯一来源。

位置：`shared/common/paths.py`（中立层）。
`system/`、`services/`、`apps/` 都可依赖它；本模块不反向依赖任何上层。

导入方式（`shared/` 在 sys.path 上，由 `_pth` / pyproject 保证）：

    from common.paths import PROJECT_ROOT
"""
from pathlib import Path

# 项目根目录：向上 3 级（common/paths.py -> common -> shared -> 项目根）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 常用子目录
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
LOGS_DIR = DATA_DIR / "logs"
# 工程台位于开发机「工作区」层级（仓库外），多个 iChen 相关工程共用；正式版/移动版不存在此目录
WORKBENCH_DIR = PROJECT_ROOT.parent / "workbench"
TEMP_DIR = WORKBENCH_DIR / "temp"
TOOLS_DIR = WORKBENCH_DIR / "tools"

# 环境变量 .env 文件路径
ENV_FILE = CONFIG_DIR / ".env"

# ==================== GYun Data 模块路径 ====================
# V3.0.0 起运行时数据统一归位 data/（见 V3.0.0 Plan 第七节）
GYUN_ROOT = PROJECT_ROOT / "shared" / "GYun"                         # 代码包目录
GYUN_DATA_ROOT = DATA_DIR / "db"                                     # 运行时数据根（data/db）
GYUN_DB_PATH = GYUN_DATA_ROOT / "gyun_data.db"                       # 数据库文件
GYUN_RESOURCES_DIR = GYUN_DATA_ROOT / "resources"                    # 附件资源
GYUN_BACKUPS_DIR = GYUN_DATA_ROOT / "backups"                        # 备份文件

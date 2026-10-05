"""路径工具"""
import os
from GYun.core.constants import (
    GYUN_DB_PATH,
    GYUN_RESOURCES_DIR,
    GYUN_BACKUPS_DIR,
)

def ensure_runtime_dirs():
    for d in [os.path.dirname(GYUN_DB_PATH),
              GYUN_RESOURCES_DIR,
              GYUN_BACKUPS_DIR]:
        os.makedirs(d, exist_ok=True)

def get_resource_dir(entity_id: str) -> str:
    subdir = entity_id[:2]
    return os.path.join(GYUN_RESOURCES_DIR, subdir, entity_id)

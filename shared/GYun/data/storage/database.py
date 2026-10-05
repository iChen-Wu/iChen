"""数据库连接管理与初始化"""
import logging
from peewee import SqliteDatabase
from playhouse.sqlite_ext import FTS5Model
from GYun.core.constants import GYUN_DB_PATH
from GYun.data.utils.path_utils import ensure_runtime_dirs

logger = logging.getLogger(__name__)

# ✅ 核心：db 代理对象必须在顶层无依赖地定义，供其他模块引用
db = SqliteDatabase(None)

def init_db(enable_history: bool = False):
    ensure_runtime_dirs()
    db.init(GYUN_DB_PATH,
            pragmas={
                'journal_mode': 'wal',
                'cache_size': -1024 * 64,
                'foreign_keys': 1,  # ✅ 必须为1，外键级联删除才生效！
            })
    
    # ✅ 修复循环导入：所有 Model 的导入必须放在函数内部！
    from GYun.data.models.entities import Entity
    from GYun.data.models.tags import EntityTag
    from GYun.data.models.fts import EntityFTS
    from GYun.data.models.vectors import EntityVector  # 移入函数内部
    from GYun.data.models.edges import EntityEdge

    tables = [Entity, EntityTag, EntityFTS, EntityVector, EntityEdge]

    # 绑定FTS模型到同一个数据库
    EntityFTS._meta.database = db

    
    if enable_history:
        from GYun.data.models.history import EntityHistory
        tables.append(EntityHistory)
        
    db.create_tables(tables)
    logger.info(f"数据库初始化完成，已确保表结构存在: {[t.__name__ for t in tables]}")

    # ✅ V3.0 说明：source 升格为「应用标识」，模型上已声明 index=True。
    # peewee 的 create_tables 对已存在的库也会幂等补建缺失索引（已实测：删掉
    # entity_source/entity_type 后再次 init_db 自动重建），因此旧库升级时无需手动迁移。

    # ✅ V3.0.1 旧库自愈迁移：gyun_entity_tags 外键补 ON DELETE CASCADE
    _ensure_tags_cascade()


def _ensure_tags_cascade():
    """
    旧库自愈迁移（幂等）：早期创建的 gyun_entity_tags 表外键为 NO ACTION，
    硬删带标签实体会报 FOREIGN KEY constraint failed。检测到缺失时自动重建表补 CASCADE。
    新库（peewee 按模型建表）天然带 CASCADE，直接跳过。
    """
    fks = db.execute_sql('PRAGMA foreign_key_list("gyun_entity_tags")').fetchall()
    # 列顺序: id, seq, table, from, to, on_update, on_delete, match
    if any(r[6] == 'CASCADE' for r in fks):
        return  # 已合规，无需迁移

    logger.warning("检测到 gyun_entity_tags 外键缺少 ON DELETE CASCADE，开始自动迁移...")
    try:
        from GYun.data.service.maintenance_service import MaintenanceService
        MaintenanceService.backup()
    except Exception as e:
        logger.warning(f"迁移前备份失败（继续执行）: {e}")

    # PRAGMA foreign_keys 必须在事务外切换
    db.execute_sql('PRAGMA foreign_keys=OFF')
    try:
        with db.atomic():
            db.execute_sql('ALTER TABLE "gyun_entity_tags" RENAME TO "gyun_entity_tags_old"')
            # SQLite RENAME TO 保留旧表索引名，先删避免冲突
            db.execute_sql('DROP INDEX IF EXISTS "entitytag_entity_id"')
            db.execute_sql('DROP INDEX IF EXISTS "entitytag_entity_id_tag"')
            db.execute_sql('''
                CREATE TABLE "gyun_entity_tags" (
                    "id" INTEGER NOT NULL PRIMARY KEY,
                    "entity_id" TEXT NOT NULL,
                    "tag" TEXT NOT NULL,
                    FOREIGN KEY ("entity_id") REFERENCES "gyun_entities" ("entity_id") ON DELETE CASCADE
                )
            ''')
            db.execute_sql('CREATE INDEX "entitytag_entity_id" ON "gyun_entity_tags" ("entity_id")')
            db.execute_sql('CREATE UNIQUE INDEX "entitytag_entity_id_tag" '
                           'ON "gyun_entity_tags" ("entity_id", "tag")')
            db.execute_sql('INSERT INTO "gyun_entity_tags" ("id", "entity_id", "tag") '
                           'SELECT "id", "entity_id", "tag" FROM "gyun_entity_tags_old"')
            db.execute_sql('DROP TABLE "gyun_entity_tags_old"')
    finally:
        db.execute_sql('PRAGMA foreign_keys=ON')
    logger.info("gyun_entity_tags 已自动重建（外键补 ON DELETE CASCADE），数据无损")

def close_db():
    if not db.is_closed():
        db.close()
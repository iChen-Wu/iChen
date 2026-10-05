"""运维工具：备份、恢复、VACUUM、完整性检查、GC、向量补全、记忆清理"""
import os
import shutil
import datetime
import time
import logging
from typing import List, Callable, Optional
from GYun.core.constants import GYUN_DB_PATH, GYUN_RESOURCES_DIR, GYUN_BACKUPS_DIR
from GYun.data.storage.database import db
from GYun.data.utils.exceptions import DatabaseError, FileIOError
from GYun.data.models.entities import Entity
from GYun.data.models.vectors import EntityVector
from GYun.data.storage.vector_storage import VectorStorage

logger = logging.getLogger(__name__)

class MaintenanceService:
    @staticmethod
    def backup() -> str:
        # 执行WAL checkpoint
        db.execute_sql('PRAGMA wal_checkpoint(TRUNCATE);')
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f'gyun_data_backup_{timestamp}.db'
        backup_path = os.path.join(GYUN_BACKUPS_DIR, backup_name)
        try:
            shutil.copy2(GYUN_DB_PATH, backup_path)
        except OSError as e:
            raise FileIOError(f"备份失败: {e}", original=e)
        return backup_path

    @staticmethod
    def restore(backup_file: str):
        if not os.path.exists(backup_file):
            raise FileIOError(f"备份文件不存在: {backup_file}")
        # 先备份当前库
        MaintenanceService.backup()
        # 关闭当前连接
        db.close()
        try:
            shutil.copy2(backup_file, GYUN_DB_PATH)
        except OSError as e:
            raise FileIOError(f"恢复失败: {e}", original=e)
        # 重新连接
        from GYun.data.storage.database import init_db
        init_db()

    @staticmethod
    def vacuum():
        try:
            db.execute_sql('VACUUM;')
        except Exception as e:
            raise DatabaseError(f"VACUUM失败: {e}", original=e)

    @staticmethod
    def integrity_check() -> dict:
        cursor = db.execute_sql('PRAGMA integrity_check;')
        rows = cursor.fetchall()
        ok = all(row[0] == 'ok' for row in rows)
        return {'ok': ok, 'details': [row[0] for row in rows]}

    @staticmethod
    def gc(execute: bool = False) -> List[str]:
        """垃圾回收：检测并清理未被任何实体引用的孤立附件文件"""
        orphans = []
        # 收集所有被引用的资源路径（转换为绝对路径以便与扫描结果比对）
        used_paths = set()
        for entity in Entity.select(Entity.resource_path):
            if entity.resource_path:
                # 将数据库中的相对路径转换为绝对路径
                abs_path = os.path.join(GYUN_RESOURCES_DIR, os.path.normpath(entity.resource_path))
                used_paths.add(abs_path)
        # 扫描resources目录
        if not os.path.exists(GYUN_RESOURCES_DIR):
            return []
        for root, dirs, files in os.walk(GYUN_RESOURCES_DIR):
            for f in files:
                full = os.path.join(root, f)
                norm = os.path.normpath(full)
                if norm not in used_paths:
                    orphans.append(norm)
        if execute:
            for path in orphans:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return orphans

    # ==========================================
    # ✅ V3.0 新增：一键删除应用（烂尾项目彻底清理）
    # ==========================================

    @staticmethod
    def delete_application(source: str, cascade_resource: bool = True) -> int:
        """
        硬删除指定应用的全部实体（级联清除向量、边、标签），并物理删除附件目录 resources/{source}/。
        :param source: 应用标识（不允许 None/全局模式）
        :param cascade_resource: 是否同时物理删除 resources/{source}/ 附件目录
        :return: 被删除的实体数量
        """
        from GYun.data.storage.fts_storage import FTSStorage
        from GYun.data.storage.resource_storage import ResourceStorage, validate_source

        source = validate_source(source)
        if source is None:
            raise DatabaseError("delete_application 需要明确的应用标识，不支持全局模式")

        entity_ids = [e.entity_id for e in Entity.select(Entity.entity_id).where(Entity.source == source)]
        if not entity_ids:
            return 0

        with db.atomic():
            # FTS 是独立虚拟表（无外键级联），先逐条清理
            for eid in entity_ids:
                FTSStorage.remove(eid)
            # 主表硬删：EntityVector / EntityEdge / EntityTag 通过 ON DELETE CASCADE 自动物理擦除
            Entity.delete().where(Entity.source == source).execute()

        if cascade_resource:
            ResourceStorage.delete_application(source)
        logger.info(f"已一键删除应用 {source!r}，共 {len(entity_ids)} 条实体（级联向量/边/标签）")
        return len(entity_ids)

    # ==========================================
    # ✅ V2.1 新增：向量与记忆生命周期运维工具
    # ==========================================

    @staticmethod
    def backfill_embeddings(
        embed_func: Callable[[str], List[float]], 
        model_name: str = 'default', 
        type_filter: Optional[List[str]] = None, 
        batch_size: int = 100
    ) -> dict:
        """
        历史数据向量离线补全 (支持断点续传)
        :param embed_func: 业务层传入的调用大模型的函数 (底座绝不绑定具体模型)
        :param model_name: 向量对应的模型名称，用于断点续传判断
        :param type_filter: 限定只补全哪些 type 的实体 (如 ['memory_long', 'note'])，为 None 则补全全量
        :param batch_size: 每次处理的批量大小 (防内存溢出)
        :return: 统计信息 dict
        """
        stats = {'total': 0, 'skipped': 0, 'success': 0, 'failed': 0}
        
        # 构建查询条件
        query = Entity.select(Entity.entity_id, Entity.content, Entity.type)
        if type_filter:
            query = query.where(Entity.type << type_filter)
            
        entities = list(query.execute())
        stats['total'] = len(entities)
        
        logger.info(f"开始向量补全，总计 {stats['total']} 条候选实体，模型: {model_name}")
        
        for i, entity in enumerate(entities):
            eid = entity.entity_id
            content = entity.content
            
            # 🟡2 核心防线：断点续传！如果已有该模型的向量，直接跳过，省钱省时
            exists = EntityVector.select().where(
                (EntityVector.entity == eid) & 
                (EntityVector.model_name == model_name)
            ).exists()
            
            if exists:
                stats['skipped'] += 1
                continue
                
            if not content:
                stats['skipped'] += 1
                continue
                
            try:
                # 调用业务层传入的大模型接口
                vector = embed_func(content)
                # 存入底座
                VectorStorage.save_vector(
                    entity_id=eid, 
                    embedding=vector, 
                    model_name=model_name, 
                    dim=len(vector)
                )
                stats['success'] += 1
            except Exception as e:
                logger.error(f"实体 {eid} 向量生成失败: {e}")
                stats['failed'] += 1
                
            # 简易批次日志输出 (替代 tqdm，避免引入非必须依赖)
            if (i + 1) % batch_size == 0:
                logger.info(f"已处理 {i + 1}/{stats['total']} (成功:{stats['success']}, 跳过:{stats['skipped']}, 失败:{stats['failed']})")
                
        logger.info(f"向量补全完成: {stats}")
        return stats

    @staticmethod
    def gc_memories(
        days_unused: int = 90, 
        min_confidence: float = 0.1, 
        execute: bool = False
    ) -> List[str]:
        """
        清理长期未被召回且置信度极低的归档记忆 (大脑的深度遗忘)
        :param days_unused: 超过多少天没更新/访问的归档记忆将被清理
        :param min_confidence: extra.confidence 低于此阈值的才会被清理
        :param execute: 是否真实执行硬删除 (False 仅预览)
        :return: 将要/已被清理的 entity_id 列表
        """
        threshold_time = int((time.time() - days_unused * 24 * 3600) * 1000)
        to_cleanup = []
        
        # 找出归档状态 (condensed) 且长期未更新的实体
        # 注意：SQLite 对 JSON 的深度查询性能有限，这里采用主表时间+内存过滤的双重机制
        candidates = Entity.select(
            Entity.entity_id, Entity.update_time, Entity.extra
        ).where(
            (Entity.is_deleted == 0) & 
            (Entity.update_time < threshold_time)
        )
        
        for cand in candidates:
            # 约定归档记忆在 extra 里塞了 status='archived'
            if cand.extra and isinstance(cand.extra, dict) and cand.extra.get('status') == 'archived':
                # 约定置信度存在 extra.confidence
                confidence = cand.extra.get('confidence', 1.0)  # 如果没写置信度，默认1.0不删
                if confidence <= min_confidence:
                    to_cleanup.append(cand.entity_id)
                    
        if execute:
            for eid in to_cleanup:
                # 🔴1 防线：硬删主表，由于我们设计了外键级联 (CASCADE)
                # EntityVector 表里的对应向量会被 SQLite 自动物理擦除！无需手动清理！
                Entity.delete().where(Entity.entity_id == eid).execute()
            logger.info(f"已硬删除 {len(to_cleanup)} 条废弃归档记忆及其级联向量")
        else:
            logger.info(f"预览：发现 {len(to_cleanup)} 条可清理的废弃归档记忆")
            
        return to_cleanup
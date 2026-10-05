"""异步客户端 AsyncGyunClient

将同步 GyunClient 包装为 async API：所有操作通过 asyncio.to_thread 在线程池中执行，
不阻塞事件循环；写操作通过 asyncio.Lock 串行化，保证 SQLite 单写者下的并发安全。

用法：
    client = AsyncGyunClient(source='class_manager')
    eid = await client.create_entity({'type': 'note', 'title': 'hello'})
    res = await client.query_entities({'type': 'note'})
    await client.close()

与同步 GyunClient 方法签名一一对应，老代码可平滑迁移。
"""
import asyncio
import functools
import logging
from typing import List, Dict, Any, Optional, AsyncIterator

logger = logging.getLogger(__name__)

# Python 3.9+ 原生 asyncio.to_thread；低版本兼容降级（项目声明 requires-python>=3.10）
if hasattr(asyncio, 'to_thread'):
    _to_thread = asyncio.to_thread
else:
    async def _to_thread(func, *args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


class AsyncGyunClient:
    """异步版统一客户端入口（to_thread 包装，写操作加锁）"""

    def __init__(self, source: Optional[str] = None, enable_history: bool = False):
        # 延迟导入，避免与 client 顶层导入形成循环依赖
        from GYun.data.client import GyunClient
        self._client = GyunClient(source=source, enable_history=enable_history)
        # 写操作互斥锁：SQLite 单写者 + 组合写操作（如 batch/condense）原子性。
        # 惰性初始化：3.8/3.9 的 asyncio.Lock 构造时绑定当前 event loop，
        # 同步上下文构造后 asyncio.run 使用会跨 loop 报错。
        self._lock: Optional[asyncio.Lock] = None
        # V2.1 子服务挂载（async 版）
        self.memory = AsyncMemoryService(self)
        self.knowledge = AsyncKnowledgeService(self)
        # 运维工具（同步对象，需要时可自行 asyncio.to_thread 调用）
        self.maintenance = self._client.maintenance

    # ---- 应用上下文 ----
    @property
    def source(self) -> Optional[str]:
        """当前应用标识；None 表示全局模式"""
        return self._client.source

    def _get_write_lock(self) -> asyncio.Lock:
        """惰性创建写锁（首次在事件循环内调用时创建）"""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def set_source(self, source: Optional[str]):
        """切换应用上下文（纯配置，无 IO，直接同步执行）"""
        self._client.set_source(source)

    # ---- 实体管理 ----
    async def create_entity(self, data: dict) -> str:
        async with self._get_write_lock():
            return await _to_thread(self._client.create_entity, data)

    async def get_entity(self, entity_id: str) -> dict:
        return await _to_thread(self._client.get_entity, entity_id)

    async def update_entity(self, entity_id: str, update_data: dict):
        async with self._get_write_lock():
            await _to_thread(self._client.update_entity, entity_id, update_data)

    async def delete_entity(self, entity_id: str, hard: bool = False, cascade_resource: bool = True):
        async with self._get_write_lock():
            await _to_thread(self._client.delete_entity, entity_id, hard, cascade_resource)

    async def restore_entity(self, entity_id: str):
        async with self._get_write_lock():
            await _to_thread(self._client.restore_entity, entity_id)

    # ---- 查询 ----
    async def query_entities(self, filters: dict = None,
                             order_by: str = "create_time",
                             order: str = "desc",
                             page: int = 1,
                             page_size: int = 20) -> dict:
        return await _to_thread(
            self._client.query_entities, filters, order_by, order, page, page_size)

    async def fulltext_search(self, keyword: str, filters: dict = None,
                              order_by: str = "relevance",
                              page: int = 1,
                              page_size: int = 20) -> dict:
        return await _to_thread(
            self._client.fulltext_search, keyword, filters, order_by, page, page_size)

    async def get_entities_batch(self, entity_ids: List[str]) -> List[dict]:
        return await _to_thread(self._client.get_entities_batch, entity_ids)

    async def get_related_entities(self, entity_id: str) -> List[dict]:
        return await _to_thread(self._client.get_related_entities, entity_id)

    async def get_referenced_entities(self, entity_id: str) -> List[dict]:
        return await _to_thread(self._client.get_referenced_entities, entity_id)

    async def count_entities(self, filters: dict = None) -> int:
        return await _to_thread(self._client.count_entities, filters)

    async def group_count(self, group_by: str = "type", filters: dict = None) -> List[Dict]:
        return await _to_thread(self._client.group_count, group_by, filters)

    async def iter_all_entities(self, filters: dict = None, batch_size: int = 100) -> AsyncIterator[dict]:
        """
        异步遍历全部实体。
        内部在单个后台线程内消费完整同步生成器（避免跨线程共享 SQLite cursor），
        然后逐条 async yield；本地数据量级下内存可接受。
        """
        entities = await _to_thread(
            lambda: list(self._client.iter_all_entities(filters, batch_size)))
        for entity in entities:
            yield entity

    # ---- 附件 ----
    async def upload_resource(self, entity_id: str, file_path: str) -> str:
        async with self._get_write_lock():
            return await _to_thread(self._client.upload_resource, entity_id, file_path)

    async def get_resource_path(self, entity_id: str) -> Optional[str]:
        return await _to_thread(self._client.get_resource_path, entity_id)

    async def delete_resource(self, entity_id: str):
        async with self._get_write_lock():
            await _to_thread(self._client.delete_resource, entity_id)

    # ---- 批量 ----
    async def batch_create_entities(self, data_list: List[dict], on_error: str = "rollback") -> List[str]:
        async with self._get_write_lock():
            return await _to_thread(self._client.batch_create_entities, data_list, on_error)

    async def batch_update_entities(self, filters: dict, update_data: dict) -> int:
        async with self._get_write_lock():
            return await _to_thread(self._client.batch_update_entities, filters, update_data)

    # ---- 运维 ----
    async def backup(self) -> str:
        async with self._get_write_lock():
            return await _to_thread(self._client.backup)

    async def delete_application(self, source: str, cascade_resource: bool = True) -> int:
        async with self._get_write_lock():
            return await _to_thread(self._client.delete_application, source, cascade_resource)

    async def restore(self, backup_file: str):
        async with self._get_write_lock():
            await _to_thread(self._client.restore, backup_file)

    async def vacuum(self):
        async with self._get_write_lock():
            await _to_thread(self._client.vacuum)

    async def integrity_check(self) -> dict:
        return await _to_thread(self._client.integrity_check)

    async def gc(self, execute: bool = False) -> list:
        async with self._get_write_lock():
            return await _to_thread(self._client.gc, execute)

    # ---- 钩子 ----
    def register_hook(self, hook_type: str, func: callable):
        """注册钩子（纯配置，无 IO，直接同步执行）"""
        self._client.register_hook(hook_type, func)

    # ---- 生命周期 ----
    async def close(self):
        """关闭数据库连接"""
        try:
            await _to_thread(self._client.close)
        except Exception as e:
            logger.error(f"关闭数据库连接时出错: {e}")

    # asyncio 别名
    aclose = close

    async def __aenter__(self) -> 'AsyncGyunClient':
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


class AsyncMemoryService:
    """异步版记忆引擎（挂载于 AsyncGyunClient.memory）"""

    def __init__(self, async_client: AsyncGyunClient):
        self._async = async_client
        self._client = async_client._client  # 同步 client，供内部同步调用

    async def memorize(self, text: str, embedding: list = None, type: str = 'memory_long',
                       extra: dict = None, **kwargs) -> str:
        async with self._async._get_write_lock():
            return await _to_thread(
                self._client.memory.memorize, text, embedding, type, extra, **kwargs)

    async def recall_memories(self, query_vector=None, query_text=None,
                              filters=None, top_k=5, threshold=0.5,
                              alpha=0.7, beta=0.2, gamma=0.1,
                              expand_relations=False) -> list:
        return await _to_thread(
            self._client.memory.recall_memories, query_vector, query_text, filters,
            top_k, threshold, alpha, beta, gamma, expand_relations)

    async def condense_memories(self, source_ids: list, condensed_text: str,
                                condensed_embedding: list = None) -> str:
        async with self._async._get_write_lock():
            return await _to_thread(
                self._client.memory.condense_memories, source_ids, condensed_text,
                condensed_embedding)


class AsyncKnowledgeService:
    """异步版知识图谱服务（挂载于 AsyncGyunClient.knowledge）"""

    def __init__(self, async_client: AsyncGyunClient):
        self._async = async_client
        self._client = async_client._client

    async def add_relation(self, source_id: str, target_id: str, relation_type: str,
                           properties: dict = None, weight: float = 1.0) -> int:
        async with self._async._get_write_lock():
            return await _to_thread(
                self._client.knowledge.add_relation, source_id, target_id,
                relation_type, properties, weight)

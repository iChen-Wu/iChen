"""查询服务，支持多条件过滤、排序、分页、全文检索、关联查询"""
from typing import List, Dict, Any, Optional, Iterator
from peewee import fn, SQL, DoesNotExist, Case
import peewee
from GYun.data.models.entities import Entity
from GYun.data.models.tags import EntityTag
from GYun.data.storage import EntityStorage, TagStorage, FTSStorage
from GYun.data.utils.exceptions import EntityNotFoundError

class QueryService:
    @staticmethod
    def query(filters: dict = None, order_by: str = 'create_time',
              order: str = 'desc', page: int = 1, page_size: int = 20) -> dict:
        query = Entity.select()
        query = QueryService._apply_filters(query, filters or {})
        order_field = getattr(Entity, order_by, Entity.create_time)
        if order.lower() == 'asc':
            query = query.order_by(order_field.asc())
        else:
            query = query.order_by(order_field.desc())
        total = query.count()
        offset = (page - 1) * page_size
        items = query.limit(page_size).offset(offset)
        return {
            'total': total,
            'list': [QueryService._to_dict(e) for e in items],
            'page': page,
            'page_size': page_size,
        }

    @staticmethod
    def fulltext_search(keyword: str, filters: dict = None,
                        order_by: str = 'relevance',
                        page: int = 1,
                        page_size: int = 20) -> dict:
        # 空关键词守卫：直接返回空结果，避免 FTS match('') 命中全量后 Python 验证崩溃
        if not keyword:
            return {'total': 0, 'list': [], 'page': page, 'page_size': page_size}
        # 1. 优先尝试 FTS5 快速粗筛（解除硬编码 limit，使用极大值确保不遗漏）
        raw_results = FTSStorage.search(keyword, limit=999999, offset=0)
        ids = [r[0] for r in raw_results]
        score_map = {rid: rank for rid, rank in raw_results}
        
        # 🌟🌟🌟 核心防线：FTS 降级兜底 🌟🌟🌟
        # 如果 FTS5 找不到任何结果（通常是子串搜索时整词匹配失败），
        # 绝不能直接返回空！必须降级为全表扫描+Python子串过滤！
        if not ids and keyword:
            # 降级：直接查主表，应用常规过滤（如 is_deleted=0）
            fallback_query = Entity.select()
            fallback_query = QueryService._apply_filters(fallback_query, filters or {})
            items = list(fallback_query.execute())
            
            # 纯 Python 子串精确过滤（极其稳健）
            filtered = []
            for e in items:
                title = (e.title or '').lower()
                content = (e.content or '').lower()
                if keyword.lower() in title or keyword.lower() in content:
                    filtered.append(e)
            
            # 🌟 修复：根据 order_by 参数动态排序
            if order_by == 'relevance' or order_by not in ['create_time', 'update_time', 'priority', 'title']:
                # 降级时无相关性分数，统一按创建时间倒序
                filtered.sort(key=lambda x: x.create_time, reverse=True)
            elif order_by == 'create_time':
                filtered.sort(key=lambda x: x.create_time, reverse=True)
            elif order_by == 'update_time':
                filtered.sort(key=lambda x: x.update_time, reverse=True)
            elif order_by == 'priority':
                filtered.sort(key=lambda x: x.priority, reverse=True)
            elif order_by == 'title':
                filtered.sort(key=lambda x: x.title or '')
            # 其他字段按创建时间倒序兜底
            
            start = (page - 1) * page_size
            end = start + page_size
            # 降级结果无 score，统一赋 0.0
            result_list = []
            for e in filtered[start:end]:
                item = QueryService._to_dict(e)
                item['score'] = 0.0
                result_list.append(item)
            return {
                'total': len(filtered),
                'list': result_list,
                'page': page,
                'page_size': page_size,
            }

        # 2. FTS 找到了结果，走原有的双重过滤逻辑（FTS粗筛 + Python精确验证）
        query = Entity.select().where(Entity.entity_id.in_(ids))
        query = QueryService._apply_filters(query, filters or {})
        
        items = list(query.execute())
        
        filtered = []
        for e in items:
            title = (e.title or '').lower()
            content = (e.content or '').lower()
            if keyword.lower() in title or keyword.lower() in content:
                filtered.append(e)
        
        if order_by == 'relevance':
            filtered.sort(key=lambda x: score_map.get(x.entity_id, 9999))
        elif order_by == 'create_time':
            filtered.sort(key=lambda x: x.create_time, reverse=True)
        elif order_by == 'update_time':
            filtered.sort(key=lambda x: x.update_time, reverse=True)
        elif order_by == 'priority':
            filtered.sort(key=lambda x: x.priority, reverse=True)
        elif order_by == 'title':
            filtered.sort(key=lambda x: x.title or '')
        else:
            # 默认按相关性排序
            filtered.sort(key=lambda x: score_map.get(x.entity_id, 9999))
            
        start = (page - 1) * page_size
        end = start + page_size
        # 🌟 修复：返回结果中必须包含 score 字段，供 BM25 归一化使用
        result_list = []
        for e in filtered[start:end]:
            item = QueryService._to_dict(e)
            item['score'] = score_map.get(e.entity_id, 0.0)
            result_list.append(item)
        return {
            'total': len(filtered),
            'list': result_list,
            'page': page,
            'page_size': page_size,
        }

    @staticmethod
    def get_entities_batch(entity_ids: List[str]) -> List[dict]:
        entities = Entity.select().where(Entity.entity_id.in_(entity_ids))
        mapping = {e.entity_id: e for e in entities}
        return [QueryService._to_dict(mapping[eid]) for eid in entity_ids if eid in mapping]

    @staticmethod
    def get_related_entities(entity_id: str) -> List[dict]:
        try:
            entity = EntityStorage.get(entity_id)
        except EntityNotFoundError:
            return []
        related_ids = entity.related_ids or []
        return QueryService.get_entities_batch(related_ids)

    @staticmethod
    def get_referenced_entities(entity_id: str) -> List[dict]:
        """查询所有关联了该实体的实体（反向关联）"""
        # 使用 SQL 的 json_each 遍历 JSON 数组
        from GYun.data.storage.database import db
        raw_sql = """
            SELECT e.* FROM gyun_entities e
            WHERE EXISTS (
                SELECT 1 FROM json_each(e.related_ids)
                WHERE value = ?
            ) AND e.is_deleted = 0
        """
        cursor = db.execute_sql(raw_sql, (entity_id,))
        # 将查询结果转换为 Entity 对象
        columns = [col[0] for col in cursor.description]
        entities = []
        for row in cursor.fetchall():
            entity_dict = dict(zip(columns, row))
            # 将 extra 和 related_ids 从 JSON 字符串解析为 Python 对象
            if 'extra' in entity_dict and isinstance(entity_dict['extra'], str):
                import json
                entity_dict['extra'] = json.loads(entity_dict['extra'])
            if 'related_ids' in entity_dict and isinstance(entity_dict['related_ids'], str):
                import json
                entity_dict['related_ids'] = json.loads(entity_dict['related_ids'])
            # 创建一个临时对象
            from GYun.data.models.entities import Entity
            entity = Entity(**entity_dict)
            entities.append(entity)
        return [QueryService._to_dict(e) for e in entities]

    @staticmethod
    def count(filters: dict = None) -> int:
        query = Entity.select()
        query = QueryService._apply_filters(query, filters or {})
        return query.count()

    @staticmethod
    def group_count(group_by: str = 'type', filters: dict = None) -> List[Dict]:
        field = getattr(Entity, group_by, Entity.type)
        query = (Entity
                 .select(field.alias('key'), fn.COUNT(Entity.entity_id).alias('cnt'))
                 .group_by(field))
        query = QueryService._apply_filters(query, filters or {})
        return [{'type': row.key, 'cnt': row.cnt} for row in query]

    @staticmethod
    def iter_all(filters: dict = None, batch_size: int = 100) -> Iterator[dict]:
        query = Entity.select()
        query = QueryService._apply_filters(query, filters or {})
        page = 1
        while True:
            batch = query.limit(batch_size).offset((page - 1) * batch_size).execute()
            if not batch:
                break
            for entity in batch:
                yield QueryService._to_dict(entity)
            page += 1

    @staticmethod
    def _apply_filters(query, filters: dict):
        # type
        if 'type' in filters:
            types = filters['type']
            if isinstance(types, list):
                query = query.where(Entity.type.in_(types))
            else:
                query = query.where(Entity.type == types)
        # tags
        if 'tags' in filters and filters['tags']:
            mode = filters.get('tags_mode', 'any')
            tag_ids = TagStorage.get_entity_ids_by_tags(filters['tags'], mode)
            if not tag_ids:
                query = query.where(Entity.entity_id.is_null())
            else:
                query = query.where(Entity.entity_id.in_(tag_ids))
        # 时间范围
        if 'create_time_start' in filters:
            query = query.where(Entity.create_time >= filters['create_time_start'])
        if 'create_time_end' in filters:
            query = query.where(Entity.create_time <= filters['create_time_end'])
        if 'update_time_start' in filters:
            query = query.where(Entity.update_time >= filters['update_time_start'])
        if 'update_time_end' in filters:
            query = query.where(Entity.update_time <= filters['update_time_end'])
        # 优先级
        if 'priority_min' in filters:
            query = query.where(Entity.priority >= filters['priority_min'])
        if 'priority_max' in filters:
            query = query.where(Entity.priority <= filters['priority_max'])
        # source（V3.0 应用标识；None 或 '__null__' 表示搜索无应用归属的记录）
        if 'source' in filters:
            src = filters['source']
            if src is None or src == '__null__':
                query = query.where(Entity.source.is_null())
            else:
                query = query.where(Entity.source == src)
        # 标题模糊
        if 'keyword_title' in filters:
            query = query.where(Entity.title.contains(filters['keyword_title']))
        # extra 字段过滤
        extra_prefix = 'extra_'
        for key, val in filters.items():
            if key.startswith(extra_prefix):
                extra_key = key[len(extra_prefix):]
                # 注意：此处使用 json_extract 直接比较，若值类型不匹配可能导致结果为空。
                # 如需类型安全，可考虑 CAST(... AS TEXT) 转换，当前暂保持原样。
                expr = fn.json_extract(Entity.extra, f'$.{extra_key}') == val
                query = query.where(expr)
        # 默认排除已删除，除非显式要求
        if 'is_deleted' not in filters:
            query = query.where(Entity.is_deleted == 0)
        elif filters['is_deleted'] is not None:
            query = query.where(Entity.is_deleted == filters['is_deleted'])
        return query

    @staticmethod
    def _to_dict(entity) -> dict:
        return {
            'entity_id': entity.entity_id,
            'type': entity.type,
            'title': entity.title,
            'content': entity.content,
            'priority': entity.priority,
            'source': entity.source,
            'resource_path': entity.resource_path,
            'extra': entity.extra,
            'related_ids': entity.related_ids,
            'is_deleted': entity.is_deleted,
            'create_time': entity.create_time,
            'update_time': entity.update_time,
        }

    @staticmethod
    def get_candidate_ids(filters: dict) -> list:
        """
        【V2.1 新增】混合召回第一阶段：SQL结构化粗筛
        仅返回满足条件的 entity_id 列表，不拉取全量数据，极大地节省内存并提速
        """
        query = Entity.select(Entity.entity_id)
        
        # 1. 默认安全防线：只查未删除的
        is_deleted = filters.get('is_deleted', 0)
        query = query.where(Entity.is_deleted == is_deleted)
        
        # 2. Type 过滤 (支持单字符串或列表)
        if 'type' in filters:
            type_val = filters['type']
            if isinstance(type_val, list):
                query = query.where(Entity.type << type_val)
            else:
                query = query.where(Entity.type == type_val)
                
        # 3. Source 过滤（V3.0：None / '__null__' 表示搜索无应用归属的记录）
        if 'source' in filters:
            src = filters['source']
            if src is None or src == '__null__':
                query = query.where(Entity.source.is_null())
            else:
                query = query.where(Entity.source == src)
            
        # 4. Priority 范围过滤
        if 'priority_min' in filters:
            query = query.where(Entity.priority >= filters['priority_min'])
        if 'priority_max' in filters:
            query = query.where(Entity.priority <= filters['priority_max'])
            
        # 5. 时间范围过滤
        if 'create_time_start' in filters:
            query = query.where(Entity.create_time >= filters['create_time_start'])
        if 'create_time_end' in filters:
            query = query.where(Entity.create_time <= filters['create_time_end'])
        if 'update_time_start' in filters:
            query = query.where(Entity.update_time >= filters['update_time_start'])
        if 'update_time_end' in filters:
            query = query.where(Entity.update_time <= filters['update_time_end'])
            
        # 6. 标签过滤 (多对多关联子查询)
        if 'tags' in filters:
            tags = filters['tags']
            mode = filters.get('tags_mode', 'any')
            if mode == 'all':
                # 必须包含所有标签
                for tag in tags:
                    query = query.where(
                        Entity.entity_id.in_(
                            EntityTag.select(EntityTag.entity).where(EntityTag.tag == tag)
                        )
                    )
            else:
                # 包含任一标签
                query = query.where(
                    Entity.entity_id.in_(
                        EntityTag.select(EntityTag.entity).where(EntityTag.tag << tags)
                    )
                )
                
        # 7. Extra JSON 字段过滤 (利用 SQLite 的 json_extract 函数)
        # 注意：此处直接比较可能因类型问题导致查询结果不符合预期，
        # 若发现过滤不生效，请检查传入值类型是否与数据库中存储的类型一致。
        for key, value in filters.items():
            if key.startswith('extra_'):
                json_key = key[6:]  # 剥离 'extra_' 前缀
                if json_key.endswith('_min'):
                    actual_key = json_key[:-4]
                    query = query.where(peewee.fn.json_extract(Entity.extra, f'$.{actual_key}') >= value)
                elif json_key.endswith('_max'):
                    actual_key = json_key[:-4]
                    query = query.where(peewee.fn.json_extract(Entity.extra, f'$.{actual_key}') <= value)
                else:
                    query = query.where(peewee.fn.json_extract(Entity.extra, f'$.{json_key}') == value)

        # 执行查询并提取纯 ID 列表
        return [row.entity_id for row in query.execute()]
"""图谱边存储层"""
import time
from GYun.data.models.edges import EntityEdge
from GYun.data.models.entities import Entity

class EdgeStorage:
    @staticmethod
    def add_edge(source_id: str, target_id: str, relation_type: str, properties: dict = None, weight: float = 1.0) -> int:
        """创建一条带谓词的关系边"""
        props = properties or {}
        now = int(time.time() * 1000)
        # 利用 ON CONFLICT 自动处理重复建边（更新属性和权重）
        edge = EntityEdge.insert(
            source=source_id, target=target_id, relation_type=relation_type,
            weight=weight, properties=props, create_time=now
        ).on_conflict(
            conflict_target=[EntityEdge.source, EntityEdge.target, EntityEdge.relation_type],
            update={EntityEdge.properties: props, EntityEdge.weight: weight}
        ).execute()
        return edge

    @staticmethod
    def query_edges(source_id: str = None, target_id: str = None, relation_type: str = None) -> list:
        """灵活查询边：支持正向溯源、反向推理、按谓词过滤"""
        query = EntityEdge.select()
        if source_id:
            query = query.where(EntityEdge.source == source_id)
        if target_id:
            query = query.where(EntityEdge.target == target_id)
        if relation_type:
            query = query.where(EntityEdge.relation_type == relation_type)
        
        results = []
        for edge in query.execute():
            try:
                # 🔴 防线：查出关联实体的核心信息喂给大模型，如果实体已被硬删则跳过脏边
                src_entity = Entity.get(Entity.entity_id == edge.source_id)
                tgt_entity = Entity.get(Entity.entity_id == edge.target_id)
                results.append({
                    'edge_id': edge.id,
                    'source_id': edge.source_id,
                    'source_title': src_entity.title,
                    'target_id': edge.target_id,
                    'target_title': tgt_entity.title,
                    'relation_type': edge.relation_type,
                    'weight': edge.weight,
                    # 🚨 防止 JSON 解析异常兜底
                    'properties': edge.properties if isinstance(edge.properties, dict) else {}
                })
            except Entity.DoesNotExist:
                # 理论上因为有 CASCADE 级联防线，实体删了边不可能还在。但如果真出现了脏数据，直接忽略
                continue
        return results

    @staticmethod
    def remove_edge(source_id: str = None, target_id: str = None, relation_type: str = None) -> int:
        """精准删除关系边"""
        query = EntityEdge.delete()
        if source_id:
            query = query.where(EntityEdge.source == source_id)
        if target_id:
            query = query.where(EntityEdge.target == target_id)
        if relation_type:
            query = query.where(EntityEdge.relation_type == relation_type)
        return query.execute()
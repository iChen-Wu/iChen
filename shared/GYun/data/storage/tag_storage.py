"""标签存储层"""
from typing import List

class TagStorage:
    @staticmethod
    def set_tags(entity_id: str, tags: List[str]):
        from GYun.data.models.tags import EntityTag  # 延迟导入避免循环
        # 先删后插（事务外层负责）
        EntityTag.delete().where(EntityTag.entity == entity_id).execute()
        rows = [{'entity': entity_id, 'tag': t} for t in tags]
        if rows:
            EntityTag.insert_many(rows).execute()

    @staticmethod
    def get_tags(entity_id: str) -> List[str]:
        from GYun.data.models.tags import EntityTag  # 延迟导入
        return [t.tag for t in EntityTag.select().where(EntityTag.entity == entity_id)]

    @staticmethod
    def get_entity_ids_by_tags(tags: List[str], mode: str = 'all') -> List[str]:
        from GYun.data.models.tags import EntityTag  # 延迟导入
        from peewee import fn
        if not tags:
            return []
        query = EntityTag.select(EntityTag.entity).where(EntityTag.tag.in_(tags))
        if mode == 'all':
            # 必须包含所有标签
            result = (query
                      .group_by(EntityTag.entity)
                      .having(fn.Count(EntityTag.tag) == len(tags))
                      .execute())
            return [r.entity.entity_id for r in result]
        else:  # any
            return list(set(r.entity.entity_id for r in query))
"""FTS索引存储层"""
from typing import Optional
from GYun.data.utils.fts_utils import segment

class FTSStorage:
    @staticmethod
    def index(entity_id: str, title: str, content: Optional[str]):
        from GYun.data.models.fts import EntityFTS  # 延迟导入
        seg_title = segment(title)
        seg_content = segment(content) if content else ''
        EntityFTS.delete().where(EntityFTS.entity_id == entity_id).execute()
        EntityFTS.create(entity_id=entity_id, title=seg_title, content=seg_content)

    @staticmethod
    def remove(entity_id: str):
        from GYun.data.models.fts import EntityFTS  # 延迟导入
        EntityFTS.delete().where(EntityFTS.entity_id == entity_id).execute()

    @staticmethod
    def search(keyword: str, limit: int = 20, offset: int = 0):
        from GYun.data.models.fts import EntityFTS  # 延迟导入
        from peewee import SQL
        seg_kw = segment(keyword)
        query = (EntityFTS
                 .select(EntityFTS.entity_id, SQL('rank').alias('score'))
                 .where(EntityFTS.match(seg_kw))
                 .order_by(SQL('rank'))
                 .limit(limit)
                 .offset(offset))
        return [(row.entity_id, row.score) for row in query]

    @staticmethod
    def count(keyword: str) -> int:
        from GYun.data.models.fts import EntityFTS  # 延迟导入
        seg_kw = segment(keyword)
        return EntityFTS.select().where(EntityFTS.match(seg_kw)).count()
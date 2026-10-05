"""FTS5虚拟表"""
from playhouse.sqlite_ext import FTS5Model, SearchField

class EntityFTS(FTS5Model):
    entity_id = SearchField()
    title = SearchField()
    content = SearchField()

    class Meta:
        database = None  # 由外部绑定
        table_name = 'gyun_entities_fts'
        options = {'tokenize': 'unicode61'}

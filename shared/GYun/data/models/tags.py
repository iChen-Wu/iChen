"""标签关联表"""
from peewee import AutoField, TextField, ForeignKeyField, Model
from GYun.data.storage.database import db
from .entities import Entity

class EntityTag(Model):
    id = AutoField()
    entity = ForeignKeyField(Entity, backref='tags', field='entity_id', on_delete='CASCADE')  # ✅ 添加级联删除
    tag = TextField()

    class Meta:
        database = db
        table_name = 'gyun_entity_tags'
        indexes = (
            (('entity', 'tag'), True),  # 联合唯一
        )
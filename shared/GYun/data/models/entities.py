"""实体主表模型"""
from peewee import (
    TextField, IntegerField, BlobField, Model, SqliteDatabase
)
from playhouse.sqlite_ext import JSONField
from GYun.data.storage.database import db

class Entity(Model):
    entity_id = TextField(primary_key=True)
    type = TextField(index=True)
    title = TextField()
    content = TextField(null=True)
    priority = IntegerField(default=0)
    # V3.0 升格：source 重新定义为「应用标识」（不再作数据来源溯源），加索引加速按应用过滤
    source = TextField(null=True, index=True)
    resource_path = TextField(null=True)
    extra = JSONField(default={})
    related_ids = JSONField(default=list)
    is_deleted = IntegerField(default=0)
    create_time = IntegerField()
    update_time = IntegerField()

    class Meta:
        database = db
        table_name = 'gyun_entities'
        indexes = (
            (('type', 'is_deleted', 'create_time'), False),
        )

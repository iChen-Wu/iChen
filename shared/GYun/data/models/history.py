"""历史记录表（可选）"""
from peewee import AutoField, TextField, IntegerField, Model
from playhouse.sqlite_ext import JSONField
from GYun.data.storage.database import db

class EntityHistory(Model):
    history_id = AutoField()
    entity_id = TextField()
    snapshot = JSONField()
    change_type = TextField()
    change_time = IntegerField()

    class Meta:
        database = db
        table_name = 'gyun_entity_history'

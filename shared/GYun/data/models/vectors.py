import peewee
from .entities import Entity

class EntityVector(peewee.Model):
    """向量附属表：支持多分块、多模型、强级联删除"""
    id = peewee.AutoField()  # 自增主键，允许同一实体存多个向量
    entity = peewee.ForeignKeyField(Entity, backref='vectors', on_delete='CASCADE')  # 级联删除防线！
    chunk_index = peewee.IntegerField(default=0)  # 长文本分块序号
    embedding = peewee.BlobField()                # 序列化后的 numpy 数组
    dim = peewee.IntegerField()                   # 维度 (如 768)
    model_name = peewee.CharField(default='default')  # 模型标识 (防混用)
    create_time = peewee.IntegerField()

    class Meta:
        database = Entity._meta.database
        table_name = 'entity_vector'
        indexes = (
            (('entity', 'model_name', 'chunk_index'), True),  # 联合唯一约束
        )
"""知识图谱边模型：定义实体间带谓词的网状关系"""
import peewee
from .entities import Entity

class EntityEdge(peewee.Model):
    id = peewee.AutoField()
    # 🌟 级联删除防线：起点或终点实体硬删时，这条关系线自动物理消失
    source = peewee.ForeignKeyField(Entity, backref='out_edges', on_delete='CASCADE')
    target = peewee.ForeignKeyField(Entity, backref='in_edges', on_delete='CASCADE')
    relation_type = peewee.CharField(index=True)  # 🌟核心：关系谓词 (如 '学习了', '属于', '因果')
    weight = peewee.FloatField(default=1.0)        # 关系权重/置信度 (推理排序依据)
    properties = peewee.JSONField(default=dict)    # 关系属性 (如 {'score': 95, 'duration': '3个月'})
    create_time = peewee.IntegerField()

    class Meta:
        database = Entity._meta.database
        table_name = 'entity_edge'
        indexes = (
            # 防止重复建边：同起点、同终点、同谓词只能有一条线
            (('source', 'target', 'relation_type'), True),
        )
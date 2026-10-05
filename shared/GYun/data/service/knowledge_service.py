"""知识图谱服务：面向 Agent 的高级图谱操作 API"""
from GYun.data.storage.edge_storage import EdgeStorage

class KnowledgeService:
    def __init__(self, client):
        self.client = client

    def add_relation(self, source_id: str, target_id: str, relation_type: str, properties: dict = None, weight: float = 1.0) -> int:
        """
        建立带谓词的知识连线
        :param source_id: 起点实体ID (如: 张三)
        :param target_id: 终点实体ID (如: Python)
        :param relation_type: 关系谓词 (如: '学习了', '属于')
        :param properties: 关系属性 (如: {'score': 95})
        :param weight: 关系权重 (用于推理排序)
        """
        return EdgeStorage.add_edge(source_id, target_id, relation_type, properties, weight)
        
    # 未来可扩展：delete_relation, update_relation 等
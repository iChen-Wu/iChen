import time

import numpy as np
from ..models.vectors import EntityVector

class VectorStorage:
    MAX_BATCH_CALC = 5000  # 防OOM硬性防线

    @staticmethod
    def save_vector(entity_id: str, embedding: list, model_name: str = 'default', dim: int = 768, chunk_index: int = 0):
        vec_np = np.array(embedding, dtype=np.float32)
        EntityVector.insert(
            entity=entity_id,
            chunk_index=chunk_index,
            embedding=vec_np.tobytes(),
            dim=dim,
            model_name=model_name,
            create_time=int(time.time() * 1000)
        ).on_conflict(
            conflict_target=[EntityVector.entity, EntityVector.model_name, EntityVector.chunk_index],
            update={EntityVector.embedding: vec_np.tobytes(), EntityVector.dim: dim}
        ).execute()

    @staticmethod
    def batch_get_vectors(entity_ids: list, model_name: str = 'default') -> dict:
        """分批提取向量防溢出，返回 {entity_id: numpy_array}"""
        result = {}
        # 🟡1防线：如果候选集过大，强制切片
        batch_size = VectorStorage.MAX_BATCH_CALC
        for i in range(0, len(entity_ids), batch_size):
            batch_ids = entity_ids[i:i+batch_size]
            records = EntityVector.select(EntityVector.entity, EntityVector.embedding).where(
                (EntityVector.entity << batch_ids) & (EntityVector.model_name == model_name)
            )
            for rec in records:
                result[str(rec.entity_id)] = np.frombuffer(rec.embedding, dtype=np.float32)
        return result
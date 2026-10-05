import numpy as np
import math
import time

def cosine_similarity_batch(query_vec: np.ndarray, candidate_matrix: np.ndarray) -> np.ndarray:
    """批量计算余弦相似度"""
    if candidate_matrix.shape[0] == 0:
        return np.array([])
    query_norm = np.linalg.norm(query_vec)
    cand_norms = np.linalg.norm(candidate_matrix, axis=1)
    dots = np.dot(candidate_matrix, query_vec)
    return dots / (cand_norms * query_norm + 1e-8)  # 防除零

def time_decay_score(create_time_ms: int, lambda_decay: float = 0.01) -> float:
    """指数时间衰减 (替代危险的 1/log(t))"""
    days_elapsed = (time.time() * 1000 - create_time_ms) / (1000 * 3600 * 24)
    return math.exp(-lambda_decay * days_elapsed)  # 约70天半衰期
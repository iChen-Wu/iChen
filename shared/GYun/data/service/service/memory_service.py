import time
import logging
import numpy as np
from ..storage.vector_storage import VectorStorage
from ..storage.entity_storage import EntityStorage
from ..storage.fts_storage import FTSStorage
from ..service.query_service import QueryService
from ..utils.math_utils import cosine_similarity_batch, time_decay_score  # ✅ 移除未使用的 min_max_normalize

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, client):
        self.client = client  # 挂载主客户端

    def memorize(self, text: str, embedding: list = None, type: str = 'memory_long', extra: dict = None, **kwargs) -> str:
        """🟢2防线：绕过可能篡改文本的 before_create 钩子"""
        data = {'type': type, 'title': text[:50], 'content': text, 'extra': extra or {}}
        data.update(kwargs)
        # V3.0 应用隔离：跟随客户端应用上下文注入 source（全局模式不注入）
        client_source = getattr(self.client, 'source', None)
        if client_source is not None:
            data.setdefault('source', client_source)
        eid = EntityStorage.create(data)
        if embedding:
            VectorStorage.save_vector(eid, embedding)
        return eid

    def recall_memories(self, query_vector=None, query_text=None,
                         filters=None, top_k=5, threshold=0.5,
                         alpha=0.7, beta=0.2, gamma=0.1,
                         expand_relations=False) -> list:
        """
        混合召回引擎 (终极版：支持 GraphRAG 图谱扩展)
        """
        filters = filters or {}
        filters['is_deleted'] = 0
        candidate_ids = QueryService.get_candidate_ids(filters)
        if not candidate_ids:
            return []

        # 向量精排
        vec_scores = {eid: 0.0 for eid in candidate_ids}
        if query_vector:
            q_vec = np.array(query_vector, dtype=np.float32)
            cand_vecs = VectorStorage.batch_get_vectors(candidate_ids)
            if cand_vecs:
                cand_ids = list(cand_vecs.keys())
                cand_matrix = np.stack(list(cand_vecs.values()))
                sims = cosine_similarity_batch(q_vec, cand_matrix)
                for idx, eid in enumerate(cand_ids):
                    vec_scores[eid] = float(sims[idx])

        # 全文精排 (BM25) - 使用极大的 page_size 确保获取全部匹配项
        bm25_scores = {eid: 0.0 for eid in candidate_ids}
        if query_text:
            fts_results = self.client.fulltext_search(query_text, filters=filters, page_size=100000)
            for res in fts_results.get('list', []):
                if res['entity_id'] in bm25_scores:
                    bm25_scores[res['entity_id']] = res.get('score', 0.0)

        # 时间衰减
        time_scores = {eid: 0.0 for eid in candidate_ids}
        entities_list = self.client.get_entities_batch(candidate_ids)
        entities_data = {e['entity_id']: e for e in entities_list}
        for eid, entity in entities_data.items():
            if eid in time_scores:
                time_scores[eid] = time_decay_score(entity['create_time'])

        # 归一化与融合
        norm_vec = {eid: max(0.0, vec_scores[eid]) for eid in candidate_ids}
        max_bm25 = max(bm25_scores.values()) if bm25_scores else 1.0
        if max_bm25 <= 0:
            max_bm25 = 1.0
        norm_bm25 = {eid: bm25_scores[eid] / max_bm25 for eid in candidate_ids}
        norm_time = {eid: time_scores[eid] for eid in candidate_ids}

        final_ranked = []
        for eid in candidate_ids:
            final_score = (alpha * norm_vec[eid]) + (beta * norm_bm25[eid]) + (gamma * norm_time[eid])
            if final_score >= threshold:
                final_ranked.append({
                    'entity_id': eid,
                    'content': entities_data.get(eid, {}).get('content', ''),
                    'extra': entities_data.get(eid, {}).get('extra', {}),
                    'relevance_score': round(final_score, 4),
                    'final_score_detail': {
                        'vector': round(norm_vec[eid], 3),
                        'bm25': round(norm_bm25[eid], 3),
                        'time_decay': round(norm_time[eid], 3)
                    }
                })

        final_ranked.sort(key=lambda x: x['relevance_score'], reverse=True)
        results = final_ranked[:top_k]

        # GraphRAG 图谱扩展
        if expand_relations and results:
            from GYun.data.storage.edge_storage import EdgeStorage
            for item in results:
                eid = item['entity_id']
                out_edges = EdgeStorage.query_edges(source_id=eid)
                in_edges = EdgeStorage.query_edges(target_id=eid)
                item['expanded_knowledge'] = {
                    'out_relations': out_edges,
                    'in_relations': in_edges
                }

        return results

    # 唯一正确的 condense_memories 定义（已删除错误版本）
    def condense_memories(self, source_ids: list, condensed_text: str, condensed_embedding: list = None) -> str:
        """🔴3修补：废弃软删除，改用归档状态，保全血缘图谱"""
        new_eid = self.memorize(text=condensed_text, embedding=condensed_embedding, type='memory_long')
        for old_id in source_ids:
            old_entity = self.client.get_entity(old_id)
            old_extra = old_entity.get('extra', {}) if isinstance(old_entity, dict) else {}
            old_extra.update({'status': 'archived', 'condensed_into': new_eid})
            self.client.update_entity(old_id, {'extra': old_extra})
        new_extra = {'status': 'active', 'condensed_from': source_ids}
        self.client.update_entity(new_eid, {'related_ids': source_ids, 'extra': new_extra})
        return new_eid
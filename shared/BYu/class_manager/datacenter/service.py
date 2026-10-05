"""
service.py - 数据中心核心操作（支持可配置类型白名单）
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from GYun.data.client import GyunClient
from GYun.core.constants import PROJECT_ROOT, CONFIG_DIR

logger = logging.getLogger(__name__)

# 配置文件路径（V3.0.0 起配置归位于 data/config/）
CONFIG_PATH = CONFIG_DIR / "class_datacenter.json"
DEFAULT_ALLOWED_TYPES = [
    "person",
    "class_log",
    "song",
    "duty",
    "rule",
    "weekly_report",
    "pending_correction",
    "correction_pending",
]


def _load_config() -> dict:
    """加载配置文件"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}，使用默认配置")
    return {"allowed_types": DEFAULT_ALLOWED_TYPES.copy()}


def _save_config(config: dict) -> bool:
    """保存配置文件"""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False


def get_allowed_types() -> List[str]:
    """获取当前白名单"""
    config = _load_config()
    return config.get("allowed_types", DEFAULT_ALLOWED_TYPES.copy())


def add_allowed_type(type_name: str) -> bool:
    """添加类型到白名单"""
    config = _load_config()
    allowed = config.get("allowed_types", [])
    if type_name in allowed:
        return True
    allowed.append(type_name)
    config["allowed_types"] = allowed
    return _save_config(config)


def remove_allowed_type(type_name: str) -> bool:
    """从白名单移除类型"""
    config = _load_config()
    allowed = config.get("allowed_types", [])
    if type_name not in allowed:
        return True
    # 不允许移除所有类型（至少保留一个）
    if len(allowed) <= 1:
        logger.warning("至少保留一个类型")
        return False
    allowed.remove(type_name)
    config["allowed_types"] = allowed
    return _save_config(config)


class DataCenterService:
    """数据中心服务类"""

    @staticmethod
    def get_type_stats() -> Dict[str, int]:
        """获取各类型记录数量统计（仅白名单中的类型）"""
        client = GyunClient()
        # 一次性取足够多的数据（或者遍历所有页）
        # 设置 page_size 为 10000，确保能拿到所有数据
        result = client.query_entities({}, page=1, page_size=10000)
        entities = result.get("list", [])

        allowed = get_allowed_types()
        stats = {}
        for ent in entities:
            t = ent.get("type", "unknown") if isinstance(ent, dict) else "unknown"
            if t in allowed:
                stats[t] = stats.get(t, 0) + 1

        stats["total"] = sum(stats.values())
        stats["allowed_count"] = len(allowed)
        return stats
    
    @staticmethod
    def list_entities(
        page: int = 1,
        page_size: int = 20,
        order_by: str = "created_at desc",
        type_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页获取 Entity 列表（仅白名单中的类型）"""
        client = GyunClient()
        allowed = get_allowed_types()

        # 如果指定了 type_filter，检查是否在白名单中
        if type_filter and type_filter not in allowed:
            return {
                "total": 0,
                "page": page,
                "page_size": page_size,
                "items": [],
                "error": f"类型 '{type_filter}' 不在白名单中"
            }

        # 构造筛选条件
        filters = {}
        if type_filter:
            filters["type"] = type_filter

        # 获取数据
        result = client.query_entities(filters, page=page, page_size=page_size)
        entities = result.get("list", [])
        total = result.get("total", 0)  # API 返回的真实总数

        # 如果没有指定类型，需要内存过滤白名单
        # 但此时 total 是全部数据的总数，不是过滤后的总数
        # 所以这种情况下，我们禁用分页，直接取全部数据
        if not type_filter:
            # 取全部数据，然后在内存中过滤和分页
            all_result = client.query_entities({}, page=1, page_size=10000)
            all_entities = all_result.get("list", [])
            filtered = [e for e in all_entities if e.get("type") in allowed]
            total = len(filtered)
            # 手动分页
            start = (page - 1) * page_size
            end = start + page_size
            entities = filtered[start:end]
        else:
            # 有类型筛选，使用 API 分页结果
            # 但需要确保 entities 都在白名单中（已有 type_filter 保障）
            pass

        # 排序
        reverse = "desc" in order_by
        field = order_by.replace(" desc", "").replace(" asc", "").strip()
        if entities and field in ("created_at", "title", "type"):
            entities.sort(key=lambda x: x.get(field, ""), reverse=reverse)

        # 提取显示字段
        display_items = []
        for item in entities:
            display_items.append({
                "entity_id": item.get("entity_id"),
                "type": item.get("type"),
                "title": item.get("title"),
                "tags": item.get("tags", []),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
            })

        return {
            "total": total,  # 真实总数
            "page": page,
            "page_size": page_size,
            "items": display_items,
        }

    @staticmethod
    def get_entity(entity_id: str) -> Optional[Dict[str, Any]]:
        """查看单条记录的完整详情"""
        client = GyunClient()
        
        # 直接使用 get_entity 方法，而不是 query_entities
        try:
            entity = client.get_entity(entity_id)
            return entity
        except Exception as e:
            # 如果记录不存在，GYunClient.get_entity 会抛异常
            # 但具体异常类型需要确认，暂时用 try-except
            return None

    @staticmethod
    def create_entity(
        type_: str,
        title: str,
        content: str = "",
        tags: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """新增一条记录"""
        # 检查类型是否在白名单中
        allowed = get_allowed_types()
        if type_ not in allowed:
            logger.warning(f"类型 '{type_}' 不在白名单中，但仍可创建（需手动添加）")
            # 自动添加到白名单
            add_allowed_type(type_)
            logger.info(f"已自动将 '{type_}' 添加到白名单")

        client = GyunClient()
        entity_data = {
            "type": type_,
            "title": title,
            "content": content or "",
            "tags": tags or [],
            "extra": extra or {},
        }

        try:
            entity_id = client.create_entity(entity_data)
            logger.info(f"数据中心: 创建记录 {entity_id} (type={type_})")
            return entity_id
        except Exception as e:
            logger.error(f"数据中心: 创建记录失败 - {e}")
            return None

    @staticmethod
    def update_entity(
        entity_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """修改记录"""
        client = GyunClient()

        existing = DataCenterService.get_entity(entity_id)
        if not existing:
            logger.warning(f"数据中心: 记录不存在 {entity_id}")
            return False

        updates = {}
        if title is not None:
            updates["title"] = title
        if content is not None:
            updates["content"] = content
        if tags is not None:
            updates["tags"] = tags
        if extra is not None:
            updates["extra"] = extra

        if not updates:
            return True

        try:
            client.update_entity(entity_id, updates)
            logger.info(f"数据中心: 更新记录 {entity_id}")
            return True
        except Exception as e:
            logger.error(f"数据中心: 更新记录失败 {entity_id} - {e}")
            return False

    @staticmethod
    def delete_entity(entity_id: str) -> bool:
        """硬删除一条记录"""
        client = GyunClient()
        try:
            client.delete_entity(entity_id, hard=True)
            logger.info(f"数据中心: 删除记录 {entity_id}")
            return True
        except Exception as e:
            logger.error(f"数据中心: 删除记录失败 {entity_id} - {e}")
            return False

    @staticmethod
    def search_entities(
        type_filter: Optional[str] = None,
        tag_filter: Optional[str] = None,
        title_keyword: Optional[str] = None,
        extra_field: Optional[str] = None,
        extra_value: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """搜索/筛选记录"""
        client = GyunClient()
        filters = {}

        if type_filter:
            filters["type"] = type_filter
        if tag_filter:
            filters["tags_contains"] = tag_filter
        if extra_field and extra_value:
            filters[f"extra_{extra_field}"] = extra_value

        result = client.query_entities(filters, page=1, page_size=10000)
        entities = result.get("list", [])

        # 强制类型过滤（兜底，防止 query_entities 的 type 过滤失效）
        if type_filter:
            filtered_entities = []
            for ent in entities:
                ent_type = ent.get("type") if isinstance(ent, dict) else None
                if ent_type == type_filter:
                    filtered_entities.append(ent)
            entities = filtered_entities

        # 如果指定了 extra_field 和 extra_value，做包含匹配
        if extra_field and extra_value:
            keyword = extra_value
            filtered = []
            for ent in entities:
                extra = ent.get("extra", {})
                val = extra.get(extra_field)
                if val is None:
                    continue
                if isinstance(val, str):
                    if keyword in val:
                        filtered.append(ent)
                elif isinstance(val, list):
                    if any(keyword in str(item) for item in val):
                        filtered.append(ent)
                else:
                    if keyword in str(val):
                        filtered.append(ent)
            entities = filtered

        # 如果只有 extra_value 没有 extra_field，在所有 extra 字段中搜索
        if extra_value and not extra_field:
            keyword = extra_value
            filtered = []
            skip_keys = ["source_image", "raw_llm_output"]
            for ent in entities:
                extra = ent.get("extra", {})
                found = False
                for key, val in extra.items():
                    if key.startswith("_"):
                        continue
                    if key in skip_keys:
                        continue
                    if val is None:
                        continue
                    if isinstance(val, str):
                        if keyword in val:
                            found = True
                            break
                    elif isinstance(val, list):
                        if any(keyword in str(item) for item in val):
                            found = True
                            break
                    else:
                        if keyword in str(val):
                            found = True
                            break
                if found:
                    filtered.append(ent)
            entities = filtered

        if title_keyword:
            keyword = title_keyword.lower()
            entities = [
                e for e in entities
                if keyword in e.get("title", "").lower()
            ]

        entities = entities[:limit]

        result_list = []
        for item in entities:
            result_list.append({
                "entity_id": item.get("entity_id"),
                "type": item.get("type"),
                "title": item.get("title"),
                "tags": item.get("tags", []),
                "created_at": item.get("created_at"),
                "extra": item.get("extra", {}),
            })

        return result_list

    @staticmethod
    def batch_delete(entity_ids: List[str]) -> int:
        """批量删除记录"""
        client = GyunClient()
        success_count = 0
        for eid in entity_ids:
            try:
                client.delete_entity(eid, hard=True)
                success_count += 1
                logger.info(f"数据中心: 批量删除 {eid}")
            except Exception as e:
                logger.error(f"数据中心: 批量删除失败 {eid} - {e}")
        return success_count

    @staticmethod
    def batch_update_tags(
        entity_ids: List[str],
        tags: List[str],
        mode: str = "overwrite",
    ) -> int:
        """批量修改标签"""
        client = GyunClient()
        success_count = 0

        for eid in entity_ids:
            try:
                existing = DataCenterService.get_entity(eid)
                if not existing:
                    continue

                old_tags = existing.get("tags", [])

                if mode == "overwrite":
                    new_tags = tags
                elif mode == "append":
                    new_tags = old_tags + [t for t in tags if t not in old_tags]
                elif mode == "remove":
                    new_tags = [t for t in old_tags if t not in tags]
                else:
                    continue

                client.update_entity(eid, {"tags": new_tags})
                success_count += 1
                logger.info(f"数据中心: 批量改标签 {eid} ({mode})")
            except Exception as e:
                logger.error(f"数据中心: 批量改标签失败 {eid} - {e}")

        return success_count

    @staticmethod
    def get_allowed_types() -> List[str]:
        """获取白名单"""
        return get_allowed_types()

    @staticmethod
    def add_allowed_type(type_name: str) -> bool:
        """添加类型到白名单"""
        return add_allowed_type(type_name)

    @staticmethod
    def remove_allowed_type(type_name: str) -> bool:
        """从白名单移除类型"""
        return remove_allowed_type(type_name)
"""数据中心 App - 逻辑入口

外壳化 shared/BYu/class_manager/datacenter：业务逻辑不重写，这里只做 action 路由。
依赖：BYu.class_manager.datacenter.service.DataCenterService（GYun.data SQLite，source 全局）。
类型白名单读 config/class_datacenter.json。

run(params) 为 App 规范固定入口，params 形如 {"action": "...", "payload": {...}}。
"""
from typing import Any, Dict, List, Optional


def _service():
    """惰性加载 datacenter 业务层，import 失败时给出可读错误。"""
    from BYu.class_manager.datacenter import service as datacenter_service
    return datacenter_service


def _as_list(value: Any) -> Optional[List[str]]:
    """把界面传来的标签/ID 归一成字符串列表（None 表示"未提供、不改"）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return [t.strip() for t in value.replace("，", ",").split(",") if t.strip()]
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return None


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    action = (params.get("action") or "list").strip()
    payload = params.get("payload") or {}

    try:
        dc = _service()
    except Exception as e:  # 库缺失/环境问题：不拖垮总台
        return {"ok": False, "error": f"datacenter 业务库加载失败: {e}"}

    S = dc.DataCenterService

    try:
        # ---------- 视图 ----------
        if action == "stats":
            return {"ok": True, "data": S.get_type_stats()}

        if action == "types":
            return {"ok": True, "data": {"allowed": S.get_allowed_types()}}

        if action == "list":
            page = int(payload.get("page") or 1)
            page_size = int(payload.get("page_size") or 20)
            type_filter = (payload.get("type") or "").strip() or None
            order_by = (payload.get("order_by") or "created_at desc").strip()
            data = S.list_entities(page=page, page_size=page_size,
                                   order_by=order_by, type_filter=type_filter)
            if data.get("error"):
                return {"ok": False, "error": data["error"]}
            return {"ok": True, "data": data, "message": f"共 {data.get('total', 0)} 条"}

        if action == "search":
            items = S.search_entities(
                type_filter=(payload.get("type") or "").strip() or None,
                tag_filter=(payload.get("tag") or "").strip() or None,
                title_keyword=(payload.get("keyword") or "").strip() or None,
                extra_field=(payload.get("extra_field") or "").strip() or None,
                extra_value=(payload.get("extra_value") or "").strip() or None,
                limit=int(payload.get("limit") or 100),
            )
            return {"ok": True, "data": {"items": items, "total": len(items)},
                    "message": f"命中 {len(items)} 条"}

        if action == "view":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            entity = S.get_entity(entity_id)
            if not entity:
                return {"ok": False, "error": f"记录不存在: {entity_id}"}
            return {"ok": True, "data": entity}

        # ---------- 增删改 ----------
        if action == "create":
            type_ = (payload.get("type") or "").strip()
            title = (payload.get("title") or "").strip()
            if not type_ or not title:
                return {"ok": False, "error": "缺少 type / title"}
            extra = payload.get("extra")
            if isinstance(extra, str):
                import json
                extra = json.loads(extra) if extra.strip() else None
            entity_id = S.create_entity(
                type_=type_,
                title=title,
                content=payload.get("content") or "",
                tags=_as_list(payload.get("tags")) or [],
                extra=extra if isinstance(extra, dict) else None,
            )
            if not entity_id:
                return {"ok": False, "error": "创建失败（类型未入白名单或写入异常）"}
            return {"ok": True, "data": {"entity_id": entity_id},
                    "message": f"已创建 {entity_id}"}

        if action == "update":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            extra = payload.get("extra")
            if isinstance(extra, str):
                import json
                extra = json.loads(extra) if extra.strip() else None
            ok = S.update_entity(
                entity_id,
                title=None if payload.get("title") is None else str(payload.get("title")),
                content=None if payload.get("content") is None else str(payload.get("content")),
                tags=_as_list(payload.get("tags")),
                extra=extra if isinstance(extra, dict) else None,
            )
            return {"ok": bool(ok), "message": "已保存" if ok else "保存失败（记录不存在？）"}

        if action == "delete":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            ok = S.delete_entity(entity_id)
            return {"ok": bool(ok), "message": "已删除" if ok else "删除失败"}

        # ---------- 批量 ----------
        if action == "batch_delete":
            ids = _as_list(payload.get("entity_ids")) or []
            if not ids:
                return {"ok": False, "error": "未选择记录"}
            n = S.batch_delete(ids)
            return {"ok": True, "data": {"deleted": n}, "message": f"已删除 {n} 条"}

        if action == "batch_tags":
            ids = _as_list(payload.get("entity_ids")) or []
            tags = _as_list(payload.get("tags")) or []
            mode = (payload.get("mode") or "append").strip()
            if not ids:
                return {"ok": False, "error": "未选择记录"}
            if mode not in ("overwrite", "append", "remove"):
                return {"ok": False, "error": f"未知 mode: {mode}"}
            n = S.batch_update_tags(ids, tags, mode=mode)
            return {"ok": True, "data": {"updated": n}, "message": f"已更新 {n} 条标签"}

        # ---------- 类型白名单 ----------
        if action == "add_type":
            type_name = (payload.get("type_name") or "").strip()
            if not type_name:
                return {"ok": False, "error": "缺少 type_name"}
            ok = S.add_allowed_type(type_name)
            return {"ok": bool(ok), "message": f"已加入白名单: {type_name}"}

        if action == "remove_type":
            type_name = (payload.get("type_name") or "").strip()
            if not type_name:
                return {"ok": False, "error": "缺少 type_name"}
            ok = S.remove_allowed_type(type_name)
            return {"ok": bool(ok),
                    "message": f"已移除: {type_name}" if ok else "移除失败（至少保留一个类型）"}

        return {"ok": False, "error": f"未知 action: {action}"}
    except Exception as e:
        return {"ok": False, "error": f"{action} 执行异常: {type(e).__name__}: {e}"}


if __name__ == "__main__":
    import json
    print(json.dumps(run({"action": "stats"}), ensure_ascii=False, default=str))

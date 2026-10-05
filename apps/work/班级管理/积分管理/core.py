"""积分管理 App - 逻辑入口

外壳化 shared/BYu/class_manager/points：业务逻辑不重写，这里只做 action 路由。
流程与 CLI V3.0 一致（**库为中心**，状态落在 GYun.data，中断后可从库恢复继续）：

    识别/导入 → 校验 → 应用编辑 → 匹配 → 上传

因此本入口**无模块级状态**（每次 action 重新加载 core.py 也不影响流程），
所有中间状态都在 points_record / points_edit 的 entity_status 里。

run(params) 为 App 规范固定入口，params 形如 {"action": "...", "payload": {...}}。
"""
import json
from typing import Any, Dict, List, Optional


def _processor():
    """业务处理器（无状态；verbose/debug 关掉，避免 CLI 式 print 串进前端）。"""
    from BYu.class_manager.points.points_core import PointsProcessor
    return PointsProcessor(verbose=False, debug=False)


def _store():
    from BYu.class_manager.points import points_store as store
    return store


def _as_list(value: Any) -> Optional[List[str]]:
    """逗号/中文逗号分隔字符串 → 列表；已是列表则原样归一。"""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return [t.strip() for t in str(value).replace("，", ",").split(",") if t.strip()]


def _persons_of(entity: Dict[str, Any]) -> List[str]:
    """points_record.content 存的是 JSON 文本形式的人员列表。"""
    raw = entity.get("content")
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str) and raw.strip().startswith("["):
        try:
            val = json.loads(raw)
            return val if isinstance(val, list) else [raw]
        except Exception:
            pass
    return [raw] if raw else []


def _record_brief(entity: Dict[str, Any]) -> Dict[str, Any]:
    """points_record 实体 → 界面用的精简结构"""
    extra = entity.get("extra") or {}
    return {
        "entity_id": entity.get("entity_id"),
        "id": extra.get("id"),
        "event": entity.get("title"),
        "persons": _persons_of(entity),
        "score": extra.get("score"),
        "status": extra.get("entity_status"),
        "date": extra.get("date"),
        "recorder": extra.get("recorder"),
        "remark": extra.get("remark"),
        "error": extra.get("error_info"),
    }


def _edit_brief(entity: Dict[str, Any]) -> Dict[str, Any]:
    """points_edit 实体 → 界面用的精简结构"""
    extra = entity.get("extra") or {}
    return {
        "entity_id": entity.get("entity_id"),
        "id": extra.get("id"),
        "title": entity.get("title"),
        "operation": extra.get("operation"),
        "target_seq": extra.get("target_seq"),
        "status": extra.get("entity_status"),
        "persons": _persons_of(entity),
        "error": extra.get("error_info"),
    }


def _created_msg(created: int, skipped: int, verb: str) -> str:
    """落库结果提示：带上去重跳过的条数（同 id 已在库中不会重复落库）。"""
    msg = f"{verb} {created} 条（待校验）"
    if skipped:
        msg += f"，跳过 {skipped} 条重复（同 id 已存在）"
    return msg


def _err_from(result: Dict[str, Any], fallback: str) -> str:
    """业务层返回的 error 可能是 str / dict / None，统一成可读文本。"""
    e = result.get("error")
    if not e:
        info = result.get("error_info")
        return json.dumps(info, ensure_ascii=False) if info else fallback
    return e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    action = (params.get("action") or "status").strip()
    payload = params.get("payload") or {}

    try:
        store = _store()
    except Exception as e:  # 库缺失/环境问题：不拖垮总台
        return {"ok": False, "error": f"points 业务库加载失败: {e}"}

    try:
        # ---------- 概览 / 查询 ----------
        if action == "status":
            counts = store.count_by_status()
            return {"ok": True, "data": counts, "message": f"库中共 {counts.get('total', 0)} 条积分记录"}

        if action == "list":
            status = (payload.get("status") or "").strip() or None
            entities = store.query_records(
                status=status,
                date=(payload.get("date") or "").strip() or None,
                page_size=int(payload.get("limit") or 200),
            )
            items = [_record_brief(e) for e in entities]
            return {"ok": True, "data": {"items": items, "total": len(items)},
                    "message": f"共 {len(items)} 条"}

        if action == "edits":
            status = (payload.get("status") or "").strip() or None
            entities = store.query_edits(status=status, order="asc")
            items = [_edit_brief(e) for e in entities]
            return {"ok": True, "data": {"items": items, "total": len(items)},
                    "message": f"共 {len(items)} 条编辑请求"}

        if action == "stats":
            data = store.statistics(date_start=(payload.get("date_start") or "").strip() or None,
                                    date_end=(payload.get("date_end") or "").strip() or None)
            return {"ok": True, "data": data}

        # ---------- 导入（识别 / JSON） ----------
        if action == "recognize":
            paths = _as_list(payload.get("paths")) or []
            if not paths:
                return {"ok": False, "error": "未选择图片"}
            type_ = (payload.get("type") or "班务日志").strip()
            r = _processor().recognize_and_store(paths, type=type_)
            if not r.get("success"):
                return {"ok": False, "error": _err_from(r, "识别失败或无有效数据")}
            return {"ok": True,
                    "data": {"created": r.get("created"), "skipped": r.get("skipped", 0)},
                    "message": _created_msg(r.get("created", 0), r.get("skipped", 0), "识别并落库")}

        if action == "recognize_edits":
            paths = _as_list(payload.get("paths")) or []
            if not paths:
                return {"ok": False, "error": "未选择图片"}
            r = _processor().recognize_edits_and_store(paths, type=(payload.get("type") or "修改单").strip())
            if not r.get("success"):
                return {"ok": False, "error": _err_from(r, "未识别到编辑指令")}
            return {"ok": True, "data": {"created": r.get("created")},
                    "message": f"识别并落库 {r.get('created', 0)} 条编辑请求"}

        if action == "import_json":
            text = (payload.get("json") or "").strip()
            if not text:
                return {"ok": False, "error": "未提供 JSON 内容"}
            data = json.loads(text)
            units = data if isinstance(data, list) else (data.get("data") or [])
            if not units:
                return {"ok": False, "error": "JSON 中没有可导入的数据（应为列表或含 data 键）"}
            stats: Dict[str, Any] = {}
            pairs = store.create_points_records(units, initial_status=store.STATUS_PENDING_REVIEW,
                                                stats=stats)
            return {"ok": True,
                    "data": {"created": len(pairs), "skipped": stats.get("skipped", 0)},
                    "message": _created_msg(len(pairs), stats.get("skipped", 0), "导入并落库")}
        # ---------- 流水线（对应 CLI 菜单 4：应用编辑 → 校验 → 匹配） ----------
        if action == "validate":
            p = _processor()
            re_ = p.validate_edits_store()
            rr = p.validate_store()
            return {"ok": True,
                    "data": {"edits": re_, "records": rr},
                    "message": f"编辑校验 {re_.get('ok', 0)}/{re_.get('checked', 0)}；"
                               f"记录校验 {rr.get('ok', 0)}/{rr.get('checked', 0)}"
                               + (f"，错误 {rr.get('errors', 0)} 条待纠错" if rr.get("errors") else "")}

        if action == "apply_edits":
            r = _processor().apply_edits_store()
            return {"ok": True, "data": r,
                    "message": f"编辑应用：成功 {r.get('applied', 0)} 条，失败 {r.get('failed', 0)} 条"}

        if action == "match":
            r = _processor().match_store()
            if r.get("failed"):
                return {"ok": False, "data": r,
                        "error": f"{r['failed']} 个事件匹配失败，请先纠错"}
            return {"ok": True, "data": r, "message": f"匹配成功 {r.get('matched', 0)} 条"}

        if action == "pipeline":
            p = _processor()
            ra = p.apply_edits_store()
            rv = p.validate_store()
            if rv.get("errors"):
                return {"ok": False, "data": {"applied": ra, "validated": rv},
                        "error": f"校验发现 {rv['errors']} 处错误，请先在下方纠错"}
            rm = p.match_store()
            if rm.get("failed"):
                return {"ok": False, "data": {"applied": ra, "validated": rv, "matched": rm},
                        "error": f"{rm['failed']} 个事件匹配失败，请先纠错"}
            return {"ok": True, "data": {"applied": ra, "validated": rv, "matched": rm},
                    "message": f"已应用 {ra.get('applied', 0)} 条编辑、匹配 {rm.get('matched', 0)} 条，可以上传了"}

        if action == "upload":
            r = _processor().upload_store()
            if r.get("success"):
                return {"ok": True, "data": r, "message": f"上传成功 {r.get('uploaded', 0)} 条"}
            return {"ok": False, "data": r, "error": _err_from(r, "上传失败")}

        # ---------- 纠错 ----------
        if action == "correct_record":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            score = payload.get("score")
            ok = store.correct_record(
                entity_id,
                title=None if payload.get("event") is None else str(payload.get("event")),
                persons=_as_list(payload.get("persons")),
                score=None if score in (None, "") else float(score),
                recorder=None if payload.get("recorder") is None else str(payload.get("recorder")),
                remark=None if payload.get("remark") is None else str(payload.get("remark")),
                date=(payload.get("date") or "").strip() or None,
            )
            return {"ok": bool(ok), "message": "已修正，待重新校验" if ok else "修正失败（记录不存在？）"}

        if action == "correct_edit":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            ok = store.correct_edit(
                entity_id,
                new_line=(payload.get("new_line") or "").strip() or None,
                event=None if payload.get("event") is None else str(payload.get("event")),
                persons=_as_list(payload.get("persons")),
                remark=None if payload.get("remark") is None else str(payload.get("remark")),
            )
            return {"ok": bool(ok), "message": "已修正，待重新校验" if ok else "修正失败（编辑请求不存在？）"}

        if action == "cancel_record":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            ok = store.cancel_record(entity_id)
            return {"ok": bool(ok), "message": "已取消该条" if ok else "取消失败"}

        if action == "cancel_edit":
            entity_id = (payload.get("entity_id") or "").strip()
            if not entity_id:
                return {"ok": False, "error": "缺少 entity_id"}
            ok = store.cancel_edit(entity_id)
            return {"ok": bool(ok), "message": "已取消该条" if ok else "取消失败"}

        if action == "delete_records":
            # 批量删除（软删，is_deleted=1，列表不再显示）：用于清理重复落库等场景
            ids = _as_list(payload.get("entity_ids")) or []
            if not ids:
                return {"ok": False, "error": "未选择要删除的记录"}
            deleted, failed = 0, []
            for eid in ids:
                if store.soft_delete_record(eid):
                    deleted += 1
                else:
                    failed.append(eid)
            if not deleted:
                return {"ok": False, "error": f"{len(ids)} 条记录删除失败（记录不存在或已删除？）"}
            msg = f"已删除 {deleted} 条记录"
            if failed:
                msg += f"，{len(failed)} 条失败"
            return {"ok": True, "data": {"deleted": deleted, "failed": len(failed)}, "message": msg}

        if action == "reset":
            # 危险操作：清空库中积分记录与编辑请求（界面上必须二次确认）
            if not payload.get("confirm"):
                return {"ok": False, "error": "未确认，已中止"}
            r = store.reset_all_data()
            return {"ok": bool(r.get("success", True)), "data": r,
                    "message": "已清空全部积分数据" if r.get("success", True) else _err_from(r, "清空失败")}

        return {"ok": False, "error": f"未知 action: {action}"}
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"JSON 解析失败: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"{action} 执行异常: {type(e).__name__}: {e}"}


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run({"action": "status"}), ensure_ascii=False, default=str))

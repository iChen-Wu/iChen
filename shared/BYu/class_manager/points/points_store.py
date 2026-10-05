# points_store.py
# =============================================================================
# 模块：积分持久化层（基于 GYun.data 实体存储）
# =============================================================================
# 功能：
#   1. person 映射加载（pinyin/name -> entity_id），用于 related_ids 关联学生
#   2. points_record 实体创建：识别结果落库，防止内存数据丢失
#   3. 按 entity_status / 日期查询记录，支持中断后从库恢复继续处理
#   4. 状态流转：pending_review -> pending_match -> matched -> uploaded
#   5. error_info 读写（纠错时按 entity_status + error_info 定位问题）
#
# 实体格式（与 GYun.data.Entity 模型对应）：
#   person 实体：
#       type="person", title=姓名, extra={"name": 姓名, "pinyin": 缩写,
#                                         "student_id": 学号, "gender": 性别}
#   points_record 实体：
#       type="points_record", title=事件名,
#       content=人员原始值的 JSON 文本（GYun.data content 列为 TextField，
#               list 以 JSON 文本存储，读取时由 record_to_unit 还原为 list）,
#       extra={"id": 时间+序号, "date": YYYY-MM-DD, "score": 分数或null,
#              "entity_status": 状态, "recorder": 记录人, "remark": 备注,
#              "error_info": 纠错信息或null},
#       related_ids=[person.entity_id, ...]
# =============================================================================

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from GYun.data.client import GyunClient

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ============================================================
# 常量
# ============================================================
SOURCE = "class_manager"          # 应用标识（所有实体统一）
PERSON_TYPE = "person"            # 学生总表实体类型
RECORD_TYPE = "points_record"     # 积分记录实体类型
EDIT_TYPE = "points_edit"         # 纸质编辑指令实体类型

# 记录状态机
STATUS_PENDING_REVIEW = "pending_review"   # 刚识别入库 / 校验发现错误待纠错
STATUS_PENDING_MATCH = "pending_match"     # 校验通过，待匹配分数
STATUS_MATCHED = "matched"                 # 已匹配分数，待上传
STATUS_UPLOADED = "uploaded"               # 已上传

# 编辑指令状态机（对齐流程：pending_review -> approved -> applied）
STATUS_APPROVED = "approved"               # 编辑校验通过，待应用到目标记录
STATUS_APPLIED = "applied"                 # 已应用到目标 points_record
STATUS_CANCELLED = "cancelled"             # 用户纠错时取消该条

# error_info 错误类型
ERROR_PERSON_NOT_FOUND = "person_not_found"
ERROR_EVENT_INVALID = "event_invalid"
ERROR_RECORDER_NOT_FOUND = "recorder_not_found"
ERROR_DATE_INVALID = "date_invalid"
ERROR_SCORE_INVALID = "score_invalid"


def get_client() -> GyunClient:
    """获取应用隔离的 GyunClient（source=class_manager）"""
    return GyunClient(source=SOURCE)


# ============================================================
# 1. person 映射加载
# ============================================================

def load_person_map() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    从库加载全部 person 实体，返回两个映射：
        by_pinyin: 缩写 -> entity_id（如 "ZBY" -> "...")
        by_name:   全名 -> entity_id（如 "张博宇" -> "...")
    """
    client = get_client()
    result = client.query_entities({"type": PERSON_TYPE}, page=1, page_size=10000)
    by_pinyin: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    for ent in result.get("list", []):
        eid = ent.get("entity_id")
        if not eid:
            continue
        extra = ent.get("extra") or {}
        pinyin = extra.get("pinyin")
        name = extra.get("name")
        if pinyin:
            by_pinyin[pinyin] = eid
        if name:
            by_name[name] = eid
    logger.info(f"加载 person 映射: 缩写 {len(by_pinyin)} 个, 全名 {len(by_name)} 个")
    return by_pinyin, by_name


def resolve_person_ids(
    names: List[str],
    by_pinyin: Dict[str, str],
    by_name: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """
    将人员原始值（缩写/全名）解析为 person entity_id 列表。

    入参：
        names: 人员原始值列表（识别结果，可能是缩写、全名或错误字符串）
        by_pinyin / by_name: load_person_map 的返回值

    出参：
        (person_ids, invalid_names)
            person_ids:   成功匹配的 person.entity_id 列表（保持 names 顺序）
            invalid_names: 未匹配的名字列表
    """
    person_ids: List[str] = []
    invalid: List[str] = []
    for name in names:
        if not name:
            continue
        # 缩写统一转大写再匹配（大模型可能识别成小写）
        eid = by_pinyin.get(name.upper()) or by_name.get(name)
        if eid:
            person_ids.append(eid)
        else:
            invalid.append(name)
    return person_ids, invalid


# ============================================================
# 2. points_record 创建（识别结果落库）
# ============================================================

def unit_to_record_data(
    unit: Dict[str, Any],
    person_ids: List[str],
    initial_status: str = STATUS_PENDING_REVIEW,
) -> Dict[str, Any]:
    """
    将内存单体（data_parser 输出格式）转换为 points_record 实体数据。

    入参：
        unit: 单体，形如 {"Operation": "event", "id": "20260807003",
                          "data": {"row_num": 3, "recorder": "HHR",
                                   "date": "2026-08-07", "item_event": "早读迟到",
                                   "remark": "已提醒两次", "person_list": ["ZBY1", "WGF"]}}
        person_ids: 已解析的 related_ids（对应学生的 entity_id）
        initial_status: 初始状态，默认 pending_review

    出参：
        dict - create_entity 可直接接受的实体数据
    """
    inner = unit.get("data", {})
    person_list = inner.get("person_list", [])
    if not isinstance(person_list, list):
        person_list = []

    # 注意：GYun.data 的 content 列为 TextField（且 FTS 分词要求字符串），
    # 人员列表以 JSON 文本存储，读取时由 record_to_unit 还原为 list。
    content_text = json.dumps(person_list, ensure_ascii=False)

    return {
        "type": RECORD_TYPE,
        "title": inner.get("item_event", "?"),
        "content": content_text,             # 人员原始值（JSON 文本），保留识别原文
        "extra": {
            "id": unit.get("id", ""),                    # 时间+序号
            "date": inner.get("date", ""),               # YYYY-MM-DD，便于按日查询
            "score": None,
            "entity_status": initial_status,
            "recorder": inner.get("recorder", ""),
            "remark": inner.get("remark", ""),
            "error_info": None,
        },
        "related_ids": person_ids,
    }


def existing_record_ids() -> set:
    """
    库中现有 points_record 的 extra.id 集合（仅未删除），用于导入去重。

    出参：
        set[str] - 形如 {"20260807001", ...}
    """
    client = get_client()
    page_size = 500
    page = 1
    ids: set = set()
    while True:
        result = client.query_entities({"type": RECORD_TYPE}, page=page, page_size=page_size)
        batch = result.get("list", [])
        if not batch:
            break
        for ent in batch:
            rid = (ent.get("extra") or {}).get("id")
            if rid:
                ids.add(str(rid))
        total = result.get("total") or 0
        if len(batch) < page_size or page * page_size >= total:
            break
        page += 1
    return ids


def create_points_records(
    units: List[Dict[str, Any]],
    initial_status: str = STATUS_PENDING_REVIEW,
    skip_existing: bool = True,
    stats: Optional[Dict[str, Any]] = None,
) -> List[Tuple[str, str]]:
    """
    批量将识别单体落库为 points_record 实体。

    入参：
        units: 单体列表（data_parser.split_to_events 的输出）
        initial_status: 初始状态
        skip_existing: True 时库中已有同 extra.id 的单体直接跳过（同一批日志被
                       识别/导入两次不会再落两份，避免"同一事件两条记录"）
        stats: 可选 dict，回传落库明细 {"created": n, "skipped": n, "skipped_ids": [...]}

    出参：
        List[(unit_id, entity_id)] - 每条单体对应的 (原始id, 实体id)；
        人员解析失败的单体自动写入 error_info（person_not_found）并保持待纠错状态。
    """
    if not units:
        if stats is not None:
            stats.update({"created": 0, "skipped": 0, "skipped_ids": []})
        return []

    by_pinyin, by_name = load_person_map()
    client = get_client()

    existing = existing_record_ids() if skip_existing else set()
    skipped_ids: List[str] = []

    batch_data: List[Dict[str, Any]] = []
    unit_ids: List[str] = []

    for unit in units:
        if unit.get("Operation") != "event":
            # 非事件单体（fix_map/mistake 等）不落库
            continue
        uid = str(unit.get("id", "") or "")
        if skip_existing and uid and uid in existing:
            # 同 id 已在库中（典型场景：同一张日志图片被识别两次）
            skipped_ids.append(uid)
            logger.info(f"导入去重: 记录 {uid} 已存在，跳过")
            continue
        inner = unit.get("data", {})
        person_list = inner.get("person_list", [])
        if not isinstance(person_list, list):
            person_list = []

        person_ids, invalid = resolve_person_ids(person_list, by_pinyin, by_name)

        record_data = unit_to_record_data(unit, person_ids, initial_status)
        if invalid:
            record_data["extra"]["error_info"] = {
                "type": ERROR_PERSON_NOT_FOUND,
                "field": "persons",
                "invalid_values": invalid,
                "raw": person_list,
            }
        batch_data.append(record_data)
        unit_ids.append(unit.get("id", ""))
        if uid:
            existing.add(uid)  # 同一批内部也去重

    if not batch_data:
        if stats is not None:
            stats.update({"created": 0, "skipped": len(skipped_ids), "skipped_ids": skipped_ids})
        logger.info(f"points_record 全部跳过（重复 {len(skipped_ids)} 条）")
        return []

    entity_ids = client.batch_create_entities(batch_data)
    logger.info(f"points_record 落库 {len(entity_ids)} 条 (初始状态: {initial_status})"
                + (f"，跳过重复 {len(skipped_ids)} 条" if skipped_ids else ""))
    if stats is not None:
        stats.update({"created": len(entity_ids), "skipped": len(skipped_ids),
                      "skipped_ids": skipped_ids})
    return list(zip(unit_ids, entity_ids))


# ============================================================
# 3. 查询 / 读取
# ============================================================

def query_records(
    status: Optional[str] = None,
    date: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
) -> List[Dict[str, Any]]:
    """
    查询 points_record 实体。

    入参：
        status: 按 entity_status 精确过滤（None 不过滤）
        date: 按日期（YYYY-MM-DD）精确过滤（None 不过滤）
        page / page_size: 分页

    出参：
        List[dict] - 实体字典列表（_to_dict 格式，含 extra/related_ids）
    """
    filters: Dict[str, Any] = {"type": RECORD_TYPE}
    if status:
        filters["extra_entity_status"] = status
    if date:
        filters["extra_date"] = date
    client = get_client()
    result = client.query_entities(filters, page=page, page_size=page_size)
    return result.get("list", [])


def get_record(entity_id: str) -> Optional[Dict[str, Any]]:
    """按 entity_id 获取单条记录（不存在返回 None）"""
    client = get_client()
    try:
        return client.get_entity(entity_id)
    except Exception as e:
        logger.warning(f"获取记录失败 {entity_id}: {e}")
        return None


def count_by_status() -> Dict[str, int]:
    """统计各状态记录数量（含总待处理数）"""
    client = get_client()
    statuses = [
        STATUS_PENDING_REVIEW,
        STATUS_PENDING_MATCH,
        STATUS_MATCHED,
        STATUS_UPLOADED,
    ]
    stats: Dict[str, int] = {}
    total = 0
    for st in statuses:
        cnt = client.count_entities({
            "type": RECORD_TYPE,
            "extra_entity_status": st,
        })
        stats[st] = cnt
        total += cnt
    stats["total"] = total
    return stats


def statistics(date_start: Optional[str] = None,
               date_end: Optional[str] = None) -> Dict[str, Any]:
    """
    【上传后统计】对 uploaded 积分记录做汇总（按学生 / 按事件 / 按日期）。

    入参：
        date_start / date_end: 日期范围（YYYY-MM-DD，含边界；None 不限制）

    出参：
        {
          "record_count": 参与统计的记录数,
          "total_points": 总积分,
          "by_student": {学生名: 总分},   # 记录内每人各得 score
          "by_event":   {事件名: 总分},
          "by_date":    {日期: 总分},
        }
    """
    entities = query_records(status=STATUS_UPLOADED, page_size=10000)
    if not entities:
        return {"record_count": 0, "total_points": 0.0,
                "by_student": {}, "by_event": {}, "by_date": {}}

    # 过滤日期范围
    if date_start or date_end:
        filtered = []
        for e in entities:
            d = (e.get("extra") or {}).get("date", "")
            if date_start and d < date_start:
                continue
            if date_end and d > date_end:
                continue
            filtered.append(e)
        entities = filtered

    # person 映射（entity_id -> 姓名）
    by_pinyin, by_name = load_person_map()
    person_names: Dict[str, str] = {}
    for name, eid in by_name.items():
        person_names[eid] = name
    # 反向 pinyin 也补（理论上 by_name 已含全部 person 的 name）
    for pin, eid in by_pinyin.items():
        person_names.setdefault(eid, pin)

    by_student: Dict[str, float] = {}
    by_event: Dict[str, float] = {}
    by_date: Dict[str, float] = {}
    total = 0.0

    for e in entities:
        extra = e.get("extra") or {}
        try:
            score = float(extra.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        event = e.get("title") or "?"
        date = extra.get("date", "")
        total += score
        by_event[event] = by_event.get(event, 0.0) + score
        by_date[date] = by_date.get(date, 0.0) + score

        # 每人各得 score
        for rid in (e.get("related_ids") or []):
            name = person_names.get(rid, rid)
            by_student[name] = by_student.get(name, 0.0) + score

    logger.info(f"积分统计完成: {len(entities)} 条记录, 总积分 {total}")
    return {
        "record_count": len(entities),
        "total_points": round(total, 2),
        "by_student": {k: round(v, 2) for k, v in by_student.items()},
        "by_event": {k: round(v, 2) for k, v in by_event.items()},
        "by_date": {k: round(v, 2) for k, v in by_date.items()},
    }


def reset_all_data() -> Dict[str, Any]:
    """
    【测试用】清空所有积分数据（points_record + points_edit），保留 person 实体。

    硬删除全部积分记录与编辑请求（含已软删的），返回删除数量与剩余 person 数。
    调用前请确认：此操作不可恢复。
    """
    client = get_client()
    deleted = 0

    for type_ in (RECORD_TYPE, EDIT_TYPE):
        page = 1
        while True:
            # is_deleted=None 表示不过滤删除标记，连软删记录一并清掉
            result = client.query_entities({"type": type_, "is_deleted": None},
                                           page=page, page_size=100, order="asc")
            items = result.get("list", [])
            if not items:
                break
            for ent in items:
                try:
                    client.delete_entity(ent.get("entity_id"), hard=True)
                    deleted += 1
                except Exception as e:
                    logger.warning(f"清空数据失败 {ent.get('entity_id')}: {e}")
            if len(items) < 100:
                break
            page += 1

    # person 保留统计
    person_count = client.count_entities({"type": PERSON_TYPE})
    logger.info(f"已清空积分数据 {deleted} 条，保留 person {person_count} 个")
    return {"deleted": deleted, "person_count": person_count}


# ============================================================
# 4. 更新 / 状态流转
# ============================================================

def update_record_extra(entity_id: str, **patch: Any) -> bool:
    """更新记录的 extra 字段（深度合并；传 None 表示置空）"""
    if not patch:
        return True
    client = get_client()
    try:
        client.update_entity(entity_id, {"extra": patch})
        return True
    except Exception as e:
        logger.error(f"更新记录失败 {entity_id}: {e}")
        return False


def set_record_status(entity_id: str, status: str) -> bool:
    """状态流转：pending_review / pending_match / matched / uploaded"""
    return update_record_extra(entity_id, entity_status=status)


def set_record_score(entity_id: str, score: Optional[float]) -> bool:
    """写入匹配分数（None 清除）"""
    return update_record_extra(entity_id, score=None if score is None else float(score))


def set_record_error(entity_id: str, error_info: Optional[Dict[str, Any]]) -> bool:
    """写入纠错信息（None 清除）。纠错时按 entity_status + error_info 定位。"""
    return update_record_extra(entity_id, error_info=error_info)


def soft_delete_record(entity_id: str) -> bool:
    """软删除一条记录（is_deleted=1）"""
    client = get_client()
    try:
        client.delete_entity(entity_id, hard=False)
        return True
    except Exception as e:
        logger.error(f"删除记录失败 {entity_id}: {e}")
        return False


def cancel_record(entity_id: str) -> bool:
    """纠错时取消：置 cancelled"""
    return update_record_extra(entity_id, entity_status=STATUS_CANCELLED)


def cancel_edit(entity_id: str) -> bool:
    """纠错时取消编辑请求：置 cancelled"""
    return update_record_extra(entity_id, entity_status=STATUS_CANCELLED)


def correct_record(entity_id: str, title: Optional[str] = None,
                   persons: Optional[List[str]] = None,
                   score: Optional[float] = None,
                   recorder: Optional[str] = None,
                   date: Optional[str] = None,
                   remark: Optional[str] = None) -> bool:
    """
    应用人工修正到积分记录（纠错界面 R6 的落库实现）：
        更新字段 -> 清 error_info -> 置 pending_review 待重新校验。

    入参：
        entity_id: 目标记录
        title / persons / score / recorder / date / remark: 要更新的字段（None 表示不改）
    """
    ent = get_record(entity_id)
    if not ent:
        logger.warning(f"修正失败: 记录不存在 {entity_id}")
        return False

    updates: Dict[str, Any] = {}
    if title is not None:
        updates["title"] = title
    if persons is not None:
        updates["content"] = json.dumps(persons, ensure_ascii=False)
        person_ids, _ = resolve_person_ids(persons, *load_person_map())
        updates["related_ids"] = person_ids

    patch: Dict[str, Any] = {"error_info": None, "entity_status": STATUS_PENDING_REVIEW}
    if score is not None:
        patch["score"] = float(score)
    if recorder is not None:
        patch["recorder"] = recorder
    if date is not None:
        patch["date"] = date
    if remark is not None:
        patch["remark"] = remark

    client = get_client()
    try:
        if updates or patch:
            payload = dict(updates)
            payload["extra"] = patch
            client.update_entity(entity_id, payload)
        logger.info(f"积分记录 {entity_id} 已修正，待重新校验")
        return True
    except Exception as e:
        logger.error(f"修正积分记录失败 {entity_id}: {e}")
        return False


def correct_edit(entity_id: str, new_line: Optional[str] = None,
                 event: Optional[str] = None,
                 persons: Optional[List[str]] = None,
                 remark: Optional[str] = None,
                 field: Optional[str] = None,
                 value: Optional[str] = None) -> bool:
    """
    应用人工修正到编辑请求：
        - 提供 new_line：整行重新解析并覆盖实体字段
        - 否则按指定字段修正
    修正后清 error_info、置 pending_review 待重新校验。

    入参：
        entity_id: 目标编辑请求
        new_line: 修正后的完整原始行（如 "2026073112A<WJH>"）
        event / persons / remark / field / value: 单字段修正（None 表示不改）
    """
    ent = get_edit(entity_id)
    if not ent:
        logger.warning(f"修正失败: 编辑请求不存在 {entity_id}")
        return False

    if new_line is not None:
        # 整行重解析
        from BYu.class_manager.points.edit_parser import parse_edit_line
        edit = parse_edit_line(new_line)
        entity_data = edit_to_entity_data(edit, [], STATUS_PENDING_REVIEW)
        # 保留原有 related_ids
        new_extra = entity_data["extra"]
        # 人员解析
        persons_new = edit.get("persons", [])
        person_ids, invalid = resolve_person_ids(persons_new, *load_person_map())
        if invalid:
            new_extra["error_info"] = {
                "type": ERROR_PERSON_NOT_FOUND, "field": "persons",
                "invalid_values": invalid, "raw": persons_new,
            }
        payload = {
            "title": entity_data["title"],
            "content": entity_data["content"],
            "related_ids": person_ids,
            "extra": new_extra,
        }
    else:
        # 单字段修正
        edit = edit_entity_to_dict(ent)
        patch: Dict[str, Any] = {"error_info": None, "entity_status": STATUS_PENDING_REVIEW}
        updates: Dict[str, Any] = {}
        if event is not None:
            patch["event"] = event
            patch["operation"] = edit.get("operation", "A")
            title = f"{patch['operation']} {event}"
            updates["title"] = title
        if persons is not None:
            updates["content"] = json.dumps(persons, ensure_ascii=False)
            person_ids, invalid = resolve_person_ids(persons, *load_person_map())
            updates["related_ids"] = person_ids
            if invalid:
                patch["error_info"] = {
                    "type": ERROR_PERSON_NOT_FOUND, "field": "persons",
                    "invalid_values": invalid, "raw": persons,
                }
        if remark is not None:
            patch["remark"] = remark
        if field is not None:
            patch["field"] = field
        if value is not None:
            patch["value"] = value
        payload = dict(updates)
        payload["extra"] = patch

    client = get_client()
    try:
        client.update_entity(entity_id, payload)
        logger.info(f"编辑请求 {entity_id} 已修正，待重新校验")
        return True
    except Exception as e:
        logger.error(f"修正编辑请求失败 {entity_id}: {e}")
        return False


# ============================================================
# 5. 实体 -> 内存单体（供校验/匹配管道复用）
# ============================================================

def record_to_unit(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 points_record 实体转回内存单体格式，复用 validator/matcher 管道。

    入参：
        entity: query_records / get_record 返回的实体字典

    出参：
        dict - 单体，形如：
            {"Operation": "event", "id": "20260807003",
             "entity_id": "...", "_entity_status": "pending_match",
             "data": {"recorder": ..., "date": ..., "item_event": ...,
                      "person_list": [...], "remark": ...},
             "points": 1.0, "_matched": True, "_match_source": "store"}
    """
    extra = entity.get("extra") or {}
    person_list = entity.get("content") or []
    if isinstance(person_list, str):
        # content 以 JSON 文本存储，还原为 list
        try:
            person_list = json.loads(person_list) or []
        except (json.JSONDecodeError, TypeError):
            person_list = []
    if not isinstance(person_list, list):
        person_list = []

    inner = {
        "recorder": extra.get("recorder", ""),
        "date": extra.get("date", ""),
        "item_event": entity.get("title", ""),
        "person_list": person_list,
        "remark": extra.get("remark", ""),
    }

    unit: Dict[str, Any] = {
        "Operation": "event",
        "id": extra.get("id") or entity.get("entity_id", ""),
        "entity_id": entity.get("entity_id", ""),
        "_entity_status": extra.get("entity_status", STATUS_PENDING_REVIEW),
        "_error_info": extra.get("error_info"),
        "data": inner,
    }

    score = extra.get("score")
    if score is not None:
        try:
            unit["points"] = float(score)
            unit["_matched"] = True
            unit["_match_source"] = "store"
        except (TypeError, ValueError):
            pass
    return unit


def records_to_units(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """批量实体转单体"""
    return [record_to_unit(e) for e in entities]


# ============================================================
# 6. 纸质编辑指令（points_edit）存储与应用
# ============================================================
# 编辑指令由 edit_parser.parse_edit_line 解析为 edit dict，本段负责：
#   - 落库（create_edit_records）
#   - 查询（query_edits / get_edit）
#   - 库相关校验（validate_edit：seq 冲突、目标编号存在性）
#   - 应用（apply_edit：加人/删人/删事件/改事件/改分数）
# ============================================================

def edit_to_entity_data(
    edit: Dict[str, Any],
    person_ids: List[str],
    initial_status: str = STATUS_PENDING_REVIEW,
) -> Dict[str, Any]:
    """
    将 edit dict（edit_parser 输出）转换为 points_edit 实体数据。

    入参：
        edit: 解析后的编辑指令
        person_ids: 人员解析出的 related_ids
        initial_status: 初始状态

    出参：
        dict - create_entity 可直接接受的实体数据
    """
    op = edit.get("operation", "")
    event = edit.get("event", "")
    if op == "A":
        if edit.get("target_seq"):
            title = "A 加人"
        else:
            title = f"A {event}" if event else "A <事件>"
    elif op == "D":
        title = "D 删事件" if edit.get("delete_all") else "D 删人"
    elif op == "C":
        title = f"C {edit.get('field', '?')}: {edit.get('value', '')}"
    else:
        title = f"EDIT {op}"

    persons = edit.get("persons", [])
    if not isinstance(persons, list):
        persons = []

    # 与 points_record 一致：人员列表以 JSON 文本存 content
    content_text = json.dumps(persons, ensure_ascii=False)

    return {
        "type": EDIT_TYPE,
        "title": title,
        "content": content_text,
        "extra": {
            "id": edit.get("id", ""),                # 日期+编号（唯一，打回校验用）
            "date": edit.get("date", ""),            # YYYY-MM-DD
            "raw": edit.get("raw", ""),              # 原始编辑行（导出/纠错用）
            "seq": edit.get("seq", ""),
            "operation": edit.get("operation", ""),
            "event": event,
            "remark": edit.get("remark", ""),
            "score": edit.get("score"),
            "delete_all": bool(edit.get("delete_all", False)),
            "field": edit.get("field"),
            "value": edit.get("value"),
            "target_seq": edit.get("target_seq"),
            "target_entity_id": edit.get("target_entity_id"),
            "entity_status": initial_status,
            "error_info": edit.get("error_info"),
        },
        "related_ids": person_ids,
    }


def create_edit_records(
    edits: List[Dict[str, Any]],
    initial_status: str = STATUS_PENDING_REVIEW,
) -> List[Tuple[str, str]]:
    """
    批量将编辑指令落库为 points_edit 实体。

    入参：
        edits: edit dict 列表（edit_parser.parse_edit_line 输出）
        initial_status: 初始状态（默认 pending_review）

    出参：
        List[(edit_id, entity_id)]；人员解析失败自动写 person_not_found error_info。
    """
    if not edits:
        return []

    by_pinyin, by_name = load_person_map()
    client = get_client()

    batch_data: List[Dict[str, Any]] = []
    edit_ids: List[str] = []

    for edit in edits:
        persons = edit.get("persons", [])
        if not isinstance(persons, list):
            persons = []
        person_ids, invalid = resolve_person_ids(persons, by_pinyin, by_name)

        entity_data = edit_to_entity_data(edit, person_ids, initial_status)

        # 语法错误已由解析器写入 error_info；人员未匹配补充写入
        if invalid:
            existing_err = entity_data["extra"]["error_info"]
            entity_data["extra"]["error_info"] = {
                "type": ERROR_PERSON_NOT_FOUND,
                "field": "persons",
                "invalid_values": invalid,
                "raw": persons,
                **(existing_err or {}),
            }
        batch_data.append(entity_data)
        edit_ids.append(edit.get("id", ""))

    if not batch_data:
        return []

    entity_ids = client.batch_create_entities(batch_data)
    logger.info(f"points_edit 落库 {len(entity_ids)} 条 (初始状态: {initial_status})")
    return list(zip(edit_ids, entity_ids))


def query_edits(
    status: Optional[str] = None,
    date: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
    order: str = "desc",
) -> List[Dict[str, Any]]:
    """查询 points_edit 实体（按状态/日期过滤；order: asc/desc，正序=识别行顺序）"""
    filters: Dict[str, Any] = {"type": EDIT_TYPE}
    if status:
        filters["extra_entity_status"] = status
    if date:
        filters["extra_date"] = date
    client = get_client()
    result = client.query_entities(filters, page=page, page_size=page_size, order=order)
    return result.get("list", [])


def get_edit(entity_id: str) -> Optional[Dict[str, Any]]:
    """按 entity_id 获取单条编辑指令（不存在返回 None）"""
    client = get_client()
    try:
        return client.get_entity(entity_id)
    except Exception as e:
        logger.warning(f"获取编辑指令失败 {entity_id}: {e}")
        return None


def edit_entity_to_dict(entity: Dict[str, Any]) -> Dict[str, Any]:
    """points_edit 实体转回 edit dict（与 edit_parser 输出同构）"""
    extra = entity.get("extra") or {}
    persons = entity.get("content") or []
    if isinstance(persons, str):
        try:
            persons = json.loads(persons) or []
        except (json.JSONDecodeError, TypeError):
            persons = []
    if not isinstance(persons, list):
        persons = []

    return {
        "raw": entity.get("extra", {}).get("raw", "") or entity.get("title", ""),
        "id": extra.get("id", ""),
        "date8": extra.get("id", "")[:8],
        "date": extra.get("date", ""),
        "seq": extra.get("seq", ""),
        "operation": extra.get("operation", ""),
        "event": extra.get("event", ""),
        "persons": persons,
        "remark": extra.get("remark", ""),
        "score": extra.get("score"),
        "delete_all": bool(extra.get("delete_all", False)),
        "field": extra.get("field"),
        "value": extra.get("value"),
        "target_seq": extra.get("target_seq"),
        "target_entity_id": extra.get("target_entity_id"),
        "entity_status": extra.get("entity_status", STATUS_PENDING_REVIEW),
        "error_info": extra.get("error_info"),
    }


def resolve_edit_target(edit: Dict[str, Any]) -> Optional[str]:
    """
    根据编辑指令的 date8 + target_seq 解析目标 points_record 的 entity_id。

    规则：points_record.extra.id = 日期(8位) + 序号(2位补零)
        如编辑 "2026073112D<事件>" -> 目标 id "2026073112"（编号即序号）

    出参：
        points_record.entity_id（不存在返回 None）
    """
    target_seq = edit.get("target_seq")
    date8 = edit.get("date8") or (edit.get("id") or "")[:8]
    if not target_seq or not date8:
        return None
    try:
        target_id = f"{date8}{int(target_seq):02d}"
    except (TypeError, ValueError):
        return None

    client = get_client()
    result = client.query_entities({"type": RECORD_TYPE, "extra_id": target_id}, page=1, page_size=1)
    items = result.get("list", [])
    return items[0]["entity_id"] if items else None


def validate_edit(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    编辑指令的库相关校验（语法错误已在解析器处理）：
        - A：seq 与已有 points_edit 的 id 冲突（打回）
        - D/C：目标编号对应的 points_record 必须存在（否则打回）

    校验结果写回 extra（entity_status + error_info），返回 {"success", "error_info"}。
    """
    edit = edit_entity_to_dict(entity)
    eid = entity.get("entity_id")
    extra = entity.get("extra") or {}

    # 已应用的编辑不再参与校验（防止状态被改回 approved 导致重复应用）
    if edit.get("entity_status") == STATUS_APPLIED:
        return {"success": True, "error_info": None, "already_applied": True}

    # 已有语法错误 -> 保持待纠错
    if edit.get("error_info"):
        set_record_error(eid, edit["error_info"])
        set_record_status(eid, STATUS_PENDING_REVIEW)
        return {"success": False, "error_info": edit["error_info"]}

    op = edit.get("operation")
    is_new_event = (op == "A" and not edit.get("target_seq"))  # 新增事件（seq>=22）

    if is_new_event:
        # 新增编号冲突检查：同日期下 id（date8+seq）必须唯一（排除自身）
        conflicts = query_edits_by_id(edit.get("id"))
        if any(c.get("entity_id") != eid for c in conflicts):
            info = {"type": "seq_conflict", "field": "seq",
                    "invalid_values": [edit.get("seq", "")], "raw": [edit.get("raw", "")]}
            set_record_error(eid, info)
            set_record_status(eid, STATUS_PENDING_REVIEW)
            return {"success": False, "error_info": info}
    else:
        # D/C：目标 points_record 必须存在
        target_eid = resolve_edit_target(edit)
        if not target_eid:
            info = {"type": "seq_not_found", "field": "target_seq",
                    "invalid_values": [edit.get("target_seq", "")],
                    "raw": [edit.get("raw", "")]}
            set_record_error(eid, info)
            set_record_status(eid, STATUS_PENDING_REVIEW)
            return {"success": False, "error_info": info}
        # 回填目标 entity_id
        if target_eid != extra.get("target_entity_id"):
            update_record_extra(eid, target_entity_id=target_eid)

    # 校验通过
    set_record_error(eid, None)
    set_record_status(eid, STATUS_APPROVED)
    return {"success": True, "error_info": None}


def get_edit_by_id(edit_id: str) -> Optional[Dict[str, Any]]:
    """按 extra.id（日期+编号）查找编辑指令（存在返回第一个）"""
    items = query_edits_by_id(edit_id)
    return items[0] if items else None


def query_edits_by_id(edit_id: str, page_size: int = 100) -> List[Dict[str, Any]]:
    """按 extra.id 查询所有编辑指令（同 id 可能多条，用于冲突检测）"""
    if not edit_id:
        return []
    client = get_client()
    result = client.query_entities({"type": EDIT_TYPE, "extra_id": edit_id},
                                   page=1, page_size=page_size)
    return result.get("list", [])


def export_edits(path: str, status: Optional[str] = None) -> int:
    """
    导出库中编辑指令为 JSON 文件（原始行数组，与修改单识别输出格式一致）。

    入参：
        path: 导出文件路径（写入 {"lines": ["原始行1", ...]}, ...}）
        status: 只导出指定状态的编辑（None 为全部）

    出参：
        int - 导出的行数
    """
    edits = query_edits(status=status, page_size=10000, order="asc")
    lines = [(e.get("extra") or {}).get("raw", "")
             for e in edits if (e.get("extra") or {}).get("raw")]
    payload = {"lines": lines}
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"导出编辑失败 {path}: {e}")
        return 0
    logger.info(f"导出编辑 {len(lines)} 行到 {path}")
    return len(lines)


def import_edits(path: str, initial_status: str = STATUS_PENDING_REVIEW) -> Dict[str, Any]:
    """
    从 JSON 文件导入编辑指令（免识别，测试复用）。

    入参：
        path: 文件路径，格式 {"lines": ["原始行1", ...]} 或 ["原始行1", ...]
        initial_status: 初始状态（默认 pending_review）

    出参：
        {"imported": N, "pairs": [(edit_id, entity_id)], "edits": [...]}
    """
    from BYu.class_manager.points.edit_parser import parse_edit_lines

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"导入编辑失败 {path}: {e}")
        return {"imported": 0, "pairs": [], "edits": [], "error": str(e)}

    if isinstance(data, list):
        raw_lines = [str(x).strip() for x in data if str(x).strip()]
    elif isinstance(data, dict) and "lines" in data:
        raw_lines = [str(x).strip() for x in data.get("lines", []) if str(x).strip()]
    else:
        return {"imported": 0, "pairs": [], "edits": [],
                "error": "文件格式错误，应为 {\"lines\": [...]} 或行数组"}

    if not raw_lines:
        return {"imported": 0, "pairs": [], "edits": [], "error": "没有可导入的行"}

    edits = parse_edit_lines(raw_lines)
    pairs = create_edit_records(edits, initial_status=initial_status)
    logger.info(f"导入编辑 {len(pairs)} 条从 {path}")
    return {"imported": len(pairs), "pairs": pairs, "edits": edits}


def apply_edit(entity: Dict[str, Any]) -> Dict[str, Any]:
    """
    应用一条编辑指令到目标 points_record：
        A：创建新 points_record（id = 日期+seq 补零2位，status=pending_review）
        D delete_all：软删目标记录
        D persons：目标记录移除对应人员（content + related_ids）
        C event：更新目标 title，状态回 pending_review
        C score：更新目标 score，状态置 matched

    应用成功后编辑指令置 applied；失败保留 approved + error_info。
    """
    edit = edit_entity_to_dict(entity)
    eid = entity.get("entity_id")
    op = edit.get("operation")

    # 已是 applied 或校验未通过，直接返回
    if edit.get("entity_status") == STATUS_APPLIED:
        return {"success": True, "message": "已应用"}
    if edit.get("error_info"):
        return {"success": False, "error": "存在错误，先纠错"}

    try:
        if op == "A" and edit.get("target_seq"):
            # A 加人：目标记录追加人员
            target_eid = edit.get("target_entity_id") or resolve_edit_target(edit)
            if not target_eid:
                info = {"type": "seq_not_found", "field": "target_seq",
                        "invalid_values": [edit.get("target_seq", "")],
                        "raw": [edit.get("raw", "")]}
                set_record_error(eid, info)
                set_record_status(eid, STATUS_PENDING_REVIEW)
                return {"success": False, "error": "目标记录不存在", "error_info": info}
            return _apply_edit_add_persons(entity, edit, target_eid)

        if op == "A":
            return _apply_edit_add(entity, edit)
        else:
            target_eid = edit.get("target_entity_id") or resolve_edit_target(edit)
            if not target_eid:
                info = {"type": "seq_not_found", "field": "target_seq",
                        "invalid_values": [edit.get("target_seq", "")],
                        "raw": [edit.get("raw", "")]}
                set_record_error(eid, info)
                set_record_status(eid, STATUS_PENDING_REVIEW)
                return {"success": False, "error": "目标记录不存在", "error_info": info}

            if op == "D":
                return _apply_edit_delete(entity, edit, target_eid)
            if op == "C":
                return _apply_edit_change(entity, edit, target_eid)
            return {"success": False, "error": f"未知操作: {op}"}
    except Exception as e:
        logger.error(f"应用编辑失败 {eid}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _apply_edit_add(entity: Dict[str, Any], edit: Dict[str, Any]) -> Dict[str, Any]:
    """A：新增事件 -> 创建 points_record"""
    eid = entity.get("entity_id")
    date8 = edit.get("date8") or ""
    try:
        record_id = f"{date8}{int(edit.get('seq', '')):02d}"
    except (TypeError, ValueError):
        record_id = edit.get("id", "")

    # 已存在同 id 记录则打回
    client = get_client()
    exists = client.query_entities({"type": RECORD_TYPE, "extra_id": record_id}, page=1, page_size=1)
    if exists.get("list"):
        info = {"type": "seq_conflict", "field": "seq",
                "invalid_values": [edit.get("seq", "")], "raw": [edit.get("raw", "")]}
        set_record_error(eid, info)
        set_record_status(eid, STATUS_PENDING_REVIEW)
        return {"success": False, "error": "目标编号已存在", "error_info": info}

    # 人员 -> related_ids
    by_pinyin, by_name = load_person_map()
    persons = edit.get("persons", [])
    person_ids, invalid = resolve_person_ids(persons, by_pinyin, by_name)

    inner = {
        "item_event": edit.get("event", ""),
        "person_list": persons,
        "recorder": "",
        "date": edit.get("date", ""),
        "remark": edit.get("remark", ""),
    }
    unit = {"Operation": "event", "id": record_id, "data": inner}
    record_data = unit_to_record_data(unit, person_ids, STATUS_PENDING_REVIEW)
    if invalid:
        # 人员缺失 -> 待纠错
        record_data["extra"]["entity_status"] = STATUS_PENDING_REVIEW
        record_data["extra"]["error_info"] = {
            "type": ERROR_PERSON_NOT_FOUND, "field": "persons",
            "invalid_values": invalid, "raw": persons,
        }
    elif edit.get("score") is not None:
        # 备注直接给了分数 -> 视为已匹配
        record_data["extra"]["score"] = edit["score"]
        record_data["extra"]["entity_status"] = STATUS_MATCHED
    else:
        # 人员全部有效 -> 直接进入匹配层
        record_data["extra"]["entity_status"] = STATUS_PENDING_MATCH

    new_eid = client.create_entity(record_data)
    set_record_status(eid, STATUS_APPLIED)
    update_record_extra(eid, applied_result_id=new_eid)
    logger.info(f"编辑 {eid} 应用: 新增 points_record {new_eid}")
    return {"success": True, "created_record": new_eid}


def _apply_edit_add_persons(entity: Dict[str, Any], edit: Dict[str, Any], target_eid: str) -> Dict[str, Any]:
    """A 加人：在目标 points_record 上追加人员（content + related_ids）"""
    eid = entity.get("entity_id")
    target = get_record(target_eid)
    if not target:
        info = {"type": "seq_not_found", "field": "target_seq",
                "invalid_values": [edit.get("target_seq", "")], "raw": [edit.get("raw", "")]}
        set_record_error(eid, info)
        set_record_status(eid, STATUS_PENDING_REVIEW)
        return {"success": False, "error": "目标记录不存在", "error_info": info}

    extra = target.get("extra") or {}
    current_persons = target.get("content") or []
    if isinstance(current_persons, str):
        try:
            current_persons = json.loads(current_persons) or []
        except (json.JSONDecodeError, TypeError):
            current_persons = []
    if not isinstance(current_persons, list):
        current_persons = []

    new_persons = edit.get("persons", [])
    merged = list(current_persons)
    for p in new_persons:
        if p and p not in merged:
            merged.append(p)

    # 同步 related_ids
    current_related = target.get("related_ids") or []
    by_pinyin, by_name = load_person_map()
    new_ids = []
    for name in new_persons:
        pid = by_pinyin.get(name) or by_name.get(name)
        if pid and pid not in current_related and pid not in new_ids:
            new_ids.append(pid)
    merged_ids = current_related + new_ids

    client = get_client()
    client.update_entity(target_eid, {
        "content": json.dumps(merged, ensure_ascii=False),
        "related_ids": merged_ids,
    })
    # 人员变化 -> 目标记录需重新校验/匹配
    set_record_status(target_eid, STATUS_PENDING_REVIEW)
    set_record_error(target_eid, None)
    set_record_status(eid, STATUS_APPLIED)
    update_record_extra(eid, applied_result_id=target_eid)
    logger.info(f"编辑 {eid} 应用: 目标 {target_eid} 追加人员 {new_persons}")
    return {"success": True, "updated_record": target_eid}


def _apply_edit_delete(entity: Dict[str, Any], edit: Dict[str, Any], target_eid: str) -> Dict[str, Any]:
    """D：删除整个事件或删除人员"""
    eid = entity.get("entity_id")
    target = get_record(target_eid)
    if not target:
        info = {"type": "seq_not_found", "field": "target_seq",
                "invalid_values": [edit.get("target_seq", "")], "raw": [edit.get("raw", "")]}
        set_record_error(eid, info)
        set_record_status(eid, STATUS_PENDING_REVIEW)
        return {"success": False, "error": "目标记录不存在", "error_info": info}

    if edit.get("delete_all"):
        # 删除整个事件
        soft_delete_record(target_eid)
        set_record_status(eid, STATUS_APPLIED)
        update_record_extra(eid, applied_result_id=target_eid)
        logger.info(f"编辑 {eid} 应用: 删除 points_record {target_eid}")
        return {"success": True, "deleted_record": target_eid}

    # 删除人员：更新 content 与 related_ids
    extra = target.get("extra") or {}
    current_persons = target.get("content") or []
    if isinstance(current_persons, str):
        try:
            current_persons = json.loads(current_persons) or []
        except (json.JSONDecodeError, TypeError):
            current_persons = []
    remove_set = set(edit.get("persons", []))
    remaining = [p for p in current_persons if p not in remove_set]

    # 同步 related_ids
    current_related = target.get("related_ids") or []
    by_pinyin, by_name = load_person_map()
    remove_ids = set()
    for name in remove_set:
        pid = by_pinyin.get(name) or by_name.get(name)
        if pid:
            remove_ids.add(pid)
    remaining_ids = [r for r in current_related if r not in remove_ids]

    client = get_client()
    client.update_entity(target_eid, {
        "content": json.dumps(remaining, ensure_ascii=False),
        "related_ids": remaining_ids,
    })
    set_record_status(target_eid, STATUS_PENDING_REVIEW)
    set_record_error(target_eid, None)
    set_record_status(eid, STATUS_APPLIED)
    update_record_extra(eid, applied_result_id=target_eid)
    logger.info(f"编辑 {eid} 应用: 目标 {target_eid} 删除人员 {remove_set}")
    return {"success": True, "updated_record": target_eid}


def _apply_edit_change(entity: Dict[str, Any], edit: Dict[str, Any], target_eid: str) -> Dict[str, Any]:
    """C：修改目标记录的事件名或分数"""
    eid = entity.get("entity_id")
    target = get_record(target_eid)
    if not target:
        info = {"type": "seq_not_found", "field": "target_seq",
                "invalid_values": [edit.get("target_seq", "")], "raw": [edit.get("raw", "")]}
        set_record_error(eid, info)
        set_record_status(eid, STATUS_PENDING_REVIEW)
        return {"success": False, "error": "目标记录不存在", "error_info": info}

    client = get_client()
    field = edit.get("field")
    value = edit.get("value")

    if field == "event":
        client.update_entity(target_eid, {"title": value})
        # 事件变更：清掉旧分数/匹配标记，重新走校验+匹配
        update_record_extra(target_eid, score=None, entity_status=STATUS_PENDING_REVIEW)
        set_record_error(target_eid, None)
    elif field == "score":
        set_record_score(target_eid, edit.get("score"))
        set_record_status(target_eid, STATUS_MATCHED)
        set_record_error(target_eid, None)
    else:
        info = {"type": "field_invalid", "field": "field",
                "invalid_values": [str(field)], "raw": [edit.get("raw", "")]}
        set_record_error(eid, info)
        return {"success": False, "error": f"未知字段: {field}", "error_info": info}

    set_record_status(eid, STATUS_APPLIED)
    update_record_extra(eid, applied_result_id=target_eid)
    logger.info(f"编辑 {eid} 应用: 目标 {target_eid} 修改 {field} -> {value}")
    return {"success": True, "updated_record": target_eid}

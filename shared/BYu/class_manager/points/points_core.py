# points_core.py
# =============================================================================
# 模块：班级积分管理核心模块（V3.0）
# =============================================================================
# 功能：
#   1. 图片识别：调用 vision 模块识别图片并解析为数据单元，支持 type 参数
#   2. 数据校验：调用 validator 模块校验数据
#   3. 应用修正：应用用户提供的 fix_map
#   4. 生成最终事件：执行完整管道（校验→匹配），返回事件列表
#   5. 上传最终事件：直接上传缓存的事件列表
#   6. 辅助：清除缓存，状态管理
# =============================================================================

import sys
import os
import re
import json
import copy
import logging
import hashlib
from typing import Dict, Any, List, Optional

# 配置日志
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# ============================================================
# 导入依赖模块（使用包绝对导入）
# ============================================================
from BYu.class_manager.points import data_parser,validator,matcher,uploader
from BYu.class_manager.points import points_store as store
from BYu.class_manager.points.vision import vision

class PointsProcessor:
    """积分处理器（V3.0 简化流程）"""

    def __init__(self, verbose: bool = False, debug: bool = False):
        self.verbose = verbose
        self.debug = debug

        # 缓存与状态
        self._preview_cache = None
        self._preview_hash = None
        self._final_events_cache = None
        self._final_hash = None
        self.is_ready = False

    def _log(self, msg: str, level: str = "info"):
        if not self.verbose:
            return
        if level == "error":
            logger.error(msg)
        elif level == "warning":
            logger.warning(msg)
        else:
            logger.info(msg)

    def _dbg(self, msg: str, data: Any = None):
        """
        全面 debug 打印（debug=True 时输出，不怕刷屏，方便前端接入调试）。
        data 为结构化对象时以 JSON 输出。
        """
        if not self.debug:
            return
        print(f"\n[DBG] {msg}")
        if data is not None:
            try:
                print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
            except TypeError:
                print(data)

    # ============================================================
    # 1. 图片识别（支持 type 参数，直接打印错误详情）
    # ============================================================

    def recognize_images(self, image_paths: List[str], type: str = "班务日志") -> List[Dict]:
        """
        识别图片并解析为数据单元

        入参：
            image_paths: List[str] - 图片路径列表
            type: str - 识别类型，默认 "班务日志"

        出参：
            List[Dict] - 数据单元列表，如果全部失败则返回空列表，并打印错误详情
        """
        if not image_paths:
            return []

        self._log(f"开始处理 {len(image_paths)} 张图片，类型: {type}")
        vision_results = []
        errors = []

        for img_path in image_paths:
            if not os.path.exists(img_path):
                err_msg = f"图片文件不存在: {img_path}"
                self._log(err_msg, "warning")
                errors.append(f"{os.path.basename(img_path)}: {err_msg}")
                continue

            try:
                # 调用 vision 函数（直接从 core 导入，不再是 vision.vision）
                result = vision(img_path, type=type, print_raw=self.debug)
                if isinstance(result.get("content"), dict):
                    vision_results.append(result)
                    self._log(f"识别成功: {os.path.basename(img_path)}")
                else:
                    err_msg = result.get("content", "未知错误")
                    self._log(f"识别失败: {err_msg}", "warning")
                    errors.append(f"{os.path.basename(img_path)}: {err_msg}")
            except Exception as e:
                err_msg = f"识别异常: {e}"
                self._log(err_msg, "error")
                errors.append(f"{os.path.basename(img_path)}: {err_msg}")
                import traceback
                logger.error(traceback.format_exc())

        # ---- 如果所有图片都失败，打印错误详情 ----
        if not vision_results:
            print("\n" + "=" * 60)
            print("❌ 所有图片识别失败，错误详情如下：")
            print("=" * 60)
            for err in errors:
                print(f"  • {err}")
            print("=" * 60)
            print("💡 请检查：")
            print("  1. 图片是否清晰、格式是否支持")
            print("  2. 识别类型是否正确（当前使用: " + type + "）")
            print("  3. GYun.LLM 视觉模型服务是否正常（siliconflow/Qwen/Qwen3-VL-8B-Instruct）\n")
            return []

        # ---- 部分成功，继续处理 ----
        total_data = data_parser.collect_total_data(vision_results)
        if not total_data:
            print("⚠️ 识别成功但未能提取有效数据，可能图片内容不符合班务日志格式")
            return []

        event_list = data_parser.split_to_events(total_data)
        units = event_list.get("data", [])
        self._log(f"提取到 {len(units)} 条单体")
        return units

    # ============================================================
    # 2. 数据校验
    # ============================================================

    def validate(self, data_units: List[Dict]) -> Dict[str, Any]:
        if not data_units:
            return {"has_errors": False, "mistakes": [], "checked_data": []}

        check_result = validator.check({"data": data_units})

        mistakes = [
            {"id": u.get("id", ""), "content": u.get("content", [])}
            for u in check_result.get("data", [])
            if u.get("Operation") == "mistake"
        ]

        checked_data = [
            u for u in check_result.get("data", [])
            if u.get("Operation") == "event"
        ]

        return {
            "has_errors": len(mistakes) > 0,
            "mistakes": mistakes,
            "checked_data": checked_data
        }

    # ============================================================
    # 3. 应用修正
    # ============================================================

    def apply_fix_map(self, data_units: List[Dict], fix_maps: List[Dict]) -> List[Dict]:
        if not fix_maps:
            return data_units[:]

        temp_data = data_units + fix_maps
        corrected = validator.correct({"data": temp_data})

        result = [
            u for u in corrected.get("data", [])
            if u.get("Operation") == "event"
        ]

        self._log(f"应用了 {len(fix_maps)} 条修正，修正后 {len(result)} 条数据")
        return result

    # ============================================================
    # 4. 生成最终事件
    # ============================================================

    def generate_final_events(self, data_units: List[Dict]) -> Dict[str, Any]:
        if not data_units:
            return {"success": False, "error": "没有数据"}

        # 哈希计算
        hash_data = []
        for u in data_units:
            u_copy = {k: v for k, v in u.items() if k not in ["_matched", "_match_source", "points"]}
            hash_data.append(u_copy)
        data_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
        current_hash = hashlib.md5(data_str.encode()).hexdigest()

        if self._final_hash == current_hash and self._final_events_cache is not None:
            self._log("最终事件缓存命中，直接返回")
            return {"success": True, "events": copy.deepcopy(self._final_events_cache)}

        self._log("缓存未命中，开始执行完整管道...")

        # 校验
        check_data = validator.check({"data": data_units})
        correct_data = validator.correct(check_data)

        remaining = [u for u in correct_data.get("data", []) if u.get("Operation") == "mistake"]
        if remaining:
            errors = [f"ID:{mu.get('id')} -> {mu.get('content')}" for mu in remaining]
            self._log("存在无法修复的错误", "error")
            return {"success": False, "error": "存在无法修复的数据错误", "error_info": errors}

        # 匹配
        matched_data = matcher.match(correct_data)
        match_errors = [u for u in matched_data.get("data", []) if u.get("Operation") == "mistake"]
        if match_errors:
            errors = [f"ID:{mu.get('id')} -> {mu.get('content')}" for mu in match_errors]
            self._log("存在无法匹配分数的事件", "error")
            return {"success": False, "error": "部分事件无法匹配分数", "error_info": errors}

        # 提取事件（匹配结果即为最终数据，无运算环节）
        events = []
        for unit in matched_data.get("data", []):
            if unit.get("Operation") == "event":
                inner = unit.get("data", {})
                events.append({
                    "id": unit.get("id"),
                    "item_event": unit.get("item_event") or inner.get("item_event", "?"),
                    "person_list": unit.get("person_list") or inner.get("person_list", []),
                    "points": float(unit.get("points", 0)),
                    "_match_source": unit.get("_match_source", "unknown")
                })

        self._final_hash = current_hash
        self._final_events_cache = copy.deepcopy(events)
        self.is_ready = True
        self._log(f"生成最终事件成功，共 {len(events)} 个")
        return {"success": True, "events": events}

    # ============================================================
    # 5. 上传最终事件
    # ============================================================

    def upload_final(self, final_events: List[Dict]) -> Dict[str, Any]:
        if not final_events:
            return {"success": False, "error": "没有事件可上传"}

        upload_data = {"data": []}
        for ev in final_events:
            unit = {
                "Operation": "event",
                "id": ev.get("id"),
                "item_event": ev.get("item_event"),
                "person_list": ev.get("person_list", []),
                "points": ev.get("points", 0),
                "_match_source": ev.get("_match_source", "unknown"),
                "data": {
                    "item_event": ev.get("item_event"),
                    "person_list": ev.get("person_list", []),
                    "points": ev.get("points", 0)
                }
            }
            upload_data["data"].append(unit)

        try:
            result = uploader.update(upload_data)
            if result.get("upload_success"):
                return {"success": True, "upload_result": result}
            else:
                return {"success": False, "error": result.get("error", "上传失败"), "error_info": result.get("error_detail")}
        except Exception as e:
            self._log(f"上传异常: {e}", "error")
            return {"success": False, "error": str(e)}

    # ============================================================
    # 6. 清除缓存
    # ============================================================

    def clear_cache(self):
        self._preview_cache = None
        self._preview_hash = None
        self._final_events_cache = None
        self._final_hash = None
        self.is_ready = False
        self._log("缓存已清除，状态置为未就绪")

    # ============================================================
    # 7. 兼容旧接口
    # ============================================================

    def preview_scores(self, data_units: List[Dict]) -> List[Dict]:
        self._log("调用已废弃的 preview_scores，请改用 generate_final_events", "warning")
        result = self.generate_final_events(data_units)
        return result["events"] if result["success"] else [{"error": result.get("error")}]

    def process_and_upload(self, data_units: List[Dict], run_calculations: bool = True) -> Dict[str, Any]:
        self._log("调用已废弃的 process_and_upload，建议使用新流程", "warning")
        gen = self.generate_final_events(data_units)
        if not gen["success"]:
            return {"success": False, "error": gen.get("error"), "error_info": gen.get("error_info")}
        return self.upload_final(gen["events"])

    # ============================================================
    # 8. 持久化链路（GYun.data 落库，防数据丢失）
    # ============================================================
    # 流程：识别即落库 -> 校验写回 -> 匹配写回 -> 上传置位
    # 每一步都可中断，下次从库中按 entity_status 恢复继续处理。

    def recognize_and_store(self, image_paths: List[str], type: str = "班务日志",
                            initial_status: str = None) -> Dict[str, Any]:
        """
        识别图片并立即落库为 points_record。

        入参：
            image_paths: 图片路径列表
            type: 识别类型
            initial_status: 初始状态（默认 pending_review）

        出参：
            {"success": True, "created": N, "pairs": [(unit_id, entity_id)],
             "units": 识别单体}
        """
        units = self.recognize_images(image_paths, type=type)
        if not units:
            return {"success": False, "error": "识别失败或无有效数据", "units": []}

        self._dbg("班务日志识别结果（原始单体）", units)

        initial = initial_status or store.STATUS_PENDING_REVIEW
        stats: Dict[str, Any] = {}
        pairs = store.create_points_records(units, initial_status=initial, stats=stats)
        skipped = stats.get("skipped", 0)
        self._log(f"识别并落库 {len(pairs)} 条 points_record (状态: {initial})"
                  + (f"，跳过重复 {skipped} 条" if skipped else ""))
        self._dbg("points_record 落库映射 (unit_id, entity_id)", pairs)
        return {"success": True, "created": len(pairs), "skipped": skipped,
                "skipped_ids": stats.get("skipped_ids", []), "pairs": pairs, "units": units}

    def load_store_units(self, status: str = None, date: str = None) -> List[Dict]:
        """
        从库加载 points_record 并转为内存单体（中断恢复入口）。

        入参：
            status: entity_status 过滤（None 为全部）
            date: YYYY-MM-DD 过滤（None 为全部）

        出参：
            List[Dict] - 单体列表（record_to_unit 格式）
        """
        entities = store.query_records(status=status, date=date)
        return store.records_to_units(entities)

    def recognize_edit_lines(self, image_paths: List[str], type: str = "修改单") -> List[str]:
        """
        识别修改单图片，返回原始编辑行列表（LLM 逐行读出，不改写格式）。

        入参：
            image_paths: 图片路径列表
            type: 识别类型（默认 "修改单"）

        出参：
            List[str] - 原始行列表（如 ["2026080923A<积极><ZBY,CWXC><+1>", ...]）
        """
        lines: List[str] = []
        for img_path in image_paths:
            if not os.path.exists(img_path):
                self._log(f"图片文件不存在: {img_path}", "warning")
                continue
            try:
                result = vision(img_path, type=type, print_raw=self.debug)
                content = result.get("content")
                if isinstance(content, dict):
                    batch = content.get("lines", [])
                    if isinstance(batch, list):
                        lines.extend(str(x).strip() for x in batch if str(x).strip())
                        self._log(f"识别修改单成功: {os.path.basename(img_path)} -> {len(batch)} 行")
                        self._dbg(f"修改单原始行 [{os.path.basename(img_path)}]", batch)
                    else:
                        self._log(f"识别修改单缺少 lines 字段: {os.path.basename(img_path)}", "warning")
                else:
                    self._log(f"识别修改单失败: {content}", "warning")
            except Exception as e:
                self._log(f"识别修改单异常: {e}", "error")
        return lines

    def recognize_edits_and_store(self, image_paths: List[str], type: str = "修改单",
                                  initial_status: str = None) -> Dict[str, Any]:
        """
        识别修改单图片并落库为 points_edit 实体（解析错误写入 error_info）。

        入参：
            image_paths: 图片路径列表
            type: 识别类型（默认 "修改单"）
            initial_status: 初始状态（默认 pending_review）

        出参：
            {"success": True, "created": N, "pairs": [(edit_id, entity_id)],
             "edits": 解析后的 edit dict 列表, "raw_lines": 原始行}
        """
        from BYu.class_manager.points.edit_parser import parse_edit_lines

        raw_lines = self.recognize_edit_lines(image_paths, type=type)
        if not raw_lines:
            return {"success": False, "error": "未识别到编辑指令", "raw_lines": raw_lines}

        edits = parse_edit_lines(raw_lines)
        self._dbg("修改单解析结果（edit dict）", edits)
        initial = initial_status or store.STATUS_PENDING_REVIEW
        pairs = store.create_edit_records(edits, initial_status=initial)
        self._log(f"识别修改单并落库 {len(pairs)} 条 points_edit (状态: {initial})")
        self._dbg("points_edit 落库映射 (edit_id, entity_id)", pairs)
        return {"success": True, "created": len(pairs), "pairs": pairs,
                "edits": edits, "raw_lines": raw_lines}

    def validate_store(self, status: str = None) -> Dict[str, Any]:
        """
        校验库中记录并写回：
            - 校验通过 -> entity_status=pending_match, error_info=None
            - 校验失败 -> entity_status=pending_review, error_info=结构化错误

        入参：
            status: 只处理指定状态的记录（默认 pending_review）

        出参：
            {"success": True, "checked": N, "ok": N, "errors": N}
        """
        entities = store.query_records(status=status or store.STATUS_PENDING_REVIEW)
        units = store.records_to_units(entities)
        if not units:
            return {"success": True, "checked": 0, "ok": 0, "errors": 0}

        self._dbg(f"校验加载 {len(units)} 条记录", [
            {"id": u.get("id"), "event": (u.get("data") or {}).get("item_event"),
             "persons": (u.get("data") or {}).get("person_list"), "eid": u.get("entity_id")}
            for u in units
        ])

        result = self.validate(units)
        mistake_by_id = {m.get("id"): m.get("content", []) for m in result["mistakes"]}

        ok = 0
        err = 0
        for unit in units:
            eid = unit.get("entity_id")
            uid = unit.get("id")
            if not eid:
                continue
            contents = mistake_by_id.get(uid)
            if contents:
                info = _build_error_info(unit, contents)
                store.set_record_error(eid, info)
                store.set_record_status(eid, store.STATUS_PENDING_REVIEW)
                err += 1
                self._dbg(f"校验失败 id={uid} eid={eid}", {"errors": contents, "error_info": info})
            else:
                store.set_record_error(eid, None)
                store.set_record_status(eid, store.STATUS_PENDING_MATCH)
                ok += 1

        self._log(f"落库校验完成: 通过 {ok} 条, 错误 {err} 条")
        self._dbg("校验写回完成", {"ok": ok, "errors": err, "mistakes": result["mistakes"]})
        return {"success": True, "checked": len(units), "ok": ok, "errors": err}

    def validate_edits_store(self, status: str = None) -> Dict[str, Any]:
        """
        校验库中编辑请求并写回：
            - 校验通过 -> entity_status=approved
            - 校验失败 -> entity_status=pending_review + error_info

        入参：
            status: 只处理指定状态的编辑请求（默认 pending_review）

        出参：
            {"success": True, "checked": N, "ok": N, "errors": N}
        """
        entities = store.query_edits(status=status or store.STATUS_PENDING_REVIEW, order="asc")
        ok = 0
        err = 0
        for ent in entities:
            r = store.validate_edit(ent)
            if r["success"]:
                ok += 1
            else:
                err += 1
            self._dbg(f"编辑校验 id={(ent.get('extra') or {}).get('id')} eid={ent.get('entity_id')}", r)
        self._log(f"编辑请求校验完成: 通过 {ok} 条, 错误 {err} 条")
        return {"success": True, "checked": len(entities), "ok": ok, "errors": err}

    def apply_edits_store(self, status: str = None) -> Dict[str, Any]:
        """
        应用库中 approved 的编辑请求：
            - 成功 -> entity_status=applied（并回填 applied_result_id）
            - 失败 -> 保留错误信息

        入参：
            status: 只处理指定状态的编辑请求（默认 approved）

        出参：
            {"success": True, "applied": N, "failed": N, "results": [...]}
        """
        entities = store.query_edits(status=status or store.STATUS_APPROVED, order="asc")
        applied = 0
        failed = 0
        results = []
        for ent in entities:
            r = store.apply_edit(ent)
            results.append({"edit_id": ent.get("entity_id"),
                            "id": (ent.get("extra") or {}).get("id"),
                            "success": r.get("success"),
                            "result": r})
            if r.get("success"):
                applied += 1
            else:
                failed += 1
        self._log(f"编辑请求应用完成: 成功 {applied} 条, 失败 {failed} 条")
        self._dbg("编辑应用明细", results)
        return {"success": True, "applied": applied, "failed": failed, "results": results}

    def match_store(self, status: str = None) -> Dict[str, Any]:
        """
        匹配库中记录的分数并写回：
            - 匹配成功 -> extra.score + entity_status=matched
            - 匹配失败 -> error_info + entity_status=pending_review

        入参：
            status: 只处理指定状态的记录（默认 pending_match）

        出参：
            {"success": True, "matched": N, "failed": N}
        """
        entities = store.query_records(status=status or store.STATUS_PENDING_MATCH)
        units = store.records_to_units(entities)
        if not units:
            return {"success": True, "matched": 0, "failed": 0}

        self._dbg(f"匹配加载 {len(units)} 条记录", [
            {"id": u.get("id"), "event": (u.get("data") or {}).get("item_event"),
             "persons": (u.get("data") or {}).get("person_list")}
            for u in units
        ])

        matched_data = matcher.match({"data": units})
        ok = 0
        failed = 0
        for unit in matched_data.get("data", []):
            eid = unit.get("entity_id")
            if not eid:
                continue
            if unit.get("Operation") == "mistake":
                info = {
                    "type": "match_failed",
                    "field": "event",
                    "invalid_values": [],
                    "raw": unit.get("content", []),
                }
                store.set_record_error(eid, info)
                store.set_record_status(eid, store.STATUS_PENDING_REVIEW)
                failed += 1
                self._dbg(f"匹配失败 id={unit.get('id')}", info)
            else:
                score = unit.get("points")
                if score is not None:
                    store.set_record_score(eid, float(score))
                store.set_record_error(eid, None)
                store.set_record_status(eid, store.STATUS_MATCHED)
                ok += 1
                self._dbg(f"匹配成功 id={unit.get('id')} eid={eid}",
                          {"event": unit.get("item_event") or (unit.get("data") or {}).get("item_event"),
                           "score": score, "source": unit.get("_match_source")})

        self._log(f"落库匹配完成: 匹配 {ok} 条, 失败 {failed} 条")
        return {"success": True, "matched": ok, "failed": failed}

    def upload_store(self, status: str = None) -> Dict[str, Any]:
        """
        上传库中已匹配记录，成功后批量置 entity_status=uploaded。

        入参：
            status: 只处理指定状态的记录（默认 matched）

        出参：
            {"success": True, "uploaded": N, "upload_result": {...}}
        """
        entities = store.query_records(status=status or store.STATUS_MATCHED)
        if not entities:
            return {"success": True, "uploaded": 0, "message": "没有待上传记录"}

        self._dbg(f"上传加载 {len(entities)} 条 matched 记录", [
            {"id": (e.get("extra") or {}).get("id"), "event": e.get("title"),
             "score": (e.get("extra") or {}).get("score"), "eid": e.get("entity_id")}
            for e in entities
        ])

        units = store.records_to_units(entities)
        events = []
        for unit in units:
            inner = unit.get("data", {})
            events.append({
                "id": unit.get("id"),
                "item_event": unit.get("item_event") or inner.get("item_event", "?"),
                "person_list": unit.get("person_list") or inner.get("person_list", []),
                "points": float(unit.get("points", 0)),
                "_match_source": unit.get("_match_source", "store"),
            })

        self._dbg("组装上传事件列表", events)
        upload_result = self.upload_final(events)
        self._dbg("scmAPI 上传结果", upload_result)
        if not upload_result.get("success"):
            return upload_result

        # 上传成功 -> 批量置 uploaded
        for unit in units:
            eid = unit.get("entity_id")
            if eid:
                store.set_record_status(eid, store.STATUS_UPLOADED)
        self._log(f"落库上传完成: {len(units)} 条已置 uploaded")
        return {"success": True, "uploaded": len(units), "upload_result": upload_result.get("upload_result")}

    def store_summary(self) -> Dict[str, Any]:
        """库中积分记录状态概览（各状态数量）"""
        return store.count_by_status()


# ============================================================
# 辅助：将 validator 错误文本解析为结构化 error_info
# ============================================================

def _build_error_info(unit: Dict[str, Any], contents: List[str]) -> Dict[str, Any]:
    """
    将 validator 生成的错误文本列表解析为 points_record 的 error_info。

    出参：
        {"type": 错误类型, "field": 字段, "invalid_values": [...], "raw": [...]}
    """
    inner = unit.get("data", {})
    person_list = inner.get("person_list", [])
    recorder = inner.get("recorder", "")

    for c in contents:
        if "人员列表为空" in c:
            return {
                "type": store.ERROR_PERSON_NOT_FOUND,
                "field": "persons",
                "invalid_values": [],
                "raw": person_list,
            }
        m = re.search(r"未知人员[:：]?\s*(\S+)", c)
        if m:
            return {
                "type": store.ERROR_PERSON_NOT_FOUND,
                "field": "persons",
                "invalid_values": [m.group(1)],
                "raw": person_list,
            }
        m = re.search(r"记录人不存在[:：]?\s*(\S+)", c)
        if m:
            return {
                "type": store.ERROR_RECORDER_NOT_FOUND,
                "field": "recorder",
                "invalid_values": [m.group(1)],
                "raw": [recorder],
            }
        if "事件名称" in c:
            return {
                "type": store.ERROR_EVENT_INVALID,
                "field": "event",
                "invalid_values": [],
                "raw": [c],
            }
        if "日期" in c:
            return {
                "type": store.ERROR_DATE_INVALID,
                "field": "date",
                "invalid_values": [],
                "raw": [c],
            }
        if "分数" in c:
            return {
                "type": store.ERROR_SCORE_INVALID,
                "field": "score",
                "invalid_values": [],
                "raw": [c],
            }
    return {"type": "unknown", "field": "", "invalid_values": [], "raw": contents}


# ============================================================
# 兼容旧接口：update_points 函数（简化入口）
# ============================================================

def update_points(input_data: dict) -> dict:
    """
    简化入口函数（兼容旧版本调用）

    入参：
        input_data: dict - 包含 "image" 或 "data" 键的字典
            image: List[str] - 图片路径列表（可选）
            data: List[Dict] - 数据单元列表（可选）

    出参：
        dict - 处理结果
            success: bool
            error: str (失败时)
            error_info: Any (失败时的详情)
            upload_result: dict (成功时)
    """
    processor = PointsProcessor(verbose=False, debug=False)
    data_units = []

    # 如果提供了图片路径，先识别
    if input_data.get("image"):
        # 识别时使用默认类型 "班务日志"
        units = processor.recognize_images(input_data["image"], type="班务日志")
        if units:
            data_units.extend(units)

    # 如果提供了数据，追加
    if input_data.get("data"):
        data_units.extend(input_data["data"])

    if not data_units:
        return {"success": False, "error": "没有可处理的数据"}

    # 使用新流程：生成最终事件
    gen_result = processor.generate_final_events(data_units)
    if not gen_result["success"]:
        return {
            "success": False,
            "error": gen_result.get("error"),
            "error_info": gen_result.get("error_info")
        }

    # 上传
    return processor.upload_final(gen_result["events"])


# ============================================================
# 自测试代码
# ============================================================
if __name__ == "__main__":
    print("=== 测试 points_core.py ===")
    processor = PointsProcessor(verbose=True, debug=False)
    # 模拟测试，不实际调用 vision
    print("✅ 测试完成")
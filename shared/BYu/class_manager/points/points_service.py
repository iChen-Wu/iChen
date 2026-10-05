# points_service.py
# =============================================================================
# 模块：积分服务类（供远程调用）
# =============================================================================
# 功能：
#   提供与 CLI 相同的业务逻辑，但以方法调用的形式暴露，无交互。
#   每个方法接收参数，返回结构化结果，方便远程调用。
#   已同步 CLI V3.0 的所有改进：
#     - 图片识别支持 type 参数
#     - 加载数据时自动生成 ID（日期+010+编号格式）
#     - 生成最终预览（校验→匹配）
#     - 上传使用新流程（generate_final_events + upload_final）
#     - 状态管理与 is_ready 同步
#     - 详细的错误信息返回
# =============================================================================

import json
import copy
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

# 导入核心模块（使用包绝对导入）
from BYu.class_manager.points.points_core import PointsProcessor
from BYu.class_manager.points.config import EVENT_SCORE_CFG, NAME_CODE_MAP, ABBR_TO_NAME


class PointsService:
    """
    积分服务类 - 供远程调用的业务逻辑层
    已同步 CLI V3.0 改进
    """

    def __init__(self, session_id: str = None, init_args: dict = None, debug: bool = False):
        """
        初始化服务实例

        :param session_id: 会话标识（可选）
        :param init_args: 初始化参数（可选）
        :param debug: 是否开启全量 debug 打印（前端接入调试用，默认 False）
        """
        self.session_id = session_id
        self.processor = PointsProcessor(verbose=debug, debug=debug)
        self.current_data: List[Dict] = []
        self._state = "idle"  # idle, ready, uploaded
        self.last_error: Optional[str] = None
        self._backup_data = None
        # 新增：同步 is_ready 状态（从 processor 读取）
        self.is_ready: bool = False
        self.final_events: List[Dict] = []

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_preview(self, limit: int = 50) -> Dict:
        """生成数据预览（精简信息，用于 UI 显示）"""
        total = len(self.current_data)
        events = []
        for u in self.current_data[:limit]:
            if u.get("Operation") == "event":
                inner = u.get("data", {})
                event_name = u.get("item_event") or inner.get("item_event") or "?"
                persons = u.get("person_list") or inner.get("person_list", [])
                points = u.get("points") or inner.get("points")

                if points is not None:
                    status = "已匹配"
                elif u.get("_matched") is True:
                    status = "匹配中"
                elif event_name in EVENT_SCORE_CFG:
                    status = "可匹配(配置)"
                else:
                    status = "未匹配"

                events.append({
                    "id": u.get("id"),
                    "event": event_name,
                    "persons": persons,
                    "points": points,
                    "status": status,
                    "has_error": False
                })
            elif u.get("Operation") == "mistake":
                events.append({
                    "id": u.get("id"),
                    "event": "❌错误",
                    "persons": [],
                    "points": None,
                    "status": "错误",
                    "has_error": True
                })
        return {"total": total, "events": events}

    def _backup(self):
        self._backup_data = copy.deepcopy(self.current_data)

    def _restore_backup(self):
        if self._backup_data is not None:
            self.current_data = self._backup_data
            self._backup_data = None

    def _clear_backup(self):
        self._backup_data = None

    def _update_state(self):
        """更新内部状态，从 processor 同步 is_ready"""
        self._state = "ready" if self.current_data else "idle"
        self.is_ready = self.processor.is_ready
        if self.is_ready:
            # 尝试从 processor 获取 final_events（通过 generate_final_events 缓存）
            # 这里不直接调用，由外部调用 generate() 来设置
            pass

    def _make_response(self, success: bool, message: str = "", data: Any = None,
                        error: str = None, error_detail: Any = None) -> Dict:
        """
        构建统一响应格式

        :param success: 是否成功
        :param message: 消息
        :param data: 数据
        :param error: 错误信息
        :param error_detail: 错误详情（可选）
        """
        resp = {"success": success}
        if message:
            resp["message"] = message
        if data is not None:
            resp["data"] = data
        if error:
            resp["error"] = error
        if error_detail:
            resp["error_detail"] = error_detail

        # 附加状态信息
        resp["is_ready"] = self.is_ready
        resp["state"] = self._state
        resp["data_count"] = len(self.current_data)

        if success and self.current_data:
            resp["preview"] = self._get_preview()
        return resp

    # ============================================================
    # ID 生成（从 CLI 提取）
    # ============================================================

    def _ensure_event_ids(self, units: List[Dict]) -> List[Dict]:
        """
        为没有合法 ID 的事件单元生成 "日期+010+编号" 格式的 ID。
        规则：
            - 如果有 id 且格式为 YYYYMMDD+2位数字，保留
            - 如果有 id 且格式为 YYYYMMDD010+2位数字，保留（视为新增事件）
            - 如果没有 id 或 id 格式不合法，生成新 ID
            - 新 ID 格式：当前日期 + "010" + 编号（2位）
        """
        if not units:
            return units

        need_id_units = []
        for u in units:
            if u.get("Operation") != "event":
                continue
            uid = u.get("id", "")
            if not uid:
                need_id_units.append(u)
                continue
            if re.match(r'^\d{8}\d{2}$', uid):
                continue
            if re.match(r'^\d{8}010\d{2}$', uid):
                continue
            need_id_units.append(u)

        if not need_id_units:
            return units

        today_str = datetime.now().strftime("%Y%m%d")

        existing_ids = set()
        all_data = self.current_data + units
        for u in all_data:
            uid = u.get("id", "")
            if uid and uid.startswith(today_str + "010"):
                existing_ids.add(uid)

        existing_nums = set()
        for eid in existing_ids:
            try:
                num = int(eid[-3:])
                existing_nums.add(num)
            except ValueError:
                pass

        max_num = max(existing_nums) if existing_nums else 0

        generated_ids = []
        for u in need_id_units:
            max_num += 1
            new_id = f"{today_str}010{max_num:02d}"
            u["id"] = new_id
            u["_source"] = "manual"
            u["_new_event"] = True
            generated_ids.append(new_id)

        # 记录生成的 ID（用于日志）
        if generated_ids:
            print(f"  📝 为新增事件生成 ID: {', '.join(generated_ids)}")

        return units

    # ============================================================
    # 业务方法
    # ============================================================

    def recognize(self, paths: List[str], type: str = "班务日志") -> Dict:
        """
        识别图片

        :param paths: 图片路径列表
        :param type: 识别类型，默认 "班务日志"
        """
        if not paths:
            return self._make_response(False, error="未提供图片路径")

        self._backup()
        units = self.processor.recognize_images(paths, type=type)
        if units:
            self.processor.clear_cache()
            self.current_data.extend(units)
            self._clear_backup()
            self._update_state()
            return self._make_response(
                True,
                f"识别成功，添加 {len(units)} 条数据 (类型: {type})",
                data={"added_count": len(units), "type": type}
            )
        else:
            self._restore_backup()
            return self._make_response(False, error="识别失败，请检查图片")

    def load_data(self, json_data: Any) -> Dict:
        """加载 JSON 数据（客户端发送的数据）"""
        if not json_data:
            return self._make_response(False, error="未提供数据")

        try:
            if isinstance(json_data, list):
                units = json_data
            elif isinstance(json_data, dict) and "data" in json_data:
                units = json_data["data"]
            else:
                return self._make_response(False, error="数据格式错误，应为列表或包含 data 键的字典")

            if not units:
                return self._make_response(False, error="数据为空")

            # ---- 生成 ID（新增） ----
            units = self._ensure_event_ids(units)

            self._backup()
            self.processor.clear_cache()
            self.current_data = units
            self._clear_backup()
            self._update_state()
            return self._make_response(
                True,
                f"加载 {len(units)} 条数据",
                data={"loaded_count": len(units)}
            )
        except Exception as e:
            self._restore_backup()
            return self._make_response(False, error=f"加载失败: {str(e)}")

    def load_server_data(self, path: str) -> Dict:
        """
        从服务端文件系统加载 JSON 数据

        :param path: 服务端文件路径
        """
        if not path:
            return self._make_response(False, error="未提供文件路径")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                units = data
            elif isinstance(data, dict) and "data" in data:
                units = data["data"]
            else:
                return self._make_response(False, error="数据格式错误")

            if not units:
                return self._make_response(False, error="数据为空")

            # ---- 生成 ID（新增） ----
            units = self._ensure_event_ids(units)

            self._backup()
            self.processor.clear_cache()
            self.current_data = units
            self._clear_backup()
            self._update_state()
            return self._make_response(
                True,
                f"加载 {len(units)} 条数据",
                data={"loaded_count": len(units), "source": path}
            )
        except FileNotFoundError:
            return self._make_response(False, error=f"文件不存在: {path}")
        except json.JSONDecodeError as e:
            return self._make_response(False, error=f"JSON 解析失败: {str(e)}")
        except Exception as e:
            return self._make_response(False, error=f"加载失败: {str(e)}")

    def save_data(self, path: str) -> Dict:
        """保存数据到服务端文件"""
        if not path:
            return self._make_response(False, error="未提供保存路径")
        if not self.current_data:
            return self._make_response(False, error="没有数据可保存")

        try:
            dirname = os.path.dirname(path)
            if dirname and not os.path.exists(dirname):
                os.makedirs(dirname)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.current_data, f, ensure_ascii=False, indent=2)
            return self._make_response(True, f"已保存到 {path}")
        except Exception as e:
            return self._make_response(False, error=f"保存失败: {str(e)}")

    def preview(self) -> Dict:
        """预览数据"""
        if not self.current_data:
            return {"total": 0, "events": [], "data_count": 0, "is_ready": self.is_ready}
        return self._get_preview(limit=200)

    def validate(self) -> Dict:
        """校验数据"""
        if not self.current_data:
            return {
                "has_errors": False,
                "mistakes": [],
                "data_count": 0,
                "is_ready": self.is_ready
            }
        result = self.processor.validate(self.current_data)
        return {
            "has_errors": result["has_errors"],
            "mistakes": result["mistakes"],
            "data_count": len(self.current_data),
            "is_ready": self.is_ready
        }

    def correct(self, fix_maps: List[Dict]) -> Dict:
        """应用修正映射"""
        if not fix_maps:
            return self._make_response(False, error="未提供修正映射")
        if not self.current_data:
            return self._make_response(False, error="没有数据")

        self._backup()
        try:
            self.processor.clear_cache()
            self.current_data = self.processor.apply_fix_map(self.current_data, fix_maps)
            self._clear_backup()
            self._update_state()
            validate_result = self.processor.validate(self.current_data)
            return self._make_response(
                True,
                f"应用 {len(fix_maps)} 条修正",
                data={
                    "has_errors": validate_result["has_errors"],
                    "mistakes": validate_result["mistakes"],
                    "applied_count": len(fix_maps)
                }
            )
        except Exception as e:
            self._restore_backup()
            return self._make_response(False, error=f"修正失败: {str(e)}")

    def edit(self, target_id: str, updates: Dict) -> Dict:
        """手动编辑单元"""
        if not target_id:
            return self._make_response(False, error="未指定 ID")
        if not self.current_data:
            return self._make_response(False, error="没有数据")

        target_index = None
        for i, u in enumerate(self.current_data):
            if u.get("id") == target_id:
                target_index = i
                break

        if target_index is None:
            return self._make_response(False, error=f"未找到 ID 为 {target_id} 的单元")

        self._backup()
        try:
            unit = self.current_data[target_index]
            if "data" in updates:
                if "data" not in unit:
                    unit["data"] = {}
                unit["data"].update(updates["data"])
                if "item_event" in updates["data"]:
                    unit["_matched"] = False
                    if "_match_source" in unit:
                        del unit["_match_source"]
                    if "points" in unit:
                        del unit["points"]
                    if "points" in unit["data"]:
                        del unit["data"]["points"]

            for key, value in updates.items():
                if key != "data":
                    unit[key] = value

            self.processor.clear_cache()
            self._clear_backup()
            self._update_state()
            return self._make_response(True, f"已更新单元 {target_id}")
        except Exception as e:
            self._restore_backup()
            return self._make_response(False, error=f"编辑失败: {str(e)}")

    def generate(self) -> Dict:
        """
        生成最终预览（CLI 菜单 2 的对应方法）
        执行完整管道：校验→匹配→运算，返回最终事件列表
        """
        if not self.current_data:
            return self._make_response(False, error="没有数据")

        # 先校验
        validate_result = self.processor.validate(self.current_data)
        if validate_result["has_errors"]:
            return self._make_response(
                False,
                error="数据存在错误，请先纠错",
                data={"mistakes": validate_result["mistakes"]}
            )

        # 生成最终事件
        try:
            result = self.processor.generate_final_events(self.current_data)
            if not result["success"]:
                return self._make_response(
                    False,
                    error=result.get("error", "生成失败"),
                    error_detail=result.get("error_info")
                )

            self.final_events = result["events"]
            self.is_ready = True
            self._update_state()

            # 计算总积分
            total_points = sum(float(ev.get("points", 0)) for ev in self.final_events)

            return self._make_response(
                True,
                f"生成成功，共 {len(self.final_events)} 个事件",
                data={
                    "events": self.final_events,
                    "summary": {
                        "total_events": len(self.final_events),
                        "total_points": total_points
                    }
                }
            )
        except Exception as e:
            self._update_state()
            return self._make_response(False, error=f"生成失败: {str(e)}")

    def score(self) -> Dict:
        """
        预览分数（旧方法，建议使用 generate）
        保留用于兼容
        """
        if not self.current_data:
            return self._make_response(False, error="没有数据")

        validate_result = self.processor.validate(self.current_data)
        if validate_result["has_errors"]:
            return self._make_response(
                False,
                error="存在错误，请先纠错",
                data={"mistakes": validate_result["mistakes"]}
            )

        try:
            # 使用 generate_final_events 替代 preview_scores
            result = self.processor.generate_final_events(self.current_data)
            if not result["success"]:
                return self._make_response(False, error=result.get("error", "预览失败"))

            events = result["events"]
            self._update_state()
            total_points = 0.0
            for ev in events:
                try:
                    total_points += float(ev.get("points", 0))
                except:
                    pass

            return self._make_response(
                True,
                f"匹配完成，共 {len(events)} 个事件",
                data={
                    "events": events,
                    "summary": {"total_events": len(events), "total_points": total_points}
                }
            )
        except Exception as e:
            return self._make_response(False, error=f"预览分数失败: {str(e)}")

    def upload(self) -> Dict:
        """
        上传积分（使用新流程：generate_final_events + upload_final）
        """
        if not self.current_data:
            return self._make_response(False, error="没有数据")

        # 检查状态：如果未就绪，先执行 generate
        if not self.is_ready:
            # 自动生成预览
            gen_result = self.generate()
            if not gen_result["success"]:
                return gen_result

        # 使用缓存的 final_events 上传
        if not self.final_events:
            return self._make_response(False, error="没有可上传的事件")

        try:
            upload_result = self.processor.upload_final(self.final_events)

            if upload_result.get("success"):
                self._state = "uploaded"
                return self._make_response(
                    True,
                    "上传成功",
                    data={"upload_result": upload_result.get("upload_result")}
                )
            else:
                return self._make_response(
                    False,
                    error=upload_result.get("error", "上传失败"),
                    error_detail=upload_result.get("error_info")
                )
        except Exception as e:
            return self._make_response(False, error=f"上传异常: {str(e)}")

    def status(self) -> Dict:
        """查询状态"""
        if not self.current_data:
            return {
                "status": "idle",
                "data_count": 0,
                "has_errors": False,
                "is_ready": self.is_ready,
                "final_events_count": len(self.final_events)
            }

        has_errors = False
        for u in self.current_data:
            if u.get("Operation") == "mistake":
                has_errors = True
                break

        return {
            "status": self._state,
            "data_count": len(self.current_data),
            "has_errors": has_errors,
            "is_ready": self.is_ready,
            "final_events_count": len(self.final_events)
        }

    def clear(self) -> Dict:
        """清空数据"""
        if not self.current_data:
            return self._make_response(False, error="没有数据可清空")

        self._backup()
        self.current_data = []
        self.final_events = []
        self.is_ready = False
        self.processor.clear_cache()
        self._clear_backup()
        self._update_state()
        return self._make_response(True, "已清空所有数据")
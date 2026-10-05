# edit_parser.py
# =============================================================================
# 模块：纸质编辑指令解析器
# =============================================================================
# 解析纸质识别出的编辑行（格式）：
#   1. 日期+专有自增编号(>=22)+A+<事件><人员逗号分隔><备注可选>  新增一个事件
#   2. 日期+原编号+A+<人员>                                    在原有事件上加人员
#   3. 日期+原编号+D+<事件>                                    删除整个事件
#   4. 日期+原编号+D+<人员逗号分隔>                             删除对应的人
#   5. 日期+原编号+C+<事件/分数><内容>                          改事件/分数
#
# 示例：
#   2026080923A<积极><ZBY,CWXC><+1>
#   2026073112A<ZBY>
#   2026073112D<事件>
#   2026073112D<ZBY,CWXC>
#   2026073112C<事件><积极>
#   2026073112C<分数><+1>
#
# 出参 edit dict（内存格式，落库由 points_store 处理）：
#   {"raw": 原文, "id": "日期+编号", "date8": "YYYYMMDD", "date": "YYYY-MM-DD",
#    "seq": "编号", "operation": "A|D|C",
#    "event": 事件名, "persons": [...], "remark": 备注, "score": ±数字或None,
#    "delete_all": bool, "field": "event|score", "value": 值,
#    "target_seq": 目标编号, "target_entity_id": None,
#    "error_info": None 或 {"type": ..., "field": ..., "invalid_values": [...], "raw": ...}}
# =============================================================================

import re
from datetime import datetime
from typing import Dict, List, Any, Optional

# 新增事件编号起点（与原有编号不冲突）
MIN_NEW_SEQ = 22

# 操作符
OP_ADD = "A"          # 新增
OP_DELETE = "D"       # 删除
OP_CHANGE = "C"       # 修改
VALID_OPERATIONS = (OP_ADD, OP_DELETE, OP_CHANGE)

# C 操作的合法字段
FIELD_EVENT = "event"
FIELD_SCORE = "score"
VALID_FIELDS = (FIELD_EVENT, FIELD_SCORE)

# error_info 错误类型
ERROR_FORMAT_INVALID = "format_invalid"
ERROR_DATE_INVALID = "date_invalid"
ERROR_CONTENT_MISSING = "content_missing"
ERROR_OPERATION_INVALID = "operation_invalid"
ERROR_EVENT_INVALID = "event_invalid"
ERROR_PERSONS_INVALID = "persons_invalid"
ERROR_FIELD_INVALID = "field_invalid"
ERROR_SCORE_INVALID = "score_invalid"
ERROR_SEQ_CONFLICT = "seq_conflict"
ERROR_SEQ_NOT_FOUND = "seq_not_found"

# 行首正则：8位日期 + 编号 + 操作符
_LINE_HEAD = re.compile(r'^(\d{8})(\d+)([ADC])')
# 尖括号参数
_PARAM = re.compile(r'<([^<>]*)>')
# ±数字（分数）
_SCORE_RE = re.compile(r'^[-+]?\d+(?:\.\d+)?$')


def _split_persons(text: str) -> List[str]:
    """按逗号/顿号/空格分隔人员，去除括号（"（张雨绮）" -> "张雨绮"），字母缩写转大写"""
    parts = re.split(r'[,，、\s]+', text)
    result = []
    for p in parts:
        name = re.sub(r'[()（）]', '', p.strip()).upper()
        if name:
            result.append(name)
    return result


def _parse_remark_score(remark: str) -> Optional[float]:
    """备注若为 ±数字（如 +1 / -0.5）则解析为分数，否则 None"""
    if not remark:
        return None
    if _SCORE_RE.match(remark.strip()):
        try:
            return float(remark.strip())
        except ValueError:
            return None
    return None


def parse_edit_line(line: str) -> Dict[str, Any]:
    """
    解析一行纸质编辑指令为结构化 edit dict。

    入参：
        line: 原始行，如 "2026080923A<积极><ZBY,CWXC><+1>"

    出参：
        edit dict；语法/格式问题写入 error_info，此时仍返回可识别的字段。
    """
    line = line.strip()
    if not line:
        return {"raw": line, "error_info": {"type": "format_invalid", "field": "line",
                                            "invalid_values": [], "raw": line}}

    # 行首：日期 + 编号 + 操作符
    m = _LINE_HEAD.match(line)
    if not m:
        return {"raw": line, "error_info": {"type": ERROR_FORMAT_INVALID, "field": "line",
                                            "invalid_values": [], "raw": line}}

    date8, seq, op = m.groups()
    rest = line[m.end():]
    params = _PARAM.findall(rest)

    edit: Dict[str, Any] = {
        "raw": line,
        "id": f"{date8}{seq}",
        "date8": date8,
        "date": "",
        "seq": seq,
        "operation": op,
        "event": "",
        "persons": [],
        "remark": "",
        "score": None,
        "delete_all": False,
        "field": None,
        "value": None,
        "target_seq": None,
        "target_entity_id": None,
        "error_info": None,
    }

    # ---------- 日期合法性 ----------
    try:
        dt = datetime.strptime(date8, "%Y%m%d")
        edit["date"] = dt.strftime("%Y-%m-%d")
    except ValueError:
        edit["error_info"] = {"type": ERROR_DATE_INVALID, "field": "date",
                              "invalid_values": [date8], "raw": line}
        return edit

    # ---------- 按操作符解析参数 ----------
    if op == OP_ADD:
        # A 的双重语义由编号决定：
        #   seq >= 22 -> 新增事件：<事件><人员><备注可选>
        #   seq < 22  -> 在原事件上加人：<人员逗号分隔>，target_seq=原编号
        try:
            seq_int = int(seq)
        except ValueError:
            seq_int = 0
        if seq_int >= MIN_NEW_SEQ:
            # 新增事件
            if len(params) < 1 or not params[0].strip():
                edit["error_info"] = {"type": ERROR_CONTENT_MISSING, "field": "event",
                                      "invalid_values": [], "raw": line}
                return edit
            edit["event"] = params[0].strip()
            edit["persons"] = _split_persons(params[1]) if len(params) > 1 else []
            edit["remark"] = params[2].strip() if len(params) > 2 else ""
            edit["score"] = _parse_remark_score(edit["remark"])
        else:
            # 加人：参数为人员列表，目标为原编号
            if len(params) < 1 or not params[0].strip():
                edit["error_info"] = {"type": ERROR_CONTENT_MISSING, "field": "persons",
                                      "invalid_values": [], "raw": line}
                return edit
            edit["persons"] = _split_persons(params[0])
            if not edit["persons"]:
                edit["error_info"] = {"type": ERROR_PERSONS_INVALID, "field": "persons",
                                      "invalid_values": [params[0]], "raw": line}
                return edit
            edit["target_seq"] = seq

    elif op == OP_DELETE:
        # 参数为"事件"字面量 -> 删除整个事件；否则为人员列表
        if len(params) < 1 or not params[0].strip():
            edit["error_info"] = {"type": ERROR_CONTENT_MISSING, "field": "target",
                                  "invalid_values": [], "raw": line}
            return edit
        target = params[0].strip()
        if target in ("事件", "整个事件", "整条"):
            edit["delete_all"] = True
        else:
            edit["persons"] = _split_persons(target)
            if not edit["persons"]:
                edit["error_info"] = {"type": ERROR_PERSONS_INVALID, "field": "persons",
                                      "invalid_values": [target], "raw": line}
                return edit
        edit["target_seq"] = seq

    elif op == OP_CHANGE:
        if len(params) < 2 or not params[0].strip() or not params[1].strip():
            edit["error_info"] = {"type": ERROR_CONTENT_MISSING, "field": "field",
                                  "invalid_values": [], "raw": line}
            return edit
        field_raw = params[0].strip()
        value = params[1].strip()
        if field_raw in ("事件", "事件名", "event"):
            edit["field"] = FIELD_EVENT
            edit["value"] = value
        elif field_raw in ("分数", "分值", "score"):
            edit["field"] = FIELD_SCORE
            edit["value"] = value
            score = _parse_remark_score(value)
            if score is None:
                edit["error_info"] = {"type": ERROR_SCORE_INVALID, "field": "score",
                                      "invalid_values": [value], "raw": line}
                return edit
            edit["score"] = score
        else:
            edit["error_info"] = {"type": ERROR_FIELD_INVALID, "field": "field",
                                  "invalid_values": [field_raw], "raw": line}
            return edit
        edit["target_seq"] = seq

    return edit


def parse_edit_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """批量解析多行编辑指令"""
    return [parse_edit_line(line) for line in lines]


# ==================== 自测试 ====================
if __name__ == "__main__":
    samples = [
        "2026080923A<积极><ZBY,CWXC><+1>",
        "2026073112A<ZBY>",
        "2026073112D<事件>",
        "2026073112D<ZBY,CWXC>",
        "2026073112C<事件><积极>",
        "2026073112C<分数><+1>",
        "2026080901A<积极>",          # 编号冲突（<22）
        "20260809A<积极><ZBY>",        # 缺编号
        "2026073112C<备注><abc>",      # 非法字段
        "abc123",                      # 完全非法
    ]
    for s in samples:
        e = parse_edit_line(s)
        err = e.get("error_info")
        print(f"{s:42} -> op={e.get('operation')} seq={e.get('seq')} "
              f"event={e.get('event')} persons={e.get('persons')} "
              f"remark={e.get('remark')} score={e.get('score')} "
              f"delete_all={e.get('delete_all')} field={e.get('field')} "
              f"err={err.get('type') if err else None}")

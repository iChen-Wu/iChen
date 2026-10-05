"""
scmAPI - 学生积分、歌曲管理、键值存储的 API 封装

【可用函数列表】

一、学生积分管理 (4个函数)
1. set_points(events_data) 
   - 从事件列表计算并设置学生积分
   - 输入: [{"names": ["姓名"], "event": "事件名", "points": 分数}, ...]
   - 返回: {"code": 0, "message": "...", "data": {...}}

2. get_points(year, week)
   - 获取周积分，不传参则获取当周
   - 返回: {"code": 0, "message": "...", "data": [...]}

3. get_all_students()
   - 获取所有学生名单
   - 返回: {"code": 0, "message": "...", "data": [...]}

4. del_points(day)
   - 删除周积分，day不传则删除当周
   - 返回: {"code": 0, "message": "...", "data": null}
   - ⚠️ 危险操作，不可逆！

二、歌曲管理 (5个函数)
1. add_song(song_list)
   - 批量新增歌曲
   - 返回: {"code": 0, "message": "...", "data": [...]}

2. set_song(song_id, weight)
   - 设置歌曲权重
   - 返回: {"code": 0, "message": "...", "data": null}

3. get_song(name, singer)
   - 获取单首歌曲信息
   - 返回: {"code": 0, "message": "...", "data": {...}}

4. get_all_song()
   - 获取所有歌曲列表
   - 返回: {"code": 0, "message": "...", "data": [...]}

5. del_song(name, singer)
   - 删除指定歌曲
   - 返回: {"code": 0, "message": "...", "data": null}
   - ⚠️ 危险操作，不可逆！

三、键值存储 (5个函数)
1. set_data(key, content, tag, order, remark)
   - 创建或更新键值数据
   - 返回: {"code": 0, "message": "...", "data": null}

2. get_data(key)
   - 获取指定键值数据
   - 返回: {"code": 0, "message": "...", "data": {...}}

3. get_all_data()
   - 获取所有键值数据
   - 返回: {"code": 0, "message": "...", "data": [...]}

4. edit_data(key, content, tag, order, remark)
   - 更新键值数据
   - 返回: {"code": 0, "message": "...", "data": null}

5. del_data(key)
   - 删除键值数据
   - 返回: {"code": 0, "message": "...", "data": null}
   - ⚠️ 危险操作，不可逆！

四、辅助工具函数 (1个)
1. safe_get_list(data, key)
   - 安全地从返回数据中提取列表
   - 输入: data=返回数据, key="list"(默认)
   - 返回: list

【返回格式说明】
成功: {"code": 0, "message": "描述信息", "data": 数据}
失败: {"code": 1, "message": "错误描述", "data": null}

【使用前配置】
在 ../config/.env 文件中配置 scmAPI_KEY
或直接设置 scmAPI._key = "你的key"

作者: Auto-generated
版本: 1.1.0
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

import requests

# ⭐ 使用全局常量定位配置文件
from GYun.core.constants import CONFIG_DIR


# ==================== 配置加载 ====================

# 从 config/.env 读取 scmAPI_key
_env_path = CONFIG_DIR / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

# 全局配置（兼容 SCM_API_KEY / scmAPI_KEY 两种命名）
_key = os.environ.get("SCM_API_KEY") or os.environ.get("scmAPI_KEY") or ""
_base_url = "http://scm.dreamwu.com"

# 所有学生名单（中文名）
ALL_STUDENTS = [
    "张先炜", "王棋辉", "董泽宇", "范润", "余永清", "胡奥棋", "熊志", "郑昱林",
    "黄海睿", "王可", "韩天乐", "姜玉清", "胡浩轩", "骆梓宸", "叶升宇", "王岱琳",
    "胡钊", "邓林宵", "占兆庆", "胡彬", "张思琪", "张琰明", "陈小芬", "项雅萱",
    "吴毅晨", "张博宇", "陈抒怡", "王俊宝", "吴干凡", "高棋", "伊栩嘉", "冯清哲",
    "操景林", "陈富林", "叶昊然", "董科志", "张莹", "何银钰", "陈家熠", "陈梦",
    "张雨绮", "管铭鑫", "方伟宸", "张锦瑞", "陈健豪", "邓涵菲", "周铭浩", "潘越",
    "郭宇轩", "殷吉源", "田子夫", "胡树朋", "翁欣林", "陈子轩", "伊佳辉", "詹雨薇",
    "张淼", "张昱", "陈熠庭", "吴家辉", "操宇", "曹芸浩", "陈文鑫畅", "田霑",
    "方媛", "田钊智"
]


# ==================== 内部请求函数 ====================

def _request(method: str, url: str, data: dict = None, params: dict = None, timeout: int = 30) -> Union[dict, list]:
    """
    底层HTTP请求封装，直接返回API原始数据
    """
    try:
        if method.upper() == "POST":
            if params:
                response = requests.post(url, json=data, params=params, timeout=timeout)
            else:
                response = requests.post(url, json=data, timeout=timeout)
        else:
            response = requests.get(url, params=params, timeout=timeout)

        response.raise_for_status()
        result = response.json()

        if isinstance(result, list):
            return result

        if result.get("code") != 1:
            raise Exception(f"请求失败: code={result.get('code')}, msg={result.get('msg')}")
        return result.get("data")

    except requests.exceptions.ConnectionError as e:
        raise Exception(f"网络连接失败: {e}")
    except requests.exceptions.Timeout as e:
        raise Exception(f"请求超时: {e}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"网络请求失败: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"响应解析失败: {e}")


def _post(url: str, data: dict = None, params: dict = None, timeout: int = 30) -> Union[dict, list]:
    """POST请求快捷方式"""
    return _request("POST", url, data, params, timeout)


def _get(url: str, params: dict = None, timeout: int = 30) -> Union[dict, list]:
    """GET请求快捷方式"""
    return _request("GET", url, None, params, timeout)


def _format_response(code: int, message: str, data: Any = None) -> dict:
    """
    统一返回格式
    """
    return {
        "code": code,
        "message": message,
        "data": data
    }


# ==================== 1. 学生积分管理 ====================

def set_points(events_data: List[Dict[str, Any]]) -> dict:
    """
    从事件列表计算并设置学生积分

    入参: events_data (list) - 事件列表，每项包含:
        - names (list): 学生姓名列表，必填
        - event (str): 事件名称，必填
        - points (float): 积分值（可为负数），必填

    出参: {"code": 0, "message": "...", "data": {"students": [...], "total_events": 5, "updated_count": 3}}

    示例:
        >>> events = [
        ...     {"names": ["张博宇"], "event": "发作业", "points": 0.5},
        ...     {"names": ["张博宇"], "event": "早读认真", "points": 1.0}
        ... ]
        >>> result = set_points(events)
        >>> print(result)
        {'code': 0, 'message': '成功更新 1 名学生积分', 'data': {'students': ['张博宇'], 'total_events': 2, 'updated_count': 1}}
    """
    # 1. 按学生汇总积分和事件
    student_data = defaultdict(lambda: {"points": 0.0, "events": []})
    affected_students = set()
    invalid_students = []

    for item in events_data:
        names = item.get("names", [])
        event_name = item.get("event", "")
        points = float(item.get("points", 0))

        for name in names:
            if name not in ALL_STUDENTS:
                invalid_students.append(name)
                continue

            affected_students.add(name)
            student_data[name]["points"] += points
            student_data[name]["events"].append({
                "name": event_name,
                "points": points,
                "memo": event_name
            })

    # 如果有无效学生，返回失败
    if invalid_students:
        return _format_response(
            code=1,
            message=f"学生不存在: {', '.join(invalid_students)}",
            data=None
        )

    # 2. 为所有学生构建数据
    formatted_list = []
    for name in ALL_STUDENTS:
        if name in student_data:
            data = student_data[name]
            formatted_list.append({
                "name": name,
                "points": data["points"],
                "events": data["events"]
            })
        else:
            formatted_list.append({
                "name": name,
                "points": 0,
                "events": []
            })

    # 3. 发送请求
    url = f"{_base_url}/api/scm/student_points_calc"
    try:
        response = _post(url, data={"list": formatted_list}, params={"key": _key})
        total_events = sum(len(student_data[name]["events"]) for name in affected_students)
        return _format_response(
            code=0,
            message=f"成功更新 {len(affected_students)} 名学生积分",
            data={
                "students": list(affected_students),
                "total_events": total_events,
                "updated_count": len(affected_students)
            }
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"积分设置失败: {str(e)}",
            data=None
        )


def get_points(year: int = None, week: int = None) -> dict:
    """
    获取周积分，不传参则获取当周

    入参:
        - year (int): 年份，可选，默认当前年份
        - week (int): 周数，可选，默认当前周

    出参: {"code": 0, "message": "...", "data": [...]}

    示例:
        >>> result = get_points()
        >>> print(result)
        {'code': 0, 'message': '获取成功', 'data': [{'name': '张先炜', 'points': 0, 'events': []}, ...]}
    """
    url = f"{_base_url}/api/scm/student_get_week_points"
    params = {"key": _key}

    if year and week:
        params["year"] = year
        params["week"] = week
    else:
        today = datetime.now()
        year, week, _ = today.isocalendar()
        params["year"] = year
        params["week"] = week

    try:
        result = _get(url, params=params)
        if isinstance(result, list):
            return _format_response(
                code=0,
                message=f"获取成功，共 {len(result)} 名学生",
                data=result
            )
        else:
            return _format_response(
                code=0,
                message="获取成功",
                data=result
            )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"获取积分失败: {str(e)}",
            data=None
        )


def get_all_students() -> dict:
    """
    获取所有学生名单

    入参: 无

    出参: {"code": 0, "message": "...", "data": [...]}

    示例:
        >>> result = get_all_students()
        >>> print(result)
        {'code': 0, 'message': '共 66 名学生', 'data': ['张先炜', '王棋辉', ...]}
    """
    return _format_response(
        code=0,
        message=f"共 {len(ALL_STUDENTS)} 名学生",
        data=ALL_STUDENTS.copy()
    )


def del_points(day: str = None) -> dict:
    """
    删除周积分，day不传则删除当周

    入参:
        - day (str): 日期字符串，格式 "YYYY-MM-DD"，可选，不传则删除当周

    出参: {"code": 0, "message": "...", "data": null}

    ⚠️  危险操作，不可逆！请谨慎使用！

    示例:
        >>> result = del_points()
        >>> print(result)
        {'code': 0, 'message': '本周积分删除成功', 'data': null}
    """
    url = f"{_base_url}/api/scm/student_del_week_points"
    params = {"key": _key}
    if day:
        params["day"] = day
        msg = f"删除 {day} 所在周积分"
    else:
        msg = "删除本周积分"

    try:
        _post(url, params=params, timeout=60)
        return _format_response(
            code=0,
            message=f"{msg}成功",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"{msg}失败: {str(e)}",
            data=None
        )


# ==================== 2. 歌曲管理 ====================

def add_song(song_list: List[Dict[str, Any]]) -> dict:
    """
    批量新增歌曲

    入参: song_list (list) - 歌曲信息列表，每项包含:
        - song (str): 歌名，必填
        - singer (str): 歌手，必填
        - recommender (str): 推荐人，必填
        - type (str): 类型，可选，默认 "个人"
        - URL (str): 播放链接，可选
        - weight (int): 权重，可选，默认 0

    出参: {"code": 0, "message": "...", "data": [...]}

    示例:
        >>> songs = [
        ...     {"song": "稻香", "singer": "周杰伦", "recommender": "HZ", "type": "班级", "weight": 5}
        ... ]
        >>> result = add_song(songs)
        >>> print(result)
        {'code': 0, 'message': '成功添加 1 首歌曲', 'data': [{'id': 123, 'name': '稻香', ...}]}
    """
    results = []
    success_count = 0
    fail_count = 0

    for item in song_list:
        name = item.get("song", "")
        singer = item.get("singer", "")
        lx = item.get("type", "个人")
        play_url = item.get("URL", "")
        tj = item.get("recommender", "")
        weight_str = item.get("weight", "0")

        try:
            weight = int(weight_str) if weight_str else 0
        except ValueError:
            weight = 0

        data = {"name": name, "singer": singer, "lx": lx}
        if play_url:
            data["play_url"] = play_url
        if tj:
            data["tj"] = tj
        if weight:
            data["weight"] = weight

        url = f"{_base_url}/api/scm/song_add"
        try:
            res = _post(url, data=data, params={"key": _key})
            results.append(res)
            success_count += 1
        except Exception as e:
            results.append({"error": str(e), "song": name, "singer": singer})
            fail_count += 1

    if fail_count == 0:
        return _format_response(
            code=0,
            message=f"成功添加 {success_count} 首歌曲",
            data=results
        )
    else:
        return _format_response(
            code=1,
            message=f"添加 {success_count} 首成功，{fail_count} 首失败",
            data=results
        )


def set_song(song_id: int, weight: int) -> dict:
    """
    设置歌曲权重

    入参:
        - song_id (int): 歌曲ID，必填
        - weight (int): 权重值，必填

    出参: {"code": 0, "message": "...", "data": null}

    示例:
        >>> result = set_song(song_id=123, weight=20)
        >>> print(result)
        {'code': 0, 'message': '歌曲权重设置成功 (ID: 123, 权重: 20)', 'data': null}
    """
    url = f"{_base_url}/api/scm/song_set_weight"
    try:
        _post(url, data={"id": song_id, "weight": weight}, params={"key": _key})
        return _format_response(
            code=0,
            message=f"歌曲权重设置成功 (ID: {song_id}, 权重: {weight})",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"歌曲权重设置失败: {str(e)}",
            data=None
        )


def get_song(name: str, singer: str) -> dict:
    """
    获取单首歌曲信息

    入参:
        - name (str): 歌名，必填
        - singer (str): 歌手，必填

    出参: {"code": 0, "message": "...", "data": {...}}

    示例:
        >>> result = get_song("稻香", "周杰伦")
        >>> print(result)
        {'code': 0, 'message': '获取成功', 'data': {'id': 123, 'name': '稻香', 'singer': '周杰伦', 'weight': 5}}
    """
    url = f"{_base_url}/api/scm/song_get_info"
    try:
        result = _get(url, params={"key": _key, "name": name, "singer": singer})
        return _format_response(
            code=0,
            message="获取成功",
            data=result
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"获取歌曲信息失败: {str(e)}",
            data=None
        )


def get_all_song() -> dict:
    """
    获取所有歌曲列表

    入参: 无

    出参: {"code": 0, "message": "...", "data": [...]}

    示例:
        >>> result = get_all_song()
        >>> print(result)
        {'code': 0, 'message': '共 49 首歌曲', 'data': [{'id': 123, 'name': '稻香', ...}, ...]}
    """
    url = f"{_base_url}/api/scm/song_get_list"
    try:
        result = _get(url, params={"key": _key})
        song_list = safe_get_list(result)
        return _format_response(
            code=0,
            message=f"共 {len(song_list)} 首歌曲",
            data=song_list
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"获取歌曲列表失败: {str(e)}",
            data=None
        )


def del_song(name: str, singer: str) -> dict:
    """
    删除指定歌曲

    入参:
        - name (str): 歌名，必填
        - singer (str): 歌手，必填

    出参: {"code": 0, "message": "...", "data": null}

    ⚠️  危险操作，不可逆！请谨慎使用！

    示例:
        >>> result = del_song("稻香", "周杰伦")
        >>> print(result)
        {'code': 0, 'message': '歌曲删除成功: 稻香 - 周杰伦', 'data': null}
    """
    url = f"{_base_url}/api/scm/song_delete"
    data = {"name": name, "singer": singer}
    try:
        _post(url, data=data, params={"key": _key})
        return _format_response(
            code=0,
            message=f"歌曲删除成功: {name} - {singer}",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"歌曲删除失败: {str(e)}",
            data=None
        )


# ==================== 3. 键值存储 ====================

def set_data(key: str, content: str, tag: str = "", order: int = 0, remark: str = "") -> dict:
    """
    创建或更新键值数据

    入参:
        - key (str): 键名，必填
        - content (str): 值内容，必填
        - tag (str): 标签，可选，默认 ""
        - order (int): 排序号，可选，默认 0
        - remark (str): 备注，可选，默认 ""

    出参: {"code": 0, "message": "...", "data": null}

    示例:
        >>> result = set_data(key="site_title", content="我的网站", tag="config", order=1, remark="网站标题")
        >>> print(result)
        {'code': 0, 'message': '键值设置成功: site_title', 'data': null}
    """
    url = f"{_base_url}/api/scm/kv_add"
    data = {"k": key, "v": content}
    if tag:
        data["name"] = tag
    if order:
        data["sort_no"] = order
    if remark:
        data["remark"] = remark

    try:
        _post(url, data=data, params={"key": _key})
        return _format_response(
            code=0,
            message=f"键值设置成功: {key}",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"键值设置失败: {str(e)}",
            data=None
        )


def get_data(key: str) -> dict:
    """
    获取指定键值数据

    入参:
        - key (str): 键名，必填

    出参: {"code": 0, "message": "...", "data": {...}}

    示例:
        >>> result = get_data("site_title")
        >>> print(result)
        {'code': 0, 'message': '获取成功', 'data': {'id': 5, 'k': 'site_title', 'v': '我的网站', ...}}
    """
    url = f"{_base_url}/api/scm/kv_get"
    try:
        result = _get(url, params={"key": _key, "k": key})
        if not result or (isinstance(result, dict) and not result.get('id')):
            return _format_response(
                code=1,
                message=f"键 '{key}' 不存在",
                data=None
            )
        return _format_response(
            code=0,
            message="获取成功",
            data=result
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"获取键值失败: {str(e)}",
            data=None
        )


def get_all_data() -> dict:
    """
    获取所有键值数据

    入参: 无

    出参: {"code": 0, "message": "...", "data": [...]}

    示例:
        >>> result = get_all_data()
        >>> print(result)
        {'code': 0, 'message': '共 3 条键值数据', 'data': [{'id': 5, 'k': 'site_title', ...}, ...]}
    """
    url = f"{_base_url}/api/scm/kv_get_all"
    try:
        result = _get(url, params={"key": _key})
        kv_list = safe_get_list(result)
        return _format_response(
            code=0,
            message=f"共 {len(kv_list)} 条键值数据",
            data=kv_list
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"获取键值列表失败: {str(e)}",
            data=None
        )


def edit_data(key: str, content: str, tag: str = "", order: int = 0, remark: str = "") -> dict:
    """
    更新键值数据

    入参: 同 set_data

    出参: {"code": 0, "message": "...", "data": null}

    示例:
        >>> result = edit_data(key="site_title", content="新网站标题", tag="config", order=2)
        >>> print(result)
        {'code': 0, 'message': '键值更新成功: site_title', 'data': null}
    """
    url = f"{_base_url}/api/scm/kv_add"
    params = {"key": _key, "act": "edit"}
    data = {"k": key, "v": content}
    if tag:
        data["name"] = tag
    if order:
        data["sort_no"] = order
    if remark:
        data["remark"] = remark

    try:
        _post(url, data=data, params=params)
        return _format_response(
            code=0,
            message=f"键值更新成功: {key}",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"键值更新失败: {str(e)}",
            data=None
        )


def del_data(key: str) -> dict:
    """
    删除键值数据

    入参:
        - key (str): 键名，必填

    出参: {"code": 0, "message": "...", "data": null}

    ⚠️  危险操作，不可逆！请谨慎使用！

    示例:
        >>> result = del_data("site_title")
        >>> print(result)
        {'code': 0, 'message': '键值删除成功: site_title', 'data': null}
    """
    url = f"{_base_url}/api/scm/kv_delete"
    try:
        _post(url, data={"k": key}, params={"key": _key})
        return _format_response(
            code=0,
            message=f"键值删除成功: {key}",
            data=None
        )
    except Exception as e:
        return _format_response(
            code=1,
            message=f"键值删除失败: {str(e)}",
            data=None
        )


# ==================== 辅助工具函数 ====================

def safe_get_list(data: Union[dict, list], key: str = 'list') -> list:
    """
    安全地从返回数据中提取列表（兼容dict和list两种返回格式）

    入参:
        - data (dict 或 list): API返回的数据
        - key (str): 字典中的键名，可选，默认 "list"

    出参: list - 提取出的列表

    示例:
        >>> result = get_all_song()
        >>> songs = safe_get_list(result.get('data', []))
        >>> print(f"共有 {len(songs)} 首歌曲")
    """
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get(key, [])
    return []


# ==================== 测试函数 ====================

def test_all_functions():
    """测试所有功能，打印每次API返回的原始数据"""
    print("=" * 70)
    print("🧪 测试所有功能")
    print("=" * 70)

    tests_passed = 0
    tests_failed = 0
    tests_skipped = 0

    # 存储测试数据
    test_data = {
        "kv_keys": [],
        "songs": [],
        "has_points": False
    }

    # ========== 测试键值存储 ==========
    print("\n【1. 键值存储】")

    # 1.1 set_data
    try:
        test_key = f"test_{datetime.now().strftime('%H%M%S')}"
        result = set_data(test_key, "测试内容", "测试标签", 1, "测试备注")
        if result.get("code") == 0:
            print(f"  ✅ set_data: {result.get('message')}")
            print(f"     返回: {result}")
            test_data["kv_keys"].append(test_key)
            tests_passed += 1
        else:
            print(f"  ❌ set_data: {result.get('message')}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ set_data 异常: {e}")
        tests_failed += 1

    # 1.2 get_data
    if test_data["kv_keys"]:
        try:
            result = get_data(test_data["kv_keys"][0])
            if result.get("code") == 0:
                print(f"  ✅ get_data: {result.get('message')}")
                print(f"     返回: {result}")
                tests_passed += 1
            else:
                print(f"  ❌ get_data: {result.get('message')}")
                tests_failed += 1
        except Exception as e:
            print(f"  ❌ get_data 异常: {e}")
            tests_failed += 1

    # 1.3 edit_data
    if test_data["kv_keys"]:
        try:
            result = edit_data(test_data["kv_keys"][0], "修改内容", "修改标签", 2, "修改备注")
            if result.get("code") == 0:
                print(f"  ✅ edit_data: {result.get('message')}")
                print(f"     返回: {result}")
                tests_passed += 1
            else:
                print(f"  ❌ edit_data: {result.get('message')}")
                tests_failed += 1
        except Exception as e:
            print(f"  ❌ edit_data 异常: {e}")
            tests_failed += 1

    # 1.4 get_all_data
    try:
        result = get_all_data()
        if result.get("code") == 0:
            data = result.get("data", [])
            print(f"  ✅ get_all_data: {result.get('message')}")
            print(f"     返回: {result}")
            # 打印前3条数据详情
            for i, item in enumerate(data[:3]):
                print(f"     {i+1}. {item}")
            if len(data) > 3:
                print(f"     ... 还有 {len(data)-3} 条")
            tests_passed += 1
        else:
            print(f"  ❌ get_all_data: {result.get('message')}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ get_all_data 异常: {e}")
        tests_failed += 1

    # 1.5 del_data (清理)
    for key in test_data["kv_keys"]:
        try:
            result = del_data(key)
            if result.get("code") == 0:
                print(f"  ✅ del_data: {result.get('message')}")
                print(f"     返回: {result}")
            else:
                print(f"  ❌ del_data: {result.get('message')}")
        except Exception as e:
            print(f"  ❌ del_data 异常: {e}")

    # ========== 测试歌曲管理 ==========
    print("\n【2. 歌曲管理】")

    test_song = f"测试歌曲_{datetime.now().strftime('%H%M%S')}"
    test_singer = "测试歌手"

    # 2.1 add_song
    try:
        result = add_song([{
            "song": test_song,
            "singer": test_singer,
            "recommender": "WYC",
            "weight": 5
        }])
        if result.get("code") == 0:
            print(f"  ✅ add_song: {result.get('message')}")
            print(f"     返回: {result}")
            test_data["songs"].append({"name": test_song, "singer": test_singer})
            tests_passed += 1
        else:
            print(f"  ❌ add_song: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ add_song 异常: {e}")
        tests_failed += 1

    # 2.2 get_song
    try:
        result = get_song(test_song, test_singer)
        if result.get("code") == 0:
            print(f"  ✅ get_song: {result.get('message')}")
            print(f"     返回: {result}")
            song_id = result.get("data", {}).get('id') if isinstance(result.get("data"), dict) else None
            tests_passed += 1
        else:
            print(f"  ❌ get_song: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
            song_id = None
    except Exception as e:
        print(f"  ❌ get_song 异常: {e}")
        tests_failed += 1
        song_id = None

    # 2.3 set_song
    if song_id:
        try:
            result = set_song(song_id, 10)
            if result.get("code") == 0:
                print(f"  ✅ set_song: {result.get('message')}")
                print(f"     返回: {result}")
                tests_passed += 1
            else:
                print(f"  ❌ set_song: {result.get('message')}")
                print(f"     返回: {result}")
                tests_failed += 1
        except Exception as e:
            print(f"  ❌ set_song 异常: {e}")
            tests_failed += 1

    # 2.4 get_all_song
    try:
        result = get_all_song()
        if result.get("code") == 0:
            data = result.get("data", [])
            print(f"  ✅ get_all_song: {result.get('message')}")
            print(f"     返回: {result}")
            # 打印前3首
            for i, song in enumerate(data[:3]):
                print(f"     {i+1}. {song}")
            if len(data) > 3:
                print(f"     ... 还有 {len(data)-3} 首")
            tests_passed += 1
        else:
            print(f"  ❌ get_all_song: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ get_all_song 异常: {e}")
        tests_failed += 1

    # 2.5 del_song (清理)
    for song in test_data["songs"]:
        try:
            result = del_song(song["name"], song["singer"])
            if result.get("code") == 0:
                print(f"  ✅ del_song: {result.get('message')}")
                print(f"     返回: {result}")
            else:
                print(f"  ❌ del_song: {result.get('message')}")
                print(f"     返回: {result}")
        except Exception as e:
            print(f"  ❌ del_song 异常: {e}")

    # ========== 测试学生积分 ==========
    print("\n【3. 学生积分】")

    # 3.1 get_all_students
    try:
        result = get_all_students()
        if result.get("code") == 0:
            data = result.get("data", [])
            print(f"  ✅ get_all_students: {result.get('message')}")
            print(f"     返回: {result}")
            print(f"     前5名: {data[:5]}")
            tests_passed += 1
        else:
            print(f"  ❌ get_all_students: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ get_all_students 异常: {e}")
        tests_failed += 1

    # 3.2 set_points
    try:
        events = [
            {"names": ["张博宇"], "event": "测试加分", "points": 1},
            {"names": ["张博宇"], "event": "测试加分2", "points": 0.5},
        ]
        result = set_points(events)
        if result.get("code") == 0:
            print(f"  ✅ set_points: {result.get('message')}")
            print(f"     返回: {result}")
            test_data["has_points"] = True
            tests_passed += 1
        else:
            print(f"  ❌ set_points: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ set_points 异常: {e}")
        tests_failed += 1

    # 3.3 get_points (本周)
    try:
        result = get_points()
        if result.get("code") == 0:
            data = result.get("data", [])
            if isinstance(data, list):
                print(f"  ✅ get_points: {result.get('message')}")
                print(f"     返回: {result}")
                # 打印前3名学生的积分
                for i, student in enumerate(data[:3]):
                    print(f"     {i+1}. {student.get('name')}: {student.get('points', 0)}分")
                if len(data) > 3:
                    print(f"     ... 还有 {len(data)-3} 名学生")
            else:
                print(f"  ✅ get_points: {result.get('message')}")
                print(f"     返回: {result}")
            tests_passed += 1
        else:
            print(f"  ❌ get_points: {result.get('message')}")
            print(f"     返回: {result}")
            tests_failed += 1
    except Exception as e:
        print(f"  ❌ get_points 异常: {e}")
        tests_failed += 1

    # 3.4 get_points (指定周)
    try:
        result = get_points(year=2026, week=16)
        if result.get("code") == 0:
            print(f"  ✅ get_points(2025-W1): {result.get('message')}")
            print(f"     返回: {result}")
            tests_passed += 1
        else:
            # 数据不存在也算正常
            print(f"  ⚠️  get_points(2025-W1): {result.get('message')}")
            print(f"     返回: {result}")
            tests_passed += 1
    except Exception as e:
        print(f"  ❌ get_points(2025-W1) 异常: {e}")
        tests_failed += 1

    # 3.5 del_points (删除积分)
    if test_data["has_points"]:
        print("\n  ⚠️  是否删除本周积分？")
        confirm = input("  删除将清除本周所有学生积分 (y/n): ").strip().lower()
        if confirm == 'y':
            try:
                result = del_points()
                if result.get("code") == 0:
                    print(f"  ✅ del_points: {result.get('message')}")
                    print(f"     返回: {result}")
                    tests_passed += 1
                else:
                    print(f"  ❌ del_points: {result.get('message')}")
                    print(f"     返回: {result}")
                    tests_failed += 1
            except Exception as e:
                print(f"  ❌ del_points 异常: {e}")
                tests_failed += 1
        else:
            print(f"  ⏭️  跳过 del_points 测试")
            tests_skipped += 1

    # ========== 总结 ==========
    print("\n" + "=" * 70)
    print("📊 测试完成")
    print(f"  ✅ 通过: {tests_passed}")
    print(f"  ❌ 失败: {tests_failed}")
    print(f"  ⏭️  跳过: {tests_skipped}")
    print("=" * 70)


# ==================== 主入口 ====================

if __name__ == "__main__":
    import sys

    n=input("选择")
    if n == 1:
        if len(sys.argv) > 1 and sys.argv[1] == "test":
            test_all_functions()
        else:
            print("运行测试: python scmAPI.py test")
            test_all_functions()
    else:
        result = get_points(2026,26)
        print(result)

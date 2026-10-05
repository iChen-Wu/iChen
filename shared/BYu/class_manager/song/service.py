# service.py
# =============================================================================
# 歌曲管理业务逻辑层
# =============================================================================

import json
import re
from typing import List, Dict, Any, Optional

# ⭐ 包绝对导入
from GYun.scmAPI import add_song, set_song, get_song, get_all_song, del_song, safe_get_list
from BYu.class_manager.song.config import NAME_CODE_MAP, ABBR_TO_NAME
from BYu.class_manager.song.vision_adapter import recognize_songs_from_images


# ============================================================
# 辅助函数
# ============================================================

def normalize_recommender(name: str) -> str:
    """
    标准化推荐人为缩写形式（如 "张博宇" -> "ZBY"）
    后端 scmAPI 要求推荐人必须是有效的学生，缩写和中文全名都支持，
    但为了统一，全部转为缩写。
    """
    if not name:
        return ""
    name = name.strip()
    # 如果输入已经是缩写（在 ABBR_TO_NAME 中），直接返回
    if name.upper() in ABBR_TO_NAME:
        return name.upper()
    # 如果输入是中文全名，转为缩写
    if name in NAME_CODE_MAP:
        return NAME_CODE_MAP[name]
    # 尝试去掉空格和特殊字符后再匹配
    clean = re.sub(r'[^a-zA-Z\u4e00-\u9fff]', '', name)
    if clean.upper() in ABBR_TO_NAME:
        return clean.upper()
    if clean in NAME_CODE_MAP:
        return NAME_CODE_MAP[clean]
    # 如果还是无法匹配，返回原字符串（后端会报错，但让用户知道）
    return name


def validate_type(type_str: str) -> str:
    """校验歌曲类型，只允许 '班级' 或 '个人'"""
    if type_str in ["班级", "个人"]:
        return type_str
    if type_str in ["班", "class", "Class", "CLASS"]:
        return "班级"
    if type_str in ["个", "person", "Person", "PERSON"]:
        return "个人"
    return "个人"  # 默认


# ============================================================
# 业务函数
# ============================================================

def add_songs_from_input(songs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    批量添加歌曲到歌单

    入参格式：
        [
            {
                "song": "稻香",
                "singer": "周杰伦",
                "recommender": "ZBY",      # 中文全名或缩写均可
                "type": "班级",            # "班级" 或 "个人"
                "weight": 10              # 整数
            }
        ]

    出参：
        {
            "success": True/False,
            "message": "描述信息",
            "data": API返回的数据,
            "error_details": [...]       # 失败时返回详细错误
        }
    """
    # ---- 标准化数据 ----
    for s in songs:
        s["recommender"] = normalize_recommender(s.get("recommender", ""))
        s["type"] = validate_type(s.get("type", "个人"))
        try:
            s["weight"] = int(s.get("weight", 5))
        except (TypeError, ValueError):
            s["weight"] = 5

    # ---- 调试打印 ----
    print("\n" + "=" * 60)
    print("【DEBUG】发送给 scmAPI.add_song 的数据：")
    print("=" * 60)
    print(json.dumps(songs, ensure_ascii=False, indent=2))
    print("=" * 60)

    # ---- 调用 API ----
    result = add_song(songs)

    # ---- 打印返回 ----
    print("\n" + "=" * 60)
    print("【DEBUG】scmAPI.add_song 完整返回：")
    print("=" * 60)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 60)

    # ---- 解析结果 ----
    if result.get("code") == 0:
        return {
            "success": True,
            "message": result.get("message", "添加成功"),
            "data": result.get("data")
        }
    else:
        # 提取每个失败条目的详细错误
        error_details = []
        data = result.get("data", [])
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "error" in item:
                    error_details.append({
                        "song": item.get("song", "未知"),
                        "singer": item.get("singer", "未知"),
                        "error": item.get("error")
                    })
        return {
            "success": False,
            "message": result.get("message", "添加失败"),
            "data": result.get("data"),
            "error_details": error_details
        }


def get_song_info(name: str, singer: str) -> Dict[str, Any]:
    """
    查询单首歌曲信息

    入参：
        name: 歌名
        singer: 歌手

    出参：
        {
            "success": True/False,
            "message": "描述信息",
            "data": {...}  # 歌曲详情
        }
    """
    result = get_song(name, singer)
    if result.get("code") == 0:
        return {"success": True, "data": result.get("data")}
    else:
        return {"success": False, "message": result.get("message", "未找到歌曲")}


def get_all_songs() -> List[Dict]:
    """
    获取所有歌曲列表

    出参：
        List[Dict] - 歌曲列表，每项包含 id, name, singer, weight, tj, tj_name, lx, lx_name 等
    """
    result = get_all_song()
    if result.get("code") == 0:
        return safe_get_list(result.get("data", []))
    return []


def set_song_weight(song_id: int, weight: int) -> Dict[str, Any]:
    """
    修改歌曲权重

    入参：
        song_id: 歌曲ID
        weight: 新权重（整数）

    出参：
        {"success": True/False, "message": "描述信息"}
    """
    result = set_song(song_id, weight)
    if result.get("code") == 0:
        return {"success": True, "message": result.get("message", f"权重已改为 {weight}")}
    else:
        return {"success": False, "message": result.get("message", "修改失败")}


def delete_song(name: str, singer: str) -> Dict[str, Any]:
    """
    删除歌曲

    入参：
        name: 歌名
        singer: 歌手

    出参：
        {"success": True/False, "message": "描述信息"}
    """
    result = del_song(name, singer)
    if result.get("code") == 0:
        return {"success": True, "message": result.get("message", f"已删除 {name} - {singer}")}
    else:
        return {"success": False, "message": result.get("message", "删除失败")}


def restore_song(
    name: str,
    singer: str,
    new_weight: int = 5,
    recommender: str = None,
    song_type: str = "班级"
) -> Dict[str, Any]:
    """
    回溯单首歌曲：先删除，再重新添加
    注意：此函数用于单首歌曲回溯，批量回溯在 CLI 中直接实现

    入参：
        name: 歌名
        singer: 歌手
        new_weight: 新权重（默认5）
        recommender: 推荐人（必须提供）
        song_type: 类型（"班级" 或 "个人"）

    出参：
        {
            "success": True/False,
            "message": "描述信息",
            "action": "restored" | "re_added" | "delete_failed" | "need_recommender" | "re_add_failed"
        }
    """
    # 1. 查询歌曲是否存在
    info = get_song_info(name, singer)

    if info["success"]:
        data = info["data"]
        current_weight = data.get("weight", 0)
        song_id = data.get("id")

        print(f"📌 找到歌曲: {name} - {singer} (ID: {song_id}, 当前权重: {current_weight})")
        print("🗑️ 执行删除...")

        del_result = delete_song(name, singer)
        if not del_result["success"]:
            return {
                "success": False,
                "message": f"删除失败: {del_result.get('message')}",
                "action": "delete_failed"
            }
        print("✅ 删除成功")
    else:
        print(f"ℹ️ 歌曲不存在，将作为新歌添加")

    # 2. 检查推荐人
    if not recommender:
        return {
            "success": False,
            "message": "需要推荐人才能重新添加",
            "action": "need_recommender"
        }

    # 3. 重新添加
    print(f"➕ 重新添加: {name} - {singer} (推荐人: {recommender}, 权重: {new_weight})")

    songs = [{
        "song": name,
        "singer": singer,
        "recommender": recommender,
        "type": song_type,
        "weight": new_weight
    }]

    result = add_songs_from_input(songs)
    if result["success"]:
        return {
            "success": True,
            "message": f"✅ 回溯成功：已删除并重新上传 {name} - {singer}，权重 {new_weight}",
            "action": "restored"
        }
    else:
        return {
            "success": False,
            "message": f"重新添加失败: {result.get('message')}",
            "action": "re_add_failed",
            "error_details": result.get("error_details")
        }


def recognize_songs_from_images_service(
    image_paths: List[str],
    verbose: bool = False
) -> List[List[Dict[str, str]]]:
    """
    从图片识别歌曲列表，按图片分组返回

    入参：
        image_paths: 图片路径列表
        verbose: 是否打印调试信息

    出参：
        List[List[Dict]] - 每个图片对应一个子列表
            每个子列表包含该图片识别的歌曲
            每首歌格式: {"name": "...", "singer": "...", "recommender": "...", "type": "...", "weight": ...}
    """
    return recognize_songs_from_images(image_paths, verbose=verbose)


def get_statistics() -> Dict[str, Any]:
    """
    获取歌单统计信息

    出参：
        {
            "total": 总歌曲数,
            "active_count": 活跃歌曲数（权重>0）,
            "max_weight": 最高权重,
            "top_songs": 权重 Top 5 列表,
            "recommender_stats": 推荐人排行（前10）
        }
    """
    songs = get_all_songs()
    if not songs:
        return {
            "total": 0,
            "active_count": 0,
            "max_weight": 0,
            "top_songs": [],
            "recommender_stats": []
        }

    # 活跃歌曲（权重 > 0）
    active = [s for s in songs if s.get("weight", 0) > 0]
    active.sort(key=lambda x: int(x.get("weight", 0)), reverse=True)

    # 推荐人统计
    stats = {}
    for s in songs:
        rec = s.get("tj_name", "") or s.get("tj", "")
        if rec:
            stats[rec] = stats.get(rec, 0) + 1

    return {
        "total": len(songs),
        "active_count": len(active),
        "max_weight": active[0].get("weight", 0) if active else 0,
        "top_songs": active[:5],
        "recommender_stats": sorted(stats.items(), key=lambda x: x[1], reverse=True)[:10]
    }
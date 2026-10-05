"""歌曲管理 App - 逻辑入口

外壳化 src/BYu/class_manager/song：业务逻辑不重写，这里只做 action 路由。
依赖库：BYu.class_manager.song.service（scmAPI 后端；不可用时返回 ok:false 的明确错误）。

run(params) 为 App 规范固定入口，params 形如 {"action": "...", "payload": {...}}。
"""
from typing import Dict, Any


def _load_service():
    """惰性加载 song 业务层，import 失败时给出可读错误。"""
    from BYu.class_manager.song import service as song_service
    return song_service


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    action = params.get("action", "list")
    payload = params.get("payload") or {}

    try:
        s = _load_service()
    except Exception as e:  # 库缺失/环境问题：不拖垮总台
        return {"ok": False, "error": f"song 业务库加载失败: {e}"}

    try:
        if action == "list":
            songs = s.get_all_songs()
            return {"ok": True, "data": songs, "message": f"共 {len(songs)} 首"}

        if action == "stats":
            stats = s.get_statistics()
            return {"ok": True, "data": stats}

        if action == "add":
            songs = payload.get("songs") or []
            if not songs:
                return {"ok": False, "error": "缺少 songs 参数"}
            result = s.add_songs_from_input(songs)
            return {
                "ok": bool(result.get("success")),
                "message": result.get("message"),
                "data": result.get("data"),
                "error_details": result.get("error_details"),
            }

        if action == "weight":
            song_id = payload.get("id")
            weight = payload.get("weight")
            if song_id is None or weight is None:
                return {"ok": False, "error": "缺少 id / weight 参数"}
            result = s.set_song_weight(int(song_id), int(weight))
            return {"ok": bool(result.get("success")), "message": result.get("message")}

        if action == "delete":
            name = payload.get("name")
            singer = payload.get("singer")
            if not name or not singer:
                return {"ok": False, "error": "缺少 name / singer 参数"}
            result = s.delete_song(name, singer)
            return {"ok": bool(result.get("success")), "message": result.get("message")}

        return {"ok": False, "error": f"未知 action: {action}"}
    except Exception as e:
        return {"ok": False, "error": f"{action} 执行异常: {e}"}


if __name__ == "__main__":
    import json
    print(json.dumps(run({"action": "ping"}), ensure_ascii=False))

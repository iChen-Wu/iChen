def run(params: dict) -> dict:
    """App 逻辑入口：params 为调用参数，返回 dict 给前端展示。"""
    return {"ok": True, "message": "你好，来自 core.run", "params": params}


if __name__ == "__main__":
    import json
    print(json.dumps(run({}), ensure_ascii=False))

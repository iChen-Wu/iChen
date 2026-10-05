# vision_adapter.py
# =============================================================================
# Vision 适配层：调用 GYun.vision 进行图片识别，解析歌曲列表
# =============================================================================

import json
import logging
import os
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def recognize_songs_from_images(
    image_paths: List[str],
    verbose: bool = False
) -> List[List[Dict[str, str]]]:
    """
    从图片中识别歌曲列表，按图片分组返回。

    入参：
        image_paths: List[str] - 图片路径列表
        verbose: bool - 是否打印调试信息

    出参：
        List[List[Dict[str, str]]] - 每个图片对应一个子列表，子列表包含该图片识别的歌曲
    """
    if not image_paths:
        return []

    # ⭐ 图像识别能力已并入 GYun.LLM（GYun.vision 子包不存在，属历史死代码）。
    # 这里惰性导入并在缺失时记录错误、返回空结果，保证 song 包可被干净 import，
    # 识别功能的具体改造（改走 GYun.LLM.chat_with_image）留待后续。
    try:
        from GYun.vision.core import vision
    except (ImportError, ModuleNotFoundError):
        logger.error("GYun.vision 已不存在（图像能力并入 GYun.LLM），图片识别不可用")
        return [[] for _ in image_paths]

    grouped_results = []

    for img_path in image_paths:
        if not os.path.exists(img_path):
            logger.warning(f"文件不存在: {img_path}")
            grouped_results.append([])
            continue

        try:
            # ⭐ vision 函数返回 {"content": ...}
            result = vision(img_path, type="歌曲列表")

            if verbose:
                print(f"\n[DEBUG] vision 返回 ({img_path}): {json.dumps(result, ensure_ascii=False, indent=2)}")

            content = result.get("content", {})

            # 如果 content 是字符串，尝试解析 JSON
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    json_match = re.search(r'\{[\s\S]*"songs"[\s\S]*\}', content)
                    if json_match:
                        try:
                            content = json.loads(json_match.group())
                        except:
                            pass

            songs = []
            if isinstance(content, dict):
                # 尝试从常见键中提取歌曲列表
                for key in ["songs", "list", "items", "data", "result"]:
                    if key in content and isinstance(content[key], list):
                        songs = content[key]
                        break
                else:
                    # 如果直接是单首歌
                    if "name" in content and "singer" in content:
                        songs = [content]
            elif isinstance(content, list):
                songs = content

            # 过滤无效歌曲（没有歌名和歌手）
            valid_songs = [s for s in songs if s.get("name", "").strip() and s.get("singer", "").strip()]
            grouped_results.append(valid_songs)

        except Exception as e:
            logger.error(f"识别异常 {img_path}: {e}", exc_info=True)
            grouped_results.append([])

    return grouped_results
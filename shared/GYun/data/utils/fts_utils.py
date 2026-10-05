"""FTS中文分词工具 - 支持可选单字索引"""

import os
import re
import jieba

# 默认不启用单字索引（避免索引膨胀），可通过环境变量开启
ENABLE_SINGLE_CHAR = os.environ.get('FTS_SINGLE_CHAR', '0') == '1'


def _extract_chinese_chars(text: str) -> list:
    """提取所有中文字符（含单字）"""
    return re.findall(r'[\u4e00-\u9fff]', text)


def segment(text: str) -> str:
    """分词：词语 + 可选单字"""
    if not text:
        return ""
    # jieba 词语级分词
    words = list(jieba.cut(text))
    # 如果启用了单字索引，追加单字
    if ENABLE_SINGLE_CHAR:
        chars = _extract_chinese_chars(text)
        all_tokens = words + chars
    else:
        all_tokens = words
    return " ".join(all_tokens)

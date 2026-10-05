#!/usr/bin/env python3
"""
GYun.data 自动改进脚本
运行：python -m GYun.data.changer

功能：
1. 修复 get_referenced_entities JSON 查询错误
2. 修复 resource_path 存储相对路径
3. 优化 FTS 单字索引（可选，默认关闭）
4. 修复 admin.py 菜单顺序
5. 移除 pydantic 依赖检查
6. 增加 logging 日志
7. 清理未使用的导入
"""

import os
import re
import sys
import shutil
from pathlib import Path

# 当前脚本所在目录
BASE_DIR = Path(__file__).resolve().parent

# ========== 颜色输出 ==========
def log(msg: str, level: str = "INFO"):
    colors = {
        "INFO": "\033[92m",
        "WARN": "\033[93m",
        "ERROR": "\033[91m",
        "RESET": "\033[0m",
    }
    print(f"{colors.get(level, colors['RESET'])}[{level}]{colors['RESET']} {msg}")


# ========== 备份工具 ==========
def backup_file(file_path: Path) -> Path:
    """备份文件"""
    if not file_path.exists():
        return None
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    shutil.copy2(file_path, backup_path)
    log(f"备份: {file_path.name} → {backup_path.name}", "INFO")
    return backup_path


def safe_write(file_path: Path, content: str):
    """安全写入文件"""
    backup_file(file_path)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"✅ 已更新: {file_path.name}", "INFO")


# ========== 修复1: query_service.py 中的 get_referenced_entities ==========
def fix_query_service():
    """修复 get_referenced_entities 查询逻辑"""
    file_path = BASE_DIR / "service" / "query_service.py"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经修复
    if "json_each" in content:
        log("query_service.py 已修复，跳过", "INFO")
        return True

    # 替换 get_referenced_entities 方法
    old_method = r'''@staticmethod
    def get_referenced_entities\(entity_id: str\) -> List\[dict\]:
        query = \(Entity
                 .select\(\)
                 .where\(fn\.json_extract\(Entity\.related_ids, '\$'\)\.contains\(entity_id\)\)\)
        return \[QueryService\._to_dict\(e\) for e in query\]'''

    new_method = '''@staticmethod
    def get_referenced_entities(entity_id: str) -> List[dict]:
        """查询所有关联了该实体的实体（反向关联）"""
        # 使用 SQL 的 json_each 遍历 JSON 数组
        from GYun.data.storage.database import db
        raw_sql = """
            SELECT e.* FROM gyun_entities e
            WHERE EXISTS (
                SELECT 1 FROM json_each(e.related_ids)
                WHERE value = ?
            ) AND e.is_deleted = 0
        """
        cursor = db.execute_sql(raw_sql, (entity_id,))
        # 将查询结果转换为 Entity 对象
        columns = [col[0] for col in cursor.description]
        entities = []
        for row in cursor.fetchall():
            entity_dict = dict(zip(columns, row))
            # 将 extra 和 related_ids 从 JSON 字符串解析为 Python 对象
            if 'extra' in entity_dict and isinstance(entity_dict['extra'], str):
                import json
                entity_dict['extra'] = json.loads(entity_dict['extra'])
            if 'related_ids' in entity_dict and isinstance(entity_dict['related_ids'], str):
                import json
                entity_dict['related_ids'] = json.loads(entity_dict['related_ids'])
            # 创建一个临时对象
            from GYun.data.models.entities import Entity
            entity = Entity(**entity_dict)
            entities.append(entity)
        return [QueryService._to_dict(e) for e in entities]'''

    # 替换
    content = re.sub(old_method, new_method, content, flags=re.DOTALL)

    # 同时修复 contains 查询改为 LIKE（在其他地方也有）
    content = content.replace(
        ".where(fn.json_extract(Entity.related_ids, '$').contains(entity_id))",
        ".where(Entity.related_ids.contains(f'\"{entity_id}\"'))"
    )

    safe_write(file_path, content)
    return True


# ========== 修复2: resource_storage.py 存储相对路径 ==========
def fix_resource_storage():
    """修复附件存储返回相对路径"""
    file_path = BASE_DIR / "storage" / "resource_storage.py"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已修复
    if "os.path.relpath" in content:
        log("resource_storage.py 已修复，跳过", "INFO")
        return True

    # 修改 upload 方法
    old_code = '''        dest_path = os.path.join(dest_dir, new_name)
        try:
            shutil.copy2(file_path, dest_path)
        except OSError as e:
            raise FileIOError(f"复制附件失败: {e}", original=e)
        return dest_path'''

    new_code = '''        dest_path = os.path.join(dest_dir, new_name)
        try:
            shutil.copy2(file_path, dest_path)
        except OSError as e:
            raise FileIOError(f"复制附件失败: {e}", original=e)
        # 存储相对路径（相对于 GYUN_RESOURCES_DIR）
        from GYun.core.constants import GYUN_RESOURCES_DIR
        relative_path = os.path.relpath(dest_path, GYUN_RESOURCES_DIR)
        return relative_path'''

    content = content.replace(old_code, new_code)

    # 修改 get_path 方法
    old_get = '''    @staticmethod
    def get_path(entity_id: str, relative_path: str) -> Optional[str]:
        full = os.path.join(GYUN_RESOURCES_DIR, relative_path)
        return full if os.path.exists(full) else None'''

    new_get = '''    @staticmethod
    def get_path(entity_id: str, relative_path: str) -> Optional[str]:
        """根据相对路径获取绝对路径"""
        if not relative_path:
            return None
        full = os.path.join(GYUN_RESOURCES_DIR, relative_path)
        return full if os.path.exists(full) else None'''

    content = content.replace(old_get, new_get)

    safe_write(file_path, content)
    return True


# ========== 修复3: fts_utils.py 单字索引改为可选 ==========
def fix_fts_utils():
    """FTS 单字索引改为可选（默认关闭）"""
    file_path = BASE_DIR / "utils" / "fts_utils.py"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已修复
    if "ENABLE_SINGLE_CHAR" in content:
        log("fts_utils.py 已修复，跳过", "INFO")
        return True

    # 重写整个文件
    new_content = '''"""FTS中文分词工具 - 支持可选单字索引"""\n
import os
import re
import jieba

# 默认不启用单字索引（避免索引膨胀），可通过环境变量开启
ENABLE_SINGLE_CHAR = os.environ.get('FTS_SINGLE_CHAR', '0') == '1'


def _extract_chinese_chars(text: str) -> list:
    """提取所有中文字符（含单字）"""
    return re.findall(r'[\\u4e00-\\u9fff]', text)


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
    return " ".join(all_tokens)\n'''

    safe_write(file_path, new_content)
    return True


# ========== 修复4: admin.py 菜单顺序 ==========
def fix_admin_menu():
    """修复 admin.py 菜单分支顺序"""
    file_path = BASE_DIR / "admin.py"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已修复
    if "elif choice == '10':" in content and "elif choice == '11':" in content and "elif choice == '12':" in content:
        # 检查顺序是否正确：10, 11, 12 依次排列
        order_check = content.find("elif choice == '10':")
        order_check2 = content.find("elif choice == '11':")
        order_check3 = content.find("elif choice == '12':")
        if order_check < order_check2 < order_check3:
            log("admin.py 菜单顺序已正确", "INFO")
            return True

    # 找到菜单处理部分，重新排列分支
    # 定义正确的顺序
    branch_pattern = r"(elif choice == '(\d+)':\s*\n\s*(.*?)\s*\n)(?=elif choice|else|$)"
    branches = re.findall(branch_pattern, content, re.DOTALL)

    # 按数字排序
    sorted_branches = sorted(branches, key=lambda x: int(x[1]))

    # 重新组装
    new_content = content
    # 简单方法：替换整个 elif 块
    # 找到第一个 elif choice 到最后一个 elif 或 else 结束
    start = content.find("elif choice == '")
    if start == -1:
        log("未找到菜单分支", "WARN")
        return False

    # 找到 else 或 0 分支作为结束
    end = content.find("        else:", start)
    if end == -1:
        end = content.find("        elif choice == '0':", start)

    # 构建新的分支块
    new_branches = []
    for branch in sorted_branches:
        if branch[1] == '0':
            continue  # 0 分支特殊处理
        new_branches.append(f"        elif choice == '{branch[1]}':\n{branch[2].strip()}\n")

    # 保留 0 分支和 else
    zero_branch = ""
    else_branch = ""
    zero_match = re.search(r"elif choice == '0':\s*\n\s*(.*?)\s*\n", content, re.DOTALL)
    if zero_match:
        zero_branch = f"        elif choice == '0':\n            {zero_match.group(1).strip()}\n"
    else_match = re.search(r"else:\s*\n\s*(.*?)\s*\n", content, re.DOTALL)
    if else_match:
        else_branch = f"        else:\n            {else_match.group(1).strip()}\n"

    # 只替换分支部分，保留前后
    before = content[:start]
    after = content[end:]

    new_content = before + "".join(new_branches) + zero_branch + else_branch + after

    safe_write(file_path, new_content)
    return True


# ========== 修复5: 移除 pydantic 依赖 ==========
def fix_pydantic():
    """移除 README.md 中未使用的 pydantic 依赖"""
    file_path = BASE_DIR / "README.md"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 替换依赖列表
    if "pydantic" in content:
        content = content.replace("pip install peewee pydantic jieba", "pip install peewee jieba")
        content = content.replace("peewee pydantic jieba", "peewee jieba")
        log("已移除 pydantic 依赖", "INFO")
        safe_write(file_path, content)
        return True
    else:
        log("README.md 中未发现 pydantic 依赖", "INFO")
        return True


# ========== 修复6: 增加 logging 日志 ==========
def add_logging():
    """为关键模块增加 logging"""
    # 在 client.py 增加日志初始化
    file_path = BASE_DIR / "client.py"
    if not file_path.exists():
        log(f"文件不存在: {file_path}", "WARN")
        return False

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已有日志
    if "import logging" in content:
        log("client.py 已有日志，跳过", "INFO")
        return True

    # 在顶部导入后增加
    lines = content.split("\n")
    new_lines = []
    inserted = False
    for line in lines:
        new_lines.append(line)
        if line.startswith("from GYun.data.service.hook_service") and not inserted:
            new_lines.append("import logging")
            new_lines.append("")
            inserted = True

    new_content = "\n".join(new_lines)

    # 在 __init__ 方法中增加 logger
    init_pattern = r'(def __init__\(self, enable_history: bool = False\):\s*\n\s*)(self\._hooks = HookManager\(\))'
    replacement = r'\1self._logger = logging.getLogger("gyun.client")\n        \2'
    new_content = re.sub(init_pattern, replacement, new_content)

    safe_write(file_path, new_content)
    return True


# ========== 修复7: 清理未使用的导入 ==========
def clean_imports():
    """清理未使用的导入"""
    files_to_clean = [
        BASE_DIR / "storage" / "entity_storage.py",
        BASE_DIR / "storage" / "fts_storage.py",
        BASE_DIR / "service" / "entity_service.py",
    ]

    for file_path in files_to_clean:
        if not file_path.exists():
            continue

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        original = content

        # 移除未使用的 List, Dict, Any, Optional
        patterns = [
            (r"from typing import List, Dict, Any, Optional\n", ""),
            (r"from typing import List, Dict, Any\n", ""),
            (r"from typing import List, Dict, Optional\n", ""),
            (r"from typing import List, Optional\n", ""),
            (r"from typing import Dict, Any\n", ""),
        ]

        for pattern, replacement in patterns:
            if pattern in content:
                # 检查是否真的没用到
                types = re.findall(r'\b(List|Dict|Any|Optional)\b', content)
                # 简单判断：如果只出现一次（在导入中），则删除
                if len(types) <= 2:
                    content = content.replace(pattern, replacement)

        if content != original:
            safe_write(file_path, content)
            log(f"清理导入: {file_path.name}", "INFO")


# ========== 主函数 ==========
def main():
    print("=" * 60)
    print("  GYun.data 自动改进脚本")
    print("=" * 60)
    print()

    log(f"工作目录: {BASE_DIR}", "INFO")

    fixes = [
        ("修复 get_referenced_entities", fix_query_service),
        ("修复 resource_path 存储相对路径", fix_resource_storage),
        ("优化 FTS 单字索引（默认关闭）", fix_fts_utils),
        ("修复 admin.py 菜单顺序", fix_admin_menu),
        ("移除 pydantic 依赖", fix_pydantic),
        ("增加 logging 日志", add_logging),
        ("清理未使用的导入", clean_imports),
    ]

    success_count = 0
    for name, func in fixes:
        print()
        log(f"▶ 执行: {name}", "INFO")
        try:
            if func():
                success_count += 1
            else:
                log(f"   {name} 跳过或失败", "WARN")
        except Exception as e:
            log(f"   ❌ {name} 失败: {e}", "ERROR")

    print()
    print("=" * 60)
    log(f"✅ 完成！成功 {success_count}/{len(fixes)} 项改进", "INFO")
    print()
    print("备份文件以 .bak 后缀保存")
    print("请检查修改后再运行测试")


if __name__ == "__main__":
    main()
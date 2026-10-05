"""附件存储层"""
import os
import hashlib
import shutil
from typing import Optional
from GYun.core.constants import GYUN_RESOURCES_DIR
from GYun.data.utils.exceptions import FileIOError, ParameterError

# V3.0 应用隔离：source 作为目录名的第一层。旧数据无 source，附件落在旧路径
# resources/{entity_id[:2]}/{entity_id}/；新数据按应用隔离，落在
# resources/{source}/{entity_id[:2]}/{entity_id}/。


def validate_source(source) -> Optional[str]:
    """
    校验并规范化应用标识。
    - None 表示全局/旧数据（不隔离）
    - 禁止空串、首尾空白、路径分隔符、'.' / '..'、Windows 非法字符与保留名，
      防止目录逃逸与文件系统错误
    """
    import re
    if source is None:
        return None
    if not isinstance(source, str):
        raise ParameterError(f"source 必须是字符串，当前为 {type(source).__name__}")
    s = source.strip()
    if not s:
        raise ParameterError("source 不能为空")
    if s != source:
        raise ParameterError(f"source 首尾不能有空白: {source!r}")
    if '/' in s or '\\' in s or s in ('.', '..'):
        raise ParameterError(f"source 含非法字符，不能作为目录名: {source!r}")
    # 拒绝首尾点：Windows 会将 'appA.' 归一为 'appA'，'.hidden' 是隐藏目录，均不应作为应用标识
    if s.startswith('.') or s.endswith('.'):
        raise ParameterError(f"source 不能以点开头或结尾: {source!r}")
    if any(ch in s for ch in '<>:"|?*') or any(ord(ch) < 32 for ch in s):
        raise ParameterError(f"source 含文件系统非法字符: {source!r}")
    # Windows 保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9，含带扩展名形式）
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', s, re.IGNORECASE):
        raise ParameterError(f"source 为 Windows 保留名称: {source!r}")
    return s


class ResourceStorage:
    @staticmethod
    def upload(entity_id: str, file_path: str, source: Optional[str] = None) -> str:
        """上传附件到应用隔离目录（source=None 时保持旧路径，兼容旧数据/全局模式）"""
        source = validate_source(source)
        if source:
            dest_dir = os.path.join(GYUN_RESOURCES_DIR, source, entity_id[:2], entity_id)
        else:
            dest_dir = os.path.join(GYUN_RESOURCES_DIR, entity_id[:2], entity_id)
        os.makedirs(dest_dir, exist_ok=True)
        basename = os.path.basename(file_path)
        # 计算MD5防重名
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            while chunk := f.read(8192):
                md5.update(chunk)
        suffix = md5.hexdigest()[:8]
        name, ext = os.path.splitext(basename)
        new_name = f"{name}_{suffix}{ext}"
        dest_path = os.path.join(dest_dir, new_name)
        try:
            shutil.copy2(file_path, dest_path)
        except OSError as e:
            raise FileIOError(f"复制附件失败: {e}", original=e)
        relative_path = os.path.relpath(dest_path, GYUN_RESOURCES_DIR)
        return relative_path

    @staticmethod
    def get_path(entity_id: str, relative_path: str, source: Optional[str] = None) -> Optional[str]:
        """
        根据相对路径获取绝对路径（V3.0 双路径回退）。
        :param entity_id: 实体ID（保留用于接口一致性）
        :param relative_path: 相对于 GYUN_RESOURCES_DIR 的路径（新格式含 source 前缀，旧格式不含）
        :param source: 应用标识；提供时优先尝试新路径 resources/{source}/{relative_path}，
                       文件不存在时回退旧路径 resources/{relative_path}，保证旧数据附件无感知兼容。
        :return: 绝对路径，若文件不存在则返回 None
        """
        _ = entity_id  # 消除未使用参数的代码提示

        # 🔒 防御：source 可能来自数据库旧数据/脏数据，非法时放弃新路径尝试（仅按旧路径解析）
        if source:
            try:
                source = validate_source(source)
            except ParameterError:
                source = None

        if not relative_path:
            return None
        rel = os.path.normpath(relative_path)
        # 🔒 防御：拒绝绝对路径、越界路径与根目录指向，防止数据库内脏数据导致目录逃逸
        # Windows 盘符/ADS 前缀（如 'C:foo'）不满足 isabs 但会被 join 替换盘符，一并拒绝
        if os.path.isabs(rel) or rel in ('.', '..') or rel.startswith('..' + os.sep) or ':' in rel:
            return None
        # 新路径优先：relative_path 是旧格式（不带 source 前缀）且提供了 source
        if source and not rel.startswith(source + os.sep) and not rel == source:
            new_full = os.path.join(GYUN_RESOURCES_DIR, os.path.normpath(os.path.join(source, rel)))
            if os.path.exists(new_full):
                return new_full
        # 回退：直接按 relative_path 解析（旧路径，或新格式路径本身已含 source 前缀）
        full = os.path.join(GYUN_RESOURCES_DIR, rel)
        return full if os.path.exists(full) else None

    @staticmethod
    def delete(entity_id: str, source: Optional[str] = None):
        """删除实体附件目录：同时清理新路径与旧路径，兼容旧数据"""
        source = validate_source(source)
        dirs = []
        if source:
            dirs.append(os.path.join(GYUN_RESOURCES_DIR, source, entity_id[:2], entity_id))
        # 旧路径始终尝试删除（旧数据附件 / 全局模式上传的附件）
        dirs.append(os.path.join(GYUN_RESOURCES_DIR, entity_id[:2], entity_id))
        for dir_path in dirs:
            if os.path.exists(dir_path):
                shutil.rmtree(dir_path)

    @staticmethod
    def delete_application(source: str):
        """一键删除应用：物理清除 resources/{source}/ 整个附件目录"""
        source = validate_source(source)
        if source is None:
            raise ParameterError("delete_application 需要明确的应用标识，不支持全局模式")
        app_dir = os.path.join(GYUN_RESOURCES_DIR, source)
        if os.path.exists(app_dir):
            shutil.rmtree(app_dir)

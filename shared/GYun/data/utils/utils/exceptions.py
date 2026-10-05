"""GYun Data 自定义异常体系"""

class GyunBaseError(Exception):
    """所有自定义异常的基类"""
    def __init__(self, message="", original=None):
        super().__init__(message)
        self.original = original

class ParameterError(GyunBaseError):
    """参数错误"""

class EntityNotFoundError(GyunBaseError):
    """实体不存在"""

class DatabaseError(GyunBaseError):
    """数据库操作失败"""

class FileIOError(GyunBaseError):
    """文件读写错误"""

class IntegrityError(GyunBaseError):
    """数据完整性错误"""

class HookReentryError(GyunBaseError):
    """钩子重入错误"""

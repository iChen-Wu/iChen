"""
models.py - 数据中心常量定义（独立，不依赖业务模块）
"""

# 操作类型常量
OP_LIST = "list"
OP_VIEW = "view"
OP_CREATE = "create"
OP_EDIT = "edit"
OP_DELETE = "delete"
OP_SEARCH = "search"
OP_BATCH = "batch"

# 默认分页
DEFAULT_PAGE_SIZE = 20
DEFAULT_ORDER_BY = "created_at desc"

# 显示的通用字段
DISPLAY_FIELDS = ["entity_id", "type", "title", "tags", "created_at", "updated_at"]
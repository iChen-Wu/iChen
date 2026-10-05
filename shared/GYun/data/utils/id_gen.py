"""全局唯一ID生成器（32位十六进制）"""
import uuid

def generate_entity_id() -> str:
    return uuid.uuid4().hex

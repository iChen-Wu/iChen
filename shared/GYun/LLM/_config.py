import os
import warnings
from pathlib import Path
from dotenv import load_dotenv
from GYun.LLM.exceptions import ModelNotFoundError

def _find_env_file() -> Path:
    custom_env = os.getenv("LLM_UNION_ENV_FILE")
    if custom_env and Path(custom_env).exists(): 
        return Path(custom_env)
        
    current = Path(__file__).resolve()
    # 从当前文件所在目录一直往上找
    for parent in [current.parent] + list(current.parents):
        # 优先查找 data/config/.env（V3.0.0 起配置归位于 data/）
        candidate = parent / "data" / "config" / ".env"
        if candidate.exists():
            return candidate

        # 兼容旧位置 config/.env
        candidate = parent / "config" / ".env"
        if candidate.exists():
            return candidate
            
        # 其次查找直接放在目录下的 .env
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
            
    # 最后检查当前工作目录
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env
        
    return None

ENV_PATH = _find_env_file()
if ENV_PATH: load_dotenv(dotenv_path=ENV_PATH, override=True)

class Config:
    VOLC_ARK_API_KEY: str = os.getenv("VOLC_ARK_API_KEY", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

    DEFAULT_MODEL: str = os.getenv("LLM_UNION_DEFAULT_MODEL", "deepseek-chat")
    DEFAULT_TEMPERATURE: float = float(os.getenv("LLM_UNION_TEMPERATURE", "0.7"))
    DEFAULT_TIMEOUT: int = int(os.getenv("LLM_UNION_TIMEOUT", "60"))
    DEFAULT_MAX_TOKENS: int = int(os.getenv("LLM_UNION_MAX_TOKENS", "4096"))
    # 硅基流动
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "")

    VOLC_APP_ID: str = os.getenv("VOLC_APP_ID", "")
    VOLC_TOKEN: str = os.getenv("VOLC_TOKEN", "")
    VOLC_CLUSTER: str = os.getenv("VOLC_CLUSTER", "")
    VOLC_VOICE_API_KEY: str = os.getenv("VOLC_VOICE_API_KEY", "")


    # 静态注册表：无前缀别名 -> (适配器模块, 类名, 真实模型ID)
    # 注：glm 已废弃智谱官方接口，为兼容保留该别名并路由到硅基流动的 GLM 模型
    MODEL_REGISTRY = {
        "deepseek-chat": ("adapters.deepseek_adapter", "DeepseekAdapter", "deepseek-chat"),
        "deepseek-v3": ("adapters.deepseek_adapter", "DeepseekAdapter", "deepseek-chat"),
        "deepseek-reasoner": ("adapters.deepseek_adapter", "DeepseekAdapter", "deepseek-reasoner"),
        "glm": ("adapters.siliconflow_adapter", "SiliconFlowAdapter", "THUDM/GLM-4-9B-0414"),

    }

    # 动态平台路由表 (前缀 -> (模块路径, 类名))
    # 短前缀: sf=硅基流动, vc=火山; 旧长前缀 siliconflow/volc 保留兼容
    DYNAMIC_PLATFORMS = {
        "sf": ("adapters.siliconflow_adapter", "SiliconFlowAdapter"),
        "vc": ("adapters.volc_adapter", "VolcAdapter"),
        "siliconflow": ("adapters.siliconflow_adapter", "SiliconFlowAdapter"),
        "volc": ("adapters.volc_adapter", "VolcAdapter"),
        "deepseek": ("adapters.deepseek_adapter", "DeepseekAdapter"),
        "ds": ("adapters.deepseek_adapter", "DeepseekAdapter"),
    }

    @classmethod
    def get_model_info(cls, user_model: str):
        # 1. 优先匹配静态注册表 (无前缀的直接别名)
        if user_model in cls.MODEL_REGISTRY:
            module_path, class_name, model_spec = cls.MODEL_REGISTRY[user_model]
            if isinstance(model_spec, str) and model_spec.isupper() and hasattr(cls, model_spec):
                real_model_id = getattr(cls, model_spec)
                if not real_model_id:
                    raise ValueError(f"模型 {user_model} 的环境变量 {model_spec} 未配置")
                return module_path, class_name, real_model_id
            return module_path, class_name, model_spec

        # 2. 动态前缀路由 (格式: "平台名/模型ID")
        if "/" in user_model:
            prefix, real_model_id = user_model.split("/", 1)
            prefix = prefix.lower()
            if prefix in cls.DYNAMIC_PLATFORMS:
                module_path, class_name = cls.DYNAMIC_PLATFORMS[prefix]

                # 火山短名补全: VC/doubao -> 环境变量 VOLC_DOUBAO_MODEL_ID
                if prefix in ("volc", "vc") and not real_model_id.isupper():
                    env_name = f"VOLC_{real_model_id.upper()}_MODEL_ID"
                    env_val = os.getenv(env_name, "").strip()
                    if env_val:
                        return module_path, class_name, env_val

                # 全大写: 视为环境变量名, 自动从环境变量读取真实的 ep-xxx
                if real_model_id.isupper():
                    env_val = os.getenv(real_model_id, "").strip()
                    if env_val:
                        return module_path, class_name, env_val
                    raise ModelNotFoundError(f"动态路由解析失败：环境变量 {real_model_id} 未配置或为空")

                # 否则直接当作模型 ID 使用
                return module_path, class_name, real_model_id

        raise ModelNotFoundError(f"未知模型或无效格式: {user_model}")

_config = None
def get_config():
    global _config
    if _config is None: _config = Config()
    return _config
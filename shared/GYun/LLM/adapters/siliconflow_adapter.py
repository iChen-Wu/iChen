from GYun.LLM.adapters._openai_compatible import OpenAICompatibleAdapter
from GYun.LLM._config import get_config

class SiliconFlowAdapter(OpenAICompatibleAdapter):
    def __init__(self, model_name: str):
        config = get_config()
        super().__init__(
            model_name=model_name,
            base_url="https://api.siliconflow.cn/v1",
            api_key=config.SILICONFLOW_API_KEY
        )
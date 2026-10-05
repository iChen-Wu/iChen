from GYun.LLM.adapters._openai_compatible import OpenAICompatibleAdapter
from GYun.LLM._config import get_config

class VolcAdapter(OpenAICompatibleAdapter):
    def __init__(self, model_name: str):
        config = get_config()
        super().__init__(
            model_name=model_name,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key=config.VOLC_ARK_API_KEY
        )
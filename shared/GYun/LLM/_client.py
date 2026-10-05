import asyncio
import json
from typing import List, Dict, Union, Iterator, AsyncIterator, Optional, Callable, Any
from GYun.LLM._config import Config, get_config
from GYun.LLM.exceptions import APIRequestError
from GYun.LLM.factory import ModelFactory
from GYun.LLM.base import AudioClassificationResponse, ChatResponse, EmbeddingResponse, RerankResponse, StreamChunk, ToolFunction

class LLMClient:
    def __init__(self, config):
        self.config = config

    def _get_adapter(self, model_name: str):
        return ModelFactory.get_adapter(model_name or self.config.DEFAULT_MODEL)

    @staticmethod
    def _resolve_thinking_model(model, thinking):
        """思考模式 -> 模型解析。
        - thinking=None：不干预，按所选模型默认行为
        - DeepSeek 系列：官方 API 无思考开关参数，通过切换模型实现
          (thinking=True → deepseek-reasoner；thinking=False → deepseek-chat)
        - 其他平台：模型不变，由调用方透传平台原生 thinking 参数（如火山方舟）
        """
        if thinking is None:
            return model
        if model is None:
            model = get_config().DEFAULT_MODEL
        base = model.split("/")[-1]
        if base.lower() in ("deepseek-chat", "deepseek-v3", "deepseek-reasoner"):
            return "deepseek-reasoner" if thinking else "deepseek-chat"
        return model

    @staticmethod
    def _apply_thinking_kwargs(model, thinking, kwargs):
        """对支持思考开关请求字段的平台透传原生参数。
        - 火山方舟：thinking={"type": "enabled"/"disabled"}
        - 硅基流动：enable_thinking=True/False（如 deepseek-ai/DeepSeek-R1 等推理模型）
        - DeepSeek 官方：无开关参数，由 _resolve_thinking_model 切换模型
        """
        if thinking is None or model is None:
            return kwargs
        prefix = model.split("/")[0].lower()
        if prefix in ("volc", "vc"):
            kwargs["thinking"] = {"type": "enabled" if thinking else "disabled"}
        elif prefix in ("siliconflow", "sf"):
            kwargs["enable_thinking"] = bool(thinking)
        return kwargs

    def chat(self, messages, model=None, stream=False, thinking=None, **kwargs):
        if isinstance(messages, str): messages = [{"role": "user", "content": messages}]
        model = self._resolve_thinking_model(model, thinking)
        self._apply_thinking_kwargs(model, thinking, kwargs)
        return self._get_adapter(model).chat(messages, stream=stream, **kwargs)

    def stream_chat(self, messages, model=None, thinking=None, **kwargs):
        return self.chat(messages, model=model, stream=True, thinking=thinking, **kwargs)

    def chat_with_tools(self, messages, tools, model=None, **kwargs):
        if isinstance(messages, str): messages = [{"role": "user", "content": messages}]
        return self._get_adapter(model).chat_with_tools(messages, tools, **kwargs)

    def chat_with_image(self, prompt, image, model=None, **kwargs):
        return self._get_adapter(model).chat_with_image(prompt, image, **kwargs)

    # --- 异步 API ---
    async def async_chat(self, messages, model=None, stream=False, thinking=None, **kwargs):
        if isinstance(messages, str): messages = [{"role": "user", "content": messages}]
        model = self._resolve_thinking_model(model, thinking)
        self._apply_thinking_kwargs(model, thinking, kwargs)
        return await self._get_adapter(model).async_chat(messages, stream=stream, **kwargs)

    async def async_stream_chat(self, messages, model=None, thinking=None, **kwargs):
        """异步流式对话"""
        if isinstance(messages, str): messages = [{"role": "user", "content": messages}]
        model = self._resolve_thinking_model(model, thinking)
        self._apply_thinking_kwargs(model, thinking, kwargs)
        # 调用 async_chat 并开启 stream=True
        return await self._get_adapter(model).async_chat(messages, stream=True, **kwargs)

    async def async_chat_with_tools(self, messages, tools, model=None, **kwargs) -> ChatResponse:
        if isinstance(messages, str): messages = [{"role": "user", "content": messages}]
        return await self._get_adapter(model).async_chat_with_tools(messages, tools, **kwargs)

    # 修复：Agent 循环中保护 arguments 序列化
    def run_agent_loop(self, prompt: str, tools: List[ToolFunction], tool_executor: Callable, model=None, max_steps=5, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        for _ in range(max_steps):
            resp = self.chat_with_tools(messages, tools, model=model, **kwargs)
            assistant_msg = {"role": "assistant", "content": resp.content or ""}
            if resp.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments)}}
                    for tc in resp.tool_calls
                ]
            messages.append(assistant_msg)

            if not resp.tool_calls: return resp.content

            for tc in resp.tool_calls:
                result = tool_executor(tc.name, tc.arguments)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
        return "Agent 达到最大执行步数，未返回最终结果。"

    # 修复：异步并发工具加入 return_exceptions 降级处理
    async def async_run_agent_loop(self, prompt: str, tools: List[ToolFunction], async_tool_executor: Callable, model=None, max_steps=5, **kwargs) -> str:
        messages = [{"role": "user", "content": prompt}]
        for _ in range(max_steps):
            resp = await self.async_chat_with_tools(messages, tools, model=model, **kwargs)
            assistant_msg = {"role": "assistant", "content": resp.content or ""}
            if resp.tool_calls:
                assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else str(tc.arguments)}}
                    for tc in resp.tool_calls
                ]
            messages.append(assistant_msg)

            if not resp.tool_calls: return resp.content

            tasks = [async_tool_executor(tc.name, tc.arguments) for tc in resp.tool_calls]
            # 如果某个工具报错，不会导致整个 Agent 崩溃
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for tc, res in zip(resp.tool_calls, results):
                content = str(res) if not isinstance(res, Exception) else f"Tool execution error: {res}"
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
        return "Agent 达到最大执行步数，未返回最终结果。"

    def transcribe_audio(self, audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall", platform: str = "siliconflow", language: str = None) -> str:
        """语音识别"""
        from GYun.LLM.adapters.audio_adapter import AudioAdapter
        client = AudioAdapter(platform=platform)
        try:
            return client.transcribe(audio_path, model=model, language=language)
        finally:
            client.close()

    def synthesize_audio(self, text: str, voice: str = None, **kwargs) -> bytes:
        """文本转语音 (TTS)"""
        from GYun.LLM.adapters.tts_adapter import VolcTTSAdapter
        client = VolcTTSAdapter()
        try:
            return client.synthesize(text, voice, **kwargs)
        finally:
            client.close()

    async def async_transcribe_audio_stream(self, audio_path: str) -> AsyncIterator[str]:
        """火山引擎流式语音识别 (实时返回识别结果)"""
        from GYun.LLM.adapters.volc_streaming_asr import VolcStreamingAsrClient
        async with VolcStreamingAsrClient() as client:
            try:
                async for response in client.execute(audio_path):
                    if response.payload_msg:
                        # 提取 text 字段，并过滤掉空的心跳包
                        text = response.payload_msg.get("text", "")
                        if text:
                            yield text
            except Exception as e:
                raise APIRequestError(f"流式语音识别失败: {e}")

    def embed_texts(self, texts: List[str], model: str = None, **kwargs) -> 'EmbeddingResponse':
        """文本转向量"""
        return self._get_adapter(model).embed_texts(texts, **kwargs)

    async def async_embed_texts(self, texts: List[str], model: str = None, **kwargs) -> 'EmbeddingResponse':
        """异步文本转向量"""
        return await self._get_adapter(model).async_embed_texts(texts, **kwargs)

    def rerank_texts(self, query: str, documents: List[str], model: str = None, **kwargs) -> 'RerankResponse':
        return self._get_adapter(model).rerank_texts(query, documents, **kwargs)
    
    def classify_audio(self, audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall") -> 'AudioClassificationResponse':
        """音频分类 (情感识别/声学事件检测)"""
        from GYun.LLM.adapters.audio_adapter import AudioAdapter
        client = AudioAdapter()
        try:
            return client.classify_audio(audio_path, model)
        finally:
            client.close()
    
    

_global_client = None

def get_client() -> LLMClient:
    global _global_client
    if _global_client is None: _global_client = LLMClient(get_config())
    return _global_client

def reset_client():
    global _global_client
    ModelFactory.clear_cache()
    _global_client = None

def init_llm(**config_overrides):
    config = get_config()
    for k, v in config_overrides.items():
        setattr(config, k, v)
        # 类属性（如 MODEL_REGISTRY / DYNAMIC_PLATFORMS）必须写到类上，
        # 因为 get_model_info 通过 cls.xxx 读取类属性，仅设实例属性不生效
        if hasattr(Config, k):
            setattr(Config, k, v)
    reset_client()
    return get_client()

def chat(messages, model=None, stream=False, thinking=None, **kwargs): return get_client().chat(messages, model, stream, thinking, **kwargs)
def stream_chat(messages, model=None, thinking=None, **kwargs): yield from get_client().stream_chat(messages, model, thinking, **kwargs)
def chat_with_image(prompt, image, model=None, **kwargs): return get_client().chat_with_image(prompt, image, model, **kwargs)
def chat_with_tools(messages, tools, model=None, **kwargs): return get_client().chat_with_tools(messages, tools, model, **kwargs)
def run_agent_loop(prompt, tools, tool_executor, model=None, max_steps=5, **kwargs): return get_client().run_agent_loop(prompt, tools, tool_executor, model, max_steps, **kwargs)
def transcribe_audio(audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall", platform: str = "siliconflow", language: str = None) -> str:
    return get_client().transcribe_audio(audio_path, model, platform, language)
def synthesize_audio(text: str, voice: str = None, **kwargs) -> bytes:
    return get_client().synthesize_audio(text, voice, **kwargs)
def embed_texts(texts: List[str], model: str = None, **kwargs):
    return get_client().embed_texts(texts, model, **kwargs)
def rerank_texts(query: str, documents: List[str], model: str = None, **kwargs):
    return get_client().rerank_texts(query, documents, model, **kwargs)
def classify_audio(audio_path: str, model: str = "FunAudioLLM/SenseVoiceSmall"):
    return get_client().classify_audio(audio_path, model)

async def async_transcribe_audio_stream(audio_path: str) -> AsyncIterator[str]:
    async for chunk in get_client().async_transcribe_audio_stream(audio_path):
        yield chunk

async def async_chat(messages, model=None, stream=False, thinking=None, **kwargs): 
    return await get_client().async_chat(messages, model, stream, thinking, **kwargs)

async def async_stream_chat(messages, model=None, thinking=None, **kwargs): 
    return await get_client().async_stream_chat(messages, model, thinking, **kwargs)

async def async_chat_with_tools(messages, tools, model=None, **kwargs): 
    return await get_client().async_chat_with_tools(messages, tools, model, **kwargs)

async def async_run_agent_loop(prompt, tools, async_tool_executor, model=None, max_steps=5, **kwargs): 
    return await get_client().async_run_agent_loop(prompt, tools, async_tool_executor, model, max_steps, **kwargs)

async def async_embed_texts(texts: List[str], model: str = None, **kwargs):
    return await get_client().async_embed_texts(texts, model, **kwargs)
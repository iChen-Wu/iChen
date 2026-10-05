import json
import asyncio
import httpx
from typing import List, Dict, Union, Iterator, AsyncIterator, Optional
from GYun.LLM.base import BaseAdapter, ChatResponse, EmbeddingResponse, RerankResponse, RerankResult, StreamChunk, ToolCall, ToolFunction
from GYun.LLM.exceptions import APIRequestError, AuthenticationError, RateLimitError
from GYun.LLM._config import get_config
from GYun.LLM.utils import normalize_image_input

class OpenAICompatibleAdapter(BaseAdapter):
    def __init__(self, model_name: str, base_url: str, api_key: str):
        if not api_key:
            raise APIRequestError(f"模型 {model_name} 的 API Key 未配置，请在 .env 文件中设置。")
            
        self.model_name = model_name
        self.base_url = base_url
        self.api_key = api_key
        self.config = get_config()
        self._headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        
        self._sync_client = None
        self._async_client = None
        self._async_client_loop = None  # 新增：记录异步客户端所属的事件循环

    @property
    def sync_client(self):
        if self._sync_client is None:
            limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
            self._sync_client = httpx.Client(headers=self._headers, timeout=self.config.DEFAULT_TIMEOUT, limits=limits)
        return self._sync_client

    @property
    def async_client(self):
        try:
            # 获取当前正在运行的事件循环
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        # 如果客户端不存在，或者绑定的事件循环不是当前的（比如上一次的循环已关闭）
        if self._async_client is None or self._async_client_loop is not current_loop:
            if self._async_client is not None:
                # 旧循环已死，无法 await aclose()，直接置空交给 GC 回收
                self._async_client = None
                
            if current_loop is not None:
                limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
                self._async_client = httpx.AsyncClient(headers=self._headers, timeout=self.config.DEFAULT_TIMEOUT, limits=limits)
                self._async_client_loop = current_loop
                
        return self._async_client

    def close(self):
        """同步关闭"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        if self._async_client:
            # 尝试在同步环境中安全关闭异步客户端
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._async_client.aclose())
                else:
                    loop.run_until_complete(self._async_client.aclose())
            except Exception:
                pass
            self._async_client = None

    def _build_payload(self, messages, stream, **kwargs):
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "temperature": kwargs.get("temperature", self.config.DEFAULT_TEMPERATURE),
            "max_tokens": kwargs.get("max_tokens", self.config.DEFAULT_MAX_TOKENS),
        }
        
        # 新增：透传其他高级采样参数 (如果调用时传了才生效)
        if "top_p" in kwargs: payload["top_p"] = kwargs["top_p"]
        if "frequency_penalty" in kwargs: payload["frequency_penalty"] = kwargs["frequency_penalty"]
        if "presence_penalty" in kwargs: payload["presence_penalty"] = kwargs["presence_penalty"]
        if "stop" in kwargs: payload["stop"] = kwargs["stop"]
        if "seed" in kwargs: payload["seed"] = kwargs["seed"]
        # 思考模式开关（火山方舟 thinking.type；硅基流动 enable_thinking）
        if kwargs.get("thinking"):
            payload["thinking"] = kwargs["thinking"]
        if "enable_thinking" in kwargs:
            payload["enable_thinking"] = kwargs["enable_thinking"]
        
        if kwargs.get("tools"):
            payload["tools"] = [{"type": "function", "function": t.dict()} if isinstance(t, ToolFunction) else t for t in kwargs["tools"]]
            payload["tool_choice"] = kwargs.get("tool_choice", "auto")
        if kwargs.get("response_format"):
            payload["response_format"] = kwargs["response_format"]
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _parse_response(self, data: dict) -> ChatResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = []
            for tc in message["tool_calls"]:
                try: args = json.loads(tc["function"]["arguments"])
                except: args = {}
                tool_calls.append(ToolCall(id=tc.get("id", ""), name=tc["function"]["name"], arguments=args))
        
        # 修改：增加 reasoning_content 的提取
        return ChatResponse(
            content=message.get("content") or "",
            reasoning_content=message.get("reasoning_content") or "",
            tool_calls=tool_calls,
            usage=data.get("usage")
        )

    def _parse_stream_line(self, chunk: dict) -> Optional[StreamChunk]:
        if not chunk.get("choices"): 
            return StreamChunk(usage=chunk.get("usage")) if chunk.get("usage") else None
        delta = chunk["choices"][0].get("delta", {})
        tool_calls_delta = None
        if delta.get("tool_calls"):
            tool_calls_delta = []
            for tc in delta["tool_calls"]:
                args_str = tc.get("function", {}).get("arguments", "")
                tool_calls_delta.append(ToolCall(
                    index=tc.get("index", 0),  # 新增：提取 index
                    id=tc.get("id", ""),
                    name=tc.get("function", {}).get("name", ""),
                    arguments=args_str
                ))
        
        return StreamChunk(
            content=delta.get("content") or "",
            reasoning_content=delta.get("reasoning_content") or "",
            tool_calls_delta=tool_calls_delta,
            finish_reason=chunk["choices"][0].get("finish_reason"),
            usage=chunk.get("usage")
        )

    def _handle_error(self, resp: httpx.Response):
        if resp.status_code == 401: raise AuthenticationError(f"API Key 无效: {resp.text}")
        elif resp.status_code == 429: raise RateLimitError(f"请求限流: {resp.text}")
        else: raise APIRequestError(f"API 错误 {resp.status_code}: {resp.text}")

    def _should_retry(self, status_code: int) -> bool:
        return status_code in [429, 500, 502, 503, 504]

    # ---------- 同步接口 (带重试) ----------
    def chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> Union[ChatResponse, Iterator[StreamChunk]]:
        payload = self._build_payload(messages, stream, **kwargs)
        url = f"{self.base_url}/chat/completions"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if stream:
                    # 修复：使用 stream 上下文管理器发起真正的流式请求
                    req = self.sync_client.build_request("POST", url, json=payload)
                    resp = self.sync_client.send(req, stream=True)
                    if resp.status_code != 200:
                        resp.read() # 必须读取才能获取错误信息
                        if self._should_retry(resp.status_code) and attempt < max_retries - 1:
                            import time
                            time.sleep(1 * (attempt + 1))
                            continue
                        self._handle_error(resp)
                    return self._sync_stream_generator(resp)
                else:
                    resp = self.sync_client.post(url, json=payload)
                    if resp.status_code != 200:
                        if self._should_retry(resp.status_code) and attempt < max_retries - 1:
                            import time
                            time.sleep(1 * (attempt + 1))
                            continue
                        self._handle_error(resp)
                    return self._parse_response(resp.json())
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1 * (attempt + 1))
                    continue
                raise APIRequestError(f"网络请求失败: {e}")

    def _sync_stream_generator(self, resp: httpx.Response) -> Iterator[StreamChunk]:
        try:
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "): continue
                data_str = line[6:]
                if data_str == "[DONE]": break
                try:
                    chunk = json.loads(data_str)
                    parsed = self._parse_stream_line(chunk)
                    if parsed: yield parsed
                except json.JSONDecodeError:
                    continue
        finally:
            # 手动关闭响应，释放连接池资源
            resp.close()

    def chat_with_tools(self, messages, tools, **kwargs) -> ChatResponse:
        kwargs.pop("stream", None)  # 修复：stream 已由本方法固定为 False，剥离避免重复传参
        return self.chat(messages, stream=False, tools=tools, **kwargs)

    # ---------- 异步接口 (带重试机制) ----------
    async def async_chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> Union[ChatResponse, AsyncIterator[StreamChunk]]:
        payload = self._build_payload(messages, stream, **kwargs)
        url = f"{self.base_url}/chat/completions"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if stream:
                    # 修复：使用异步 stream 上下文管理器
                    req = self.async_client.build_request("POST", url, json=payload)
                    resp = await self.async_client.send(req, stream=True)
                    if resp.status_code != 200:
                        await resp.aread()
                        if self._should_retry(resp.status_code) and attempt < max_retries - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        self._handle_error(resp)
                    return self._async_stream_generator(resp)
                else:
                    resp = await self.async_client.post(url, json=payload)
                    if resp.status_code != 200:
                        if self._should_retry(resp.status_code) and attempt < max_retries - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        self._handle_error(resp)
                    return self._parse_response(resp.json())
            except httpx.RequestError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise APIRequestError(f"异步网络请求失败: {e}")

    async def _async_stream_generator(self, resp: httpx.Response) -> AsyncIterator[StreamChunk]:
        try:
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "): continue
                data_str = line[6:]
                if data_str == "[DONE]": break
                try:
                    chunk = json.loads(data_str)
                    parsed = self._parse_stream_line(chunk)
                    if parsed: yield parsed
                except json.JSONDecodeError:
                    continue
        finally:
            # 手动关闭异步响应，释放连接池资源
            await resp.aclose()

    async def async_chat_with_tools(self, messages, tools, **kwargs) -> ChatResponse:
        kwargs.pop("stream", None)  # 修复：stream 已由本方法固定为 False，剥离避免重复传参
        return await self.async_chat(messages, stream=False, tools=tools, **kwargs)

    def chat_with_image(self, prompt: str, image: Union[str, bytes], **kwargs) -> ChatResponse:
        image_url = normalize_image_input(image)
        messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": image_url}}]}]
        return self.chat(messages, stream=False, **kwargs)

    def embed_texts(self, texts: List[str], model: str = None, **kwargs) -> EmbeddingResponse:
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": model or self.model_name,  # 如果不传 model，就用适配器初始化时的真实模型名
            "input": texts,
            "encoding_format": "float"
        }
        try:
            resp = self.sync_client.post(url, json=payload)
            if resp.status_code != 200:
                self._handle_error(resp)
            data = resp.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]
            return EmbeddingResponse(embeddings=embeddings, usage=data.get("usage"))
        except httpx.RequestError as e:
            raise APIRequestError(f"Embedding 请求失败: {e}")

    async def async_embed_texts(self, texts: List[str], model: str = None, **kwargs) -> EmbeddingResponse:
        """异步文本转向量"""
        url = f"{self.base_url}/embeddings"
        payload = {
            "model": model or self.model_name,
            "input": texts,
            "encoding_format": "float"
        }
        try:
            resp = await self.async_client.post(url, json=payload)
            if resp.status_code != 200:
                self._handle_error(resp)
            data = resp.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]
            return EmbeddingResponse(embeddings=embeddings, usage=data.get("usage"))
        except httpx.RequestError as e:
            raise APIRequestError(f"异步 Embedding 请求失败: {e}")

    # ---------- 文本重排序 ----------
    def rerank_texts(self, query: str, documents: List[str], model: str = None, **kwargs) -> RerankResponse:
        """同步文本重排序"""
        url = f"{self.base_url}/rerank"
        payload = {
            "model": model or self.model_name,
            "query": query,
            "documents": documents,
            "top_n": kwargs.get("top_n", len(documents)),
            "return_documents": kwargs.get("return_documents", False)
        }
        try:
            resp = self.sync_client.post(url, json=payload)
            if resp.status_code != 200: self._handle_error(resp)
            data = resp.json()
            results = [RerankResult(**item) for item in data.get("results", [])]
            return RerankResponse(results=results, usage=data.get("usage"))
        except httpx.RequestError as e:
            raise APIRequestError(f"Rerank 请求失败: {e}")


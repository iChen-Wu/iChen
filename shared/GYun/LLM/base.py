from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Iterator, AsyncIterator
from pydantic import BaseModel, Field

class ToolFunction(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]

class ToolCall(BaseModel):
    index: Optional[int] = None  # 新增：用于流式时区分不同的工具调用
    id: Optional[str] = ""
    name: str
    arguments: Any = Field(default_factory=dict)

class StreamChunk(BaseModel):
    content: str = ""
    reasoning_content: str = ""  # 新增：思考过程片段
    finish_reason: Optional[str] = None
    tool_calls_delta: Optional[List[ToolCall]] = None
    usage: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    content: str = ""
    reasoning_content: str = ""  # 新增：完整思考过程
    tool_calls: Optional[List[ToolCall]] = None
    usage: Optional[Dict[str, Any]] = None

class RerankResult(BaseModel):
    index: int
    relevance_score: float
    document: Optional[str] = None

class RerankResponse(BaseModel):
    results: List[RerankResult]
    usage: Optional[Dict[str, Any]] = None

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    usage: Optional[Dict[str, Any]] = None

class AudioLabel(BaseModel):
    label: str
    score: float

class AudioClassificationResponse(BaseModel):
    labels: List[AudioLabel]
    
class BaseAdapter(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> Union[ChatResponse, Iterator[StreamChunk]]: pass

    @abstractmethod
    async def async_chat(self, messages: List[Dict], stream: bool = False, **kwargs) -> Union[ChatResponse, AsyncIterator[StreamChunk]]: pass

    def chat_with_tools(self, messages: List[Dict], tools: List[ToolFunction], **kwargs) -> ChatResponse:
        raise NotImplementedError("Tools not supported")

    async def async_chat_with_tools(self, messages: List[Dict], tools: List[ToolFunction], **kwargs) -> ChatResponse:
        raise NotImplementedError("Async tools not supported")

    def chat_with_image(self, prompt: str, image: Union[str, bytes], **kwargs) -> ChatResponse:
        raise NotImplementedError("Vision not supported")
    
    def embed_texts(self, texts: List[str], model: str = None, **kwargs) -> EmbeddingResponse:
        raise NotImplementedError("Embeddings not supported")
        
    async def async_embed_texts(self, texts: List[str], model: str = None, **kwargs) -> EmbeddingResponse:
        raise NotImplementedError("Async Embeddings not supported")
    
    def rerank_texts(self, query: str, documents: List[str], model: str = None, **kwargs) -> 'RerankResponse':
        raise NotImplementedError("Rerank not supported")


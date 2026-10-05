# GYun.LLM

一个轻量、高性能的 **大模型统一基础设施库**。
专为现代 Agent 开发设计，底层基于 `httpx` 与 `aiohttp`，将 LLM 对话、多模态、Agent 工具调用、语音识别 (ASR)、语音合成 (TTS) 与文本转向量完美整合。

## 核心特性

- **完整 Agent 闭环**：内置 `run_agent_loop` 与 `async_run_agent_loop`，自动处理多轮 Tool Calling、结果回传与多工具并发执行。
- **动态模型路由**：支持 `平台名/模型ID` 格式。无需修改库代码，即可随意调用硅基流动、火山引擎等平台上的任意新模型。
- **同步/异步双通道**：底层基于 `httpx` 连接池，异步客户端智能感知事件循环，跨线程/事件循环安全复用，完美适配现代异步框架。
- **全栈语音能力**：
  - ASR：硅基流动非流式（本地短音频极速识别）+ 火山引擎流式（WebSocket 实时打字机效果）。
  - TTS：火山引擎语音合成，支持自定义声音复刻。
- **极简适配器架构**：基于 OpenAI 兼容协议的模板方法模式，接入新平台仅需 3 行代码。
- **文本转向量**：原生支持 Embeddings 接口，一行代码切换不同平台的向量模型，为 RAG 提供基石。
- **生产级稳定性**：连接池懒加载、失败自动重试、流式容错机制。

---

## 安装

```bash
pip install httpx pydantic python-dotenv aiohttp
# 如果需要使用麦克风录音测试 ASR：
pip install sounddevice scipy
```

---

## 配置

在项目目录下创建 `.env` 文件，按需配置各平台的密钥：

```env
# DeepSeek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx

# 火山引擎 LLM (豆包)
VOLC_ARK_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# 火山引擎模型 ID：通过 vc/<短名> 动态路由使用，如 VC/doubao（自动补全为 VOLC_DOUBAO_MODEL_ID）
VOLC_DOUBAO_MODEL_ID=ep-xxxxxxxxxxxxxxxx

# 硅基流动
SILICONFLOW_API_KEY=sk-xxxxxxxxxxxxxxxx

# 火山引擎语音 (ASR/TTS)
VOLC_APP_ID=xxxxxxxx
VOLC_TOKEN=xxxxxxxxxxxxxxxx
VOLC_CLUSTER=volcano_icl
VOLC_VOICE_API_KEY=xxxxxxxxxxxxxxxx
# 声音复刻 ID (可选)：synthesize_audio(..., voice="hina") 会读取 VOICE_HINA_ID
VOICE_HINA_ID=xxxxxxxxxxxxxxxx

# 全局默认生成参数 (可选)
LLM_UNION_DEFAULT_MODEL=deepseek-chat
LLM_UNION_TEMPERATURE=0.7
LLM_UNION_TIMEOUT=60
LLM_UNION_MAX_TOKENS=4096
```

---

## 内置模型别名

以下无前缀别名开箱即用（注册于 `MODEL_REGISTRY`）：

| 别名 | 实际模型 | 说明 |
|------|----------|------|
| `deepseek-chat` | `deepseek-chat`（DeepSeek 官方） | 普通对话，`thinking=False` 时自动切换至此 |
| `deepseek-v3` | `deepseek-chat`（DeepSeek 官方） | 对话主力（`deepseek-chat` 的兼容别名） |
| `deepseek-reasoner` | `deepseek-reasoner`（DeepSeek 官方） | 深度思考，响应含 `reasoning_content`，`thinking=True` 时自动切换至此 |
| `glm` | `THUDM/GLM-4-9B-0414`（硅基流动） | 兼容旧用法；智谱官方接口已废弃，统一走硅基流动 |

其余平台模型一律使用 `平台名/模型ID` 动态路由（见下文「动态模型路由」）。

---

## 核心能力速览

### 1. 文本对话与流式输出
```python
from GYun.LLM import chat, stream_chat, async_stream_chat

# 1. 同步对话
resp = chat("你好，请用一句话介绍你自己", model="deepseek-v3")
print(resp.content)

# 2. 同步流式打字机效果
print("回复: ", end="")
for chunk in stream_chat("写一首关于秋天的五言诗", model="deepseek-v3"):
    print(chunk.content, end="", flush=True)
print()

# 3. 异步流式打字机效果
async def async_stream_test():
    print("异步回复: ", end="")
    async for chunk in await async_stream_chat("写两个字：你好", model="deepseek-v3"):
        print(chunk.content, end="", flush=True)
    print()

# 4. 深度思考模式（DeepSeek-R1 等推理模型）
# 开启/关闭方式（两种，任选其一）：
#   A. 显式控制：所有对话/流式接口均支持 thinking 参数
#      thinking=True  → 开启思考
#      thinking=False → 关闭思考
#      thinking=None（默认）→ 不干预，按所选模型默认行为
#   B. 手动选模型：model 直接用推理模型 deepseek-reasoner，
#      或普通模型 deepseek-v3 / deepseek-chat / 默认模型
# 平台实现差异（thinking 参数底层自动处理，无需关心）：
#   - DeepSeek 官方：无开关参数 → 开启自动切换 deepseek-reasoner，关闭自动切回 deepseek-chat
#   - 硅基流动：透传 enable_thinking=True/False（如 SF/deepseek-ai/DeepSeek-R1）
#   - 火山方舟：透传 thinking={"type": "enabled"/"disabled"}
# 推理模型响应中：reasoning_content = 思考过程，content = 最终回答；关闭思考时 reasoning_content 为空。
# 注意：DeepSeek 官方推理模型不支持工具调用（function calling），temperature/top_p 等采样参数会被忽略。
content_started = False
print("【思考过程】：", end="", flush=True)
for chunk in stream_chat("证明根号2是无理数", thinking=True):   # 开启思考（DeepSeek 自动切到 deepseek-reasoner）
    if chunk.reasoning_content:
        print(chunk.reasoning_content, end="", flush=True)
    if chunk.content:
        if not content_started:
            print("\n\n【最终回答】：", end="", flush=True)
            content_started = True
        print(chunk.content, end="", flush=True)
print()
```

#### 联网搜索（火山引擎示例）

大模型标准的 OpenAI 协议中没有统一的搜索开关，但本库支持直接透传各平台特有的联网搜索参数。以火山引擎（豆包）为例：

```python
from GYun.LLM import chat
from GYun.LLM.base import ToolFunction

# 火山引擎通过传入特定格式的 tools 字典开启联网
resp = chat(
    "今天有什么科技新闻？",
    model="VC/doubao", 
    tools=[{"type": "web_search", "web_search": {"enable": True, "search_query": True}}]
)
print(resp.content)

# 也可以在 Agent Loop 中与自定义工具混合使用
tools = [
    {"type": "web_search", "web_search": {"enable": True}},
    ToolFunction(name="get_weather", description="获取天气", parameters={...})
]
```

### 2. Token 用量统计
无论是非流式还是流式调用，底层均完整保留了 `usage` 统计信息（流式输出会在最后一帧返回）。

```python
from GYun.LLM import chat, stream_chat

# 1. 非流式调用直接获取
resp = chat("你好", model="deepseek-v3")
if resp.usage:
    print(f"消耗总 Tokens: {resp.usage.get('total_tokens')}")

# 2. 流式调用在最后一帧获取
total_tokens = 0
for chunk in stream_chat("写首诗", model="deepseek-v3"):
    print(chunk.content, end="", flush=True)
    
    # 捕获最后一帧的 usage
    if chunk.usage:
        total_tokens = chunk.usage.get('total_tokens')

print(f"\n\n本次消耗总 Tokens: {total_tokens}")
```

### 3. 安全中断与节省 Token
在流式输出过程中，如果你已经拿到了需要的内容（或遇到网络波动），直接使用 `break` 即可安全中断。底层会自动向服务端发送断开信号，**立即停止后续 Token 的生成与计费**。

```python
from GYun.LLM import stream_chat

print("回复: ", end="")
for chunk in stream_chat("写一篇一万字的长篇小说", model="deepseek-v3"):
    print(chunk.content, end="", flush=True)
    
    # 满足条件后主动中断
    if len(chunk.content) > 50:
        print("\n\n[主动中断生成，不再消耗后续 Token]")
        break  # 触发底层 resp.close()，服务端停止生成
```

### 4. 生成参数控制
除了在 `.env` 中配置全局默认的 `LLM_UNION_TEMPERATURE` 和 `LLM_UNION_MAX_TOKENS` 外，你可以在每次调用时动态覆盖这些参数，并支持透传 OpenAI 标准的高级采样参数。

支持的参数包括：`temperature`, `max_tokens`, `top_p`, `frequency_penalty`, `presence_penalty`, `stop`, `seed`。

```python
from GYun.LLM import chat

resp = chat(
    "写一个搞笑的段子",
    model="deepseek-v3",
    temperature=0.9,        # 提高随机性，更有创意
    top_p=0.95,             # 核采样
    frequency_penalty=0.5,  # 惩罚重复词，避免车轱辘话
    max_tokens=500          # 限制最长输出
)
print(resp.content)
```

### 5. 动态模型路由
平台前缀支持短写：`SF`=硅基流动、`VC`=火山（旧前缀 `siliconflow`/`volc` 仍兼容）。
```python
# 调用硅基流动的 Qwen 模型
chat("你好", model="SF/Qwen/Qwen2.5-7B-Instruct")

# 调用硅基流动的免费向量模型
embed_texts(["你好"], model="SF/BAAI/bge-m3")

# 调用火山模型：VC/doubao 自动补全为环境变量 VOLC_DOUBAO_MODEL_ID
chat("你好", model="VC/doubao")
```

### 6. Agent 工具调用 (多轮闭环)
```python
import asyncio
from GYun.LLM import async_run_agent_loop
from GYun.LLM import ToolFunction

tools = [
    ToolFunction(
        name="get_weather",
        description="获取指定城市的天气",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    )
]

async def my_executor(name, args):
    if name == "get_weather": return f"{args['city']} 25°C 晴"
    return "未知"

async def main():
    # 自动并发执行工具，并多轮对话直到得出最终答案
    answer = await async_run_agent_loop(
        prompt="对比北京和上海的天气",
        tools=tools, async_tool_executor=my_executor, model="deepseek-v3"
    )
    print(answer)
```

### 7. 结构化输出与多模态
```python
from GYun.LLM import chat, chat_with_image

# JSON Mode
resp = chat("提取：张三25岁。返回JSON含name和age", response_format={"type": "json_object"})

# 视觉理解
resp = chat_with_image("描述图片", image="test.jpg", model="SF/Qwen/Qwen2-VL-7B-Instruct")
```

### 8. 语音识别 (ASR) 与音频分类
```python
from GYun.LLM import transcribe_audio, async_transcribe_audio_stream, classify_audio

# 1. 非流式 (硅基流动，适合本地短音频)
text = transcribe_audio("test.mp3", language="zh")

# 2. 流式 (火山引擎，适合长音频，实时返回片段)
async def stream_asr():
    async for chunk in async_transcribe_audio_stream("long_audio.wav"):
        print(chunk, end="", flush=True)

# 3. 音频分类 (情感/声学事件，复用 ASR 接口解析 SenseVoice 的 <|...|> 标签)
resp = classify_audio("test.wav")
for label in resp.labels:
    print(f"{label.label} ({label.score:.2f})")
```

### 9. 语音合成 (TTS) 与声音复刻
```python
from GYun.LLM import synthesize_audio

# 使用默认音色
audio_bytes = synthesize_audio("你好世界")

# 使用 .env 中配置的复刻音色 (voice="hina" 对应 VOICE_HINA_ID)
audio_bytes = synthesize_audio("你好世界", voice="hina")
with open("out.mp3", "wb") as f: f.write(audio_bytes)
```

### 10. 文本转向量
```python
from GYun.LLM import embed_texts

# 支持动态路由各平台向量模型
resp = embed_texts(["文本1", "文本2"], model="SF/BAAI/bge-m3")
print(resp.embeddings[0][:5])
```

### 11. 文本重排序
在 RAG（检索增强生成）场景中，向量检索（Embedding）负责快速“海选”出 Top-N 相关文档，但往往不够精准。重排序模型负责“精排”，它能逐字阅读并给出精准的相关性打分，过滤掉无关文档，极大减少大模型的幻觉。

```python
from GYun.LLM import rerank_texts

query = "如何注销账号？"
# 假设这是向量库捞出来的候选文档
documents = [
    "本系统使用 Python 3.10 开发。",
    "用户可以在设置页面点击‘注销账号’按钮来永久删除账号。",
    "天气真好，适合出去玩。"
]

# 调用硅基流动的重排序模型精排
resp = rerank_texts(query, documents, model="SF/BAAI/bge-reranker-v2-m3")

# 打印精排结果
for res in resp.results:
    print(f"得分: {res.relevance_score:.4f} | 文档: {documents[res.index]}")

# 输出结果：
# 得分: 0.9656 | 文档: 用户可以在设置页面点击‘注销账号’按钮来永久删除账号。
# 得分: 0.0000 | 文档: 本系统使用 Python 3.10 开发。
# 得分: 0.0000 | 文档: 天气真好，适合出去玩。
```


---

## 进阶：扩展自定义平台

任何兼容 OpenAI 协议的平台（如 Kimi、通义千问）只需 4 步即可接入：

1. 创建适配器 `adapters/kimi_adapter.py`：
```python
from GYun.LLM.adapters._openai_compatible import OpenAICompatibleAdapter
from GYun.LLM._config import get_config

class KimiAdapter(OpenAICompatibleAdapter):
    def __init__(self, model_name: str):
        super().__init__(model_name, "https://api.moonshot.cn/v1", get_config().KIMI_API_KEY)
```

2. 在 `_config.py` 的 `Config` 类中添加对应的 API Key 属性（用于读取 `.env`）：
```python
KIMI_API_KEY: str = os.getenv("KIMI_API_KEY", "")
```

3. 在 `_config.py` 的 `DYNAMIC_PLATFORMS` 注册前缀：
```python
"kimi": ("adapters.kimi_adapter", "KimiAdapter"),
```

4. 直接调用：`chat("你好", model="kimi/moonshot-v1-8k")`

---

## API 参考

### 顶层函数

推荐直接从 `GYun.LLM` 导入使用。所有函数均为单例 `LLMClient` 的薄封装，内部自动管理连接池与模型路由。

```python
from GYun.LLM import (
    chat, stream_chat, chat_with_image, chat_with_tools, run_agent_loop,
    async_chat, async_stream_chat, async_chat_with_tools, async_run_agent_loop,
    transcribe_audio, async_transcribe_audio_stream, synthesize_audio,
    embed_texts, async_embed_texts, rerank_texts, classify_audio,
    init_llm, get_client, reset_client, LLMClient,
)
```

| 函数 | 签名 | 返回 | 说明 |
|------|------|------|------|
| `chat` | `(messages, model=None, stream=False, thinking=None, **kwargs)` | `ChatResponse` | 单轮对话。`messages` 可为字符串（自动包成 user 消息）或 OpenAI 格式消息列表；`thinking=True/False` 显式开启/关闭思考（DeepSeek 自动切换模型，硅基流动透传 `enable_thinking`，火山方舟透传 `thinking` 字段） |
| `stream_chat` | `(messages, model=None, thinking=None, **kwargs)` | `Iterator[StreamChunk]` | 同步流式对话（生成器，逐帧 yield），`thinking` 语义同 `chat` |
| `chat_with_tools` | `(messages, tools, model=None, **kwargs)` | `ChatResponse` | 带工具定义的单轮对话，响应含 `tool_calls` |
| `chat_with_image` | `(prompt, image, model=None, **kwargs)` | `ChatResponse` | 视觉理解。`image` 支持路径 / bytes / base64 / data URL |
| `run_agent_loop` | `(prompt, tools, tool_executor, model=None, max_steps=5, **kwargs)` | `str` | 同步 Agent 多轮闭环，自动执行工具并回传结果 |
| `async_chat` | `(messages, model=None, stream=False, thinking=None, **kwargs)` | `ChatResponse` / `AsyncIterator[StreamChunk]` | 异步对话，`stream=True` 时返回异步流，`thinking` 语义同 `chat` |
| `async_stream_chat` | `(messages, model=None, thinking=None, **kwargs)` | `AsyncIterator[StreamChunk]` | 异步流式对话（先 `await` 拿到迭代器，再 `async for`），`thinking` 语义同 `chat` |
| `async_chat_with_tools` | `(messages, tools, model=None, **kwargs)` | `ChatResponse` | 异步带工具对话 |
| `async_run_agent_loop` | `(prompt, tools, async_tool_executor, model=None, max_steps=5, **kwargs)` | `str` | 异步 Agent 闭环，工具并发执行，单个工具异常不中断整体 |
| `transcribe_audio` | `(audio_path, model="FunAudioLLM/SenseVoiceSmall", platform="siliconflow", language=None)` | `str` | 非流式语音识别（硅基流动） |
| `async_transcribe_audio_stream` | `(audio_path)` | `AsyncIterator[str]` | 流式语音识别（火山引擎 WebSocket，实时返回文本片段） |
| `classify_audio` | `(audio_path, model="FunAudioLLM/SenseVoiceSmall")` | `AudioClassificationResponse` | 音频分类（情感/声学事件），复用 ASR 接口解析 SenseVoice 标签 |
| `synthesize_audio` | `(text, voice=None, **kwargs)` | `bytes` | 语音合成（火山 TTS）。`voice` 支持系统音色 ID 或 `VOICE_XXX_ID` 环境变量别名 |
| `embed_texts` | `(texts, model=None, **kwargs)` | `EmbeddingResponse` | 文本转向量 |
| `async_embed_texts` | `(texts, model=None, **kwargs)` | `EmbeddingResponse` | 异步文本转向量 |
| `rerank_texts` | `(query, documents, model=None, **kwargs)` | `RerankResponse` | 文本重排序（RAG 精排） |
| `get_client` | `()` | `LLMClient` | 获取全局单例客户端 |
| `reset_client` | `()` | `None` | 清空单例与适配器缓存（连接池被关闭） |
| `init_llm` | `(**config_overrides)` | `LLMClient` | 用覆盖项重建配置并返回新客户端。可覆盖 `DEFAULT_MODEL`、`MODEL_REGISTRY`、`DYNAMIC_PLATFORMS` 等 |

### LLMClient 类

`LLMClient(config)` 直接实例化可持有独立配置，方法与顶层函数一一对应：

- `chat` / `stream_chat` / `chat_with_tools` / `chat_with_image`
- `async_chat` / `async_stream_chat` / `async_chat_with_tools`
- `run_agent_loop` / `async_run_agent_loop`
- `transcribe_audio` / `async_transcribe_audio_stream` / `classify_audio` / `synthesize_audio`
- `embed_texts` / `async_embed_texts` / `rerank_texts`

> 顶层函数等价于 `get_client()` 上的同名方法，日常使用顶层函数即可。

### 数据模型 (`GYun.LLM.base`)

均为 `pydantic.BaseModel`：

| 模型 | 字段 | 说明 |
|------|------|------|
| `ToolFunction` | `name: str` `description: str` `parameters: dict` | 工具定义（JSON Schema 形式的 `parameters`） |
| `ToolCall` | `index: int|None` `id: str` `name: str` `arguments: any` | 模型发起的工具调用（流式时 `index` 区分多个调用） |
| `StreamChunk` | `content: str` `reasoning_content: str` `finish_reason: str|None` `tool_calls_delta: list[ToolCall]|None` `usage: dict|None` | 流式单帧；`usage` 仅在最后一帧返回 |
| `ChatResponse` | `content: str` `reasoning_content: str` `tool_calls: list[ToolCall]|None` `usage: dict|None` | 完整响应；`reasoning_content` 为深度思考模型的思考过程 |
| `RerankResult` | `index: int` `relevance_score: float` `document: str|None` | 重排序单条结果 |
| `RerankResponse` | `results: list[RerankResult]` `usage: dict|None` | 重排序结果 |
| `EmbeddingResponse` | `embeddings: list[list[float]]` `usage: dict|None` | 向量结果 |
| `AudioLabel` | `label: str` `score: float` | 音频分类标签 |
| `AudioClassificationResponse` | `labels: list[AudioLabel]` | 音频分类结果 |

### 异常 (`GYun.LLM.exceptions`)

| 异常 | 触发场景 |
|------|----------|
| `LLMUnionBaseError` | 所有异常的基类，捕获它即可兜底 |
| `ModelNotFoundError` | 模型别名/前缀无法路由（如未注册的模型名、环境变量未配置） |
| `APIRequestError` | 网络请求失败、非 401/429 的服务端错误、语音/TTS 调用失败 |
| `RateLimitError` | HTTP 429 限流 |
| `AuthenticationError` | API Key 无效（401）或 TTS 鉴权失败 |

### 配置 (GYun.LLM._config)

`Config` 类的类属性即配置项，均可通过 `.env` 或 `init_llm(**overrides)` 覆盖：

| 属性 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `DEFAULT_MODEL` | `LLM_UNION_DEFAULT_MODEL` | `deepseek-chat` | 未指定 `model` 时的默认模型 |
| `DEFAULT_TEMPERATURE` | `LLM_UNION_TEMPERATURE` | `0.7` | 默认采样温度 |
| `DEFAULT_TIMEOUT` | `LLM_UNION_TIMEOUT` | `60` | HTTP 超时（秒） |
| `DEFAULT_MAX_TOKENS` | `LLM_UNION_MAX_TOKENS` | `4096` | 默认最大输出长度 |
| `DEEPSEEK_API_KEY` | `DEEPSEEK_API_KEY` | `""` | DeepSeek 密钥 |
| `SILICONFLOW_API_KEY` | `SILICONFLOW_API_KEY` | `""` | 硅基流动密钥 |
| `VOLC_ARK_API_KEY` | `VOLC_ARK_API_KEY` | `""` | 火山方舟（LLM）密钥 |
| `VOLC_APP_ID` / `VOLC_TOKEN` | 同名 | `""` | 火山语音（ASR/TTS）鉴权 |
| `VOLC_CLUSTER` | `VOLC_CLUSTER` | `""` | 火山语音集群 |
| `VOLC_VOICE_API_KEY` | `VOLC_VOICE_API_KEY` | `""` | 火山语音 API Key |
| `MODEL_REGISTRY` | — | 见「内置模型别名」 | 无前缀模型别名表 |
| `DYNAMIC_PLATFORMS` | — | `SF` / `VC` / `deepseek`（旧前缀 `siliconflow`/`volc` 兼容） | 动态前缀路由表；`VC/<短名>` 自动补全为 `VOLC_<短名大写>_MODEL_ID` 环境变量 |
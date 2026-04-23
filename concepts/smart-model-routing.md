---
title: Smart Model Routing 智能模型路由
created: 2026-04-08
updated: 2026-04-18
type: concept
tags: [architecture, module, model-routing, performance, caching, anthropic]
sources: [agent/model_metadata.py, agent/models_dev.py, hermes_cli/model_switch.py, hermes_cli/model_normalize.py]
---

# Smart Model Routing — 智能模型路由

## 概述

> **注意**：本页涵盖**多个模块**的协作，而非仅 `agent/smart_model_routing.py`。`smart_model_routing.py` 本身只是一个约 195 行的轻量启发式模块，负责 cheap/strong 消息路由（决定用便宜模型还是强模型处理当前消息）。本页讨论的更广泛的模型基础设施——元数据解析、上下文长度探测、模型切换管道——分布在下列四个核心模块中。

Smart Model Routing 是 Hermes Agent 的**模型元数据解析与上下文长度自动检测**系统，由四个核心模块组成：

| 模块 | 源码 | 职责 |
|---|---|---|
| **model_metadata.py** | 36KB/941行 | 上下文长度检测、端点探测、token 估算 |
| **models_dev.py** | 25KB/781行 | models.dev 4000+ 模型数据库集成 |
| **model_switch.py** | 32KB/927行 | 模型切换管道（别名解析 → 凭证 → 元数据） |
| **model_normalize.py** | 外部模块 | 各提供商模型名称规范化 |

核心理念：**10 级上下文长度解析链 + models.dev 4000+ 模型数据库 + 本地服务器自动探测。**

## 架构原理

### 上下文长度解析链（10 级）

```python
def get_model_context_length(model, base_url, api_key, config_context_length, provider):
    """
    0. config 显式覆盖 → 用户知道最好
    1. 持久化缓存（之前探测到的 model@base_url）
    2. 活跃端点元数据（/models 端点，仅限自定义端点）
    3. 本地服务器查询（Ollama/LM Studio/vLLM/llama.cpp）
    4. Anthropic /v1/models API（仅 API Key，不含 OAuth）
    5. models.dev 注册表（提供商感知，含 Nous 后缀匹配）
    6. OpenRouter 实时 API 元数据
    7. 硬编码默认值（模糊匹配，最长 key 优先）
    8. 本地服务器最后尝试
    9. 默认回退: 128K
    """
```

**设计哲学**：从最精确到最宽松，每级失败才进入下一级。

### 本地服务器自动探测

```python
def detect_local_server_type(base_url):
    """
    探测顺序:
    1. LM Studio → /api/v1/models (最特定)
    2. Ollama → /api/tags (验证 response 包含 "models")
    3. llama.cpp → /v1/props 或 /props (检查 default_generation_settings)
    4. vLLM → /version (检查 "version" 字段)
    """
```

每种服务器类型有不同的元数据获取方式：

| 服务器 | 端点 | 上下文长度来源 |
|---|---|---|
| Ollama | /api/show | model_info.context_length 或 num_ctx 参数 |
| LM Studio | /api/v1/models | loaded_instances.config.context_length |
| vLLM | /v1/models/{model} | max_model_len |
| llama.cpp | /v1/props | n_ctx (实际分配的上下文) |

### 端点元数据获取

```python
def fetch_endpoint_model_metadata(base_url, api_key):
    """
    1. 尝试 {base_url}/models 和 {base_url}/v1/models
    2. 解析每个模型的 context_length、max_completion_tokens、pricing
    3. 如果是 llama.cpp → 额外查询 /v1/props 获取实际 n_ctx
    4. 缓存 5 分钟
    """
```

### 持久化缓存

```python
# 缓存 key: model@base_url
# 同一模型名从不同提供商服务可能有不同限制
def save_context_length(model, base_url, length):
    # 写入 ~/.hermes/context_length_cache.yaml
    # 格式: {context_lengths: {"qwen3@http://localhost:11434/v1": 131072}}
```

### 错误消息中的上下文长度提取

```python
def parse_context_limit_from_error(error_msg):
    """
    从 API 错误消息中提取实际上下文限制:
    - "maximum context length is 32768 tokens"
    - "context_length_exceeded: 131072"
    - "250000 tokens > 200000 maximum"
    """
```

## 核心组件

### 1. models.dev 集成

```python
# 4000+ 模型，109+ 提供商
# 离线优先: 打包快照 → 磁盘缓存 → 网络获取 → 后台刷新(60分钟)

@dataclass
class ModelInfo:
    id: str
    name: str
    family: str
    provider_id: str
    reasoning: bool
    tool_call: bool
    attachment: bool       # 视觉支持
    context_window: int
    max_output: int
    cost_input: float      # 每百万 token
    cost_output: float
    cost_cache_read: float
    # ... 更多字段
```

**三级缓存**：
1. **内存缓存**：1 小时 TTL
2. **磁盘缓存**：`~/.hermes/models_dev_cache.json`
3. **网络获取**：`https://models.dev/api.json`

### 2. 模型能力查询

```python
def get_model_capabilities(provider, model) -> ModelCapabilities:
    """
    返回:
    - supports_tools: 是否支持工具调用
    - supports_vision: 是否支持视觉
    - supports_reasoning: 是否支持推理
    - context_window: 上下文窗口
    - max_output_tokens: 最大输出
    - model_family: 模型家族
    """
```

### 3. 模型切换系统

```python
def switch_model(raw_input, current_provider, current_model, ...) -> ModelSwitchResult:
    """
    两条路径:
    
    A. 给定 --provider:
       1. 解析提供商 → 解析凭证 → 解析别名或使用原样
       2. 无模型 → 从端点自动检测
    
    B. 未给定 --provider:
       1. 在当前提供商尝试别名
       2. 别名存在但当前提供商没有 → 回退到其他认证提供商
       3. 聚合器 → vendor/model slug 转换
       4. 聚合器目录搜索
       5. detect_provider_for_model() 兜底
       6. 解析凭证 → 规范化模型名
    """
```

### 4. 别名系统

```python
MODEL_ALIASES = {
    "sonnet":  ModelIdentity("anthropic", "claude-sonnet"),
    "opus":    ModelIdentity("anthropic", "claude-opus"),
    "gpt5":    ModelIdentity("openai", "gpt-5"),
    "gemini":  ModelIdentity("google", "gemini"),
    "qwen":    ModelIdentity("qwen", "qwen"),
    # ... 20+ 短别名
}
```

别名解析是**动态的**——通过查询 models.dev 目录找到匹配的最新模型版本，而非硬编码。

### 5. Provider 前缀处理

```python
_PROVIDER_PREFIXES = frozenset({
    "openrouter", "nous", "openai-codex", "anthropic", "alibaba",
    "google", "glm", "kimi", "deepseek", "qwen", ...
})

def _strip_provider_prefix(model):
    """
    "local:my-model" → "my-model"
    "qwen3.5:27b" → "qwen3.5:27b"  (保留 Ollama tag)
    "deepseek:latest" → "deepseek:latest" (保留 Ollama tag)
    """
```

**关键**：区分 provider 前缀和 Ollama 的 model:tag 格式。

### 6. 智能模糊匹配

上下文长度默认值使用**最长 key 优先**的模糊匹配：

```python
DEFAULT_CONTEXT_LENGTHS = {
    "claude-sonnet-4.6": 1000000,   # 特定版本
    "claude": 200000,               # 兜底 (必须排在后面)
    "gpt-5": 128000,
    "gemini": 1048576,
    "qwen": 131072,
    # ...
}

# 只检查 default_model in model (不是反向)
# 避免 "claude-sonnet-4" 错误匹配 "claude-sonnet-4-6"
```

### 7. 上下文探测降级

```python
CONTEXT_PROBE_TIERS = [128_000, 64_000, 32_000, 16_000, 8_000]

def get_next_probe_tier(current_length):
    """从 128K 开始，遇错逐步降级"""
```

### 8. Token 估算

```python
def estimate_tokens_rough(text):
    """~4 chars/token 的粗略估算"""
    return len(text) // 4

def estimate_request_tokens_rough(messages, system_prompt, tools):
    """
    完整请求估算，包括:
    - 系统提示
    - 对话消息
    - 工具 schemas (50+ 工具可达 20-30K tokens)
    """
```

## 设计优越性

### 对比硬编码方案

| 维度 | 硬编码 | Smart Model Routing |
|---|---|---|
| 新模型支持 | 需要更新代码 | models.dev 自动更新 |
| 本地服务器 | 手动配置 | 自动探测 4 种服务器类型 |
| 上下文长度 | 静态字典 | 10 级解析链（0-9） |
| 凭证管理 | 硬编码 | 通过 runtime_provider 解析 |
| 错误恢复 | 无 | 从错误消息提取限制 |
| 离线支持 | 无 | 打包快照 + 磁盘缓存 |

## 配置与操作

### 显式覆盖

```yaml
# config.yaml
model:
  context_length: 128000  # 直接覆盖所有检测
```

### 别名扩展

```yaml
# config.yaml
model_aliases:
  qwen:
    model: "qwen3.5:397b"
    provider: custom
    base_url: "https://ollama.com/v1"
```

## 定价估算

```python
# agent/usage_pricing.py

def estimate_usage_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算 API 调用成本"""
    pricing = {
        "claude-opus-4.6": {"input": 15.0, "output": 75.0},  # $/MTok
        "claude-sonnet-4": {"input": 3.0, "output": 15.0},
        "gpt-4o": {"input": 2.5, "output": 10.0},
        # ...
    }
    
    prices = pricing.get(model, {"input": 5.0, "output": 15.0})
    input_cost = (prompt_tokens / 1_000_000) * prices["input"]
    output_cost = (completion_tokens / 1_000_000) * prices["output"]
    return input_cost + output_cost
```

## OpenRouter 提供商路由

```python
# 提供商偏好
provider_preferences = {}
if self.providers_allowed:
    provider_preferences["order"] = self.providers_allowed
if self.providers_ignored:
    provider_preferences["ignore"] = self.providers_ignored
if self.providers_order:
    provider_preferences["order"] = self.providers_order
if self.provider_sort:
    provider_preferences["sort"] = self.provider_sort

# 发送到 OpenRouter
extra_body["provider"] = provider_preferences
```

### 提供商排序选项

```python
# sort 选项
"sort": "price"       # 按价格排序
"sort": "throughput"  # 按吞吐量排序
"sort": "latency"     # 按延迟排序
```

## 元数据缓存

```python
# OpenRouter 模型元数据缓存（1 小时 TTL）
_model_metadata_cache: dict = {}
_metadata_cache_time: float = 0
_METADATA_CACHE_TTL = 3600  # 1 小时

def fetch_model_metadata(model: str = None) -> dict:
    """获取模型元数据（带缓存）"""
    now = time.time()
    if now - _metadata_cache_time < _METADATA_CACHE_TTL:
        return _model_metadata_cache
    
    # 后台线程预温缓存
    threading.Thread(
        target=lambda: fetch_model_metadata(),
        daemon=True,
    ).start()
```

## 推理模型支持

```python
def _supports_reasoning_extra_body(self) -> bool:
    """判断是否可以安全发送 reasoning extra_body"""
    
    # 直接 Nous Portal
    if "nousresearch" in self._base_url_lower:
        return True
    
    # OpenRouter 路由
    if "openrouter" not in self._base_url_lower:
        return False
    
    # 已知支持推理的模型前缀
    reasoning_model_prefixes = (
        "deepseek/",
        "anthropic/",
        "openai/",
        "x-ai/",
        "google/gemini-2",
        "qwen/qwen3",
    )
    return any(self.model.lower().startswith(prefix) for prefix in reasoning_model_prefixes)
```

## 会话状态跟踪

```python
# 累积 token 使用量
self.session_prompt_tokens = 0
self.session_completion_tokens = 0
self.session_total_tokens = 0
self.session_api_calls = 0
self.session_input_tokens = 0
self.session_output_tokens = 0
self.session_cache_read_tokens = 0
self.session_cache_write_tokens = 0
self.session_reasoning_tokens = 0
self.session_estimated_cost_usd = 0.0
self.session_cost_status = "unknown"
self.session_cost_source = "none"

def reset_session_state(self):
    """重置所有会话级 token 计数器"""
    self.session_total_tokens = 0
    self.session_input_tokens = 0
    self.session_output_tokens = 0
    # ... 重置所有计数器
    self._user_turn_count = 0
```

## 新增 Provider（v0.10.0，2026-04-16）

### AWS Bedrock（原生 Converse API）

双路径架构（`agent/bedrock_adapter.py`，1098 行）：
- **Claude 模型** → AnthropicBedrock SDK（保留 prompt caching、thinking budgets）
- **非 Claude 模型** → Converse API via boto3（Nova、DeepSeek、Llama、Mistral）

特性：
- IAM credential chain + Bedrock API Key 两种认证模式
- `ListFoundationModels` + `ListInferenceProfiles` 动态模型发现
- Streaming + delta callbacks + guardrails
- `/usage` 定价支持 7 个 Bedrock 模型
- `hermes doctor` + `hermes auth` 集成

### Google Gemini CLI OAuth

通过 Cloud Code Assist 后端（`cloudcode-pa.googleapis.com`）接入 Gemini，与 Google 官方 `gemini-cli` 使用同一后端。

两个新模块（`agent/` 下）：
- `google_oauth.py`（1048 行）：PKCE Authorization Code flow，跨进程文件锁（fcntl POSIX / msvcrt Windows），refresh token 自动续期，并发刷新去重
- `gemini_cloudcode_adapter.py`：provider 注册，模型发现，streaming

支持免费层（个人账户每日配额）和付费层（Standard/Enterprise via GCP project）。

### Ollama Cloud

作为内置 provider 注册（与 gemini、xai 等平级）：
- `OLLAMA_API_KEY` 环境变量认证
- Provider 别名：`ollama` → custom（本地），`ollama_cloud` → ollama-cloud
- models.dev 集成获取准确上下文长度
- 动态模型发现 + 磁盘缓存（1 小时 TTL）
- 保留 Ollama `model:tag` 格式（不做规范化）

### Step Plan（v2026.4.18+）

StepFun 首款 API-key provider（Step Plan），支持国际和中国区设置。从 `/step_plan/v1/models` 动态发现模型，离线有编码向 fallback 目录。

### Vercel AI Gateway（v2026.4.18+）

新增 `ai-gateway` provider，通过 Vercel AI Gateway 统一访问多家模型：
- 定制模型列表（`AI_GATEWAY_MODELS`，OSS first，Kimi K2.5 推荐默认）
- Live pricing 翻译（Vercel input/output → prompt/completion 格式）
- 自动把免费 Moonshot 模型顶到 picker 首位
- 提供商 picker 排序优先级提升
- 使用 Vercel 的 deep-link 创建 API key

### OpenRouter 工具支持过滤（v2026.4.18+）

hermes-agent 是工具调用优先的 agent，只有支持 `tools` 的模型才能驱动 agent 循环。`fetch_openrouter_models()` 现在过滤掉 `supported_parameters` 明确不含 `tools` 的模型（如纯图像、completion-only）。

宽容模式：`supported_parameters` 缺失时默认允许（Nous Portal、私有镜像、旧 snapshot 可能不填）。只隐藏明确声明了但不含 `tools` 的模型。

### Tool Gateway（Nous 订阅制工具网关）

把 web 搜索、TTS、浏览器、图片生成等工具的 API 调用路由到 Nous 托管的统一网关，用户无需自备各家 API key：

```yaml
# config.yaml — 按工具类别 opt-in
web:
  use_gateway: true
tts:
  use_gateway: true
image_gen:
  use_gateway: true
browser:
  use_gateway: true
```

- `managed_nous_tools_enabled()` 检查 Nous 登录状态 + 订阅层级
- `prefers_gateway(section)` 共享辅助函数，4 个工具运行时统一使用
- `hermes model` 交互流程：Nous 登录后展示可用工具列表，用户选择启用全部 / 仅未配置的 / 跳过
- 免费层用户看到升级提示

## 与其他系统的关系

- [[context-compressor-architecture]] — 使用 get_model_context_length() 确定上下文限制
- [[prompt-caching-optimization]] — 缓存成本信息来自 models.dev
- [[auxiliary-client-architecture]] — 辅助模型通过 models.dev 解析上下文长度

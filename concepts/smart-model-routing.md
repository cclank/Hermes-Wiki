---
title: Smart Model Routing 智能模型路由
created: 2026-04-08
updated: 2026-05-28
type: concept
tags: [architecture, module, model-routing, performance, caching, anthropic, provider-plugin]
sources: [agent/model_metadata.py, agent/models_dev.py, hermes_cli/model_switch.py, hermes_cli/model_normalize.py, providers/, plugins/model-providers/]
---

> v0.13.0 起，全部 30 个 provider 走 `providers/base.py:ProviderProfile` ABC + `plugins/model-providers/<name>/` 插件目录。Provider 行为是 *声明性* 的，由 transport 层读取，不再硬编码进 `model_metadata.py`。详见 [[provider-profile-plugins]]。

# Smart Model Routing — 智能模型路由

> **v0.13.0+ 重要变化**：模型路由的 provider 维度现在由 [[provider-plugin-system]] 提供 ——
> `providers/base.py:39 ProviderProfile` ABC + `plugins/model-providers/` 29 个内置 provider 插件，每个 profile 暴露 `get_hostname()` / `fetch_models()` / `default_aux_model` 等钩子，作为本页解析链的**第一站**。
> 详见 [[provider-plugin-system]]。
>
> **v0.12.0+ Remote model catalog manifest**：OpenRouter + Nous Portal 的 model catalog 不再硬编码在仓库，改成远端 manifest 拉取（PR #16033）。新模型上架**不需要发版**即可见。

> **2026-05-28 增量（v0.15.0）— claude-opus-4.8 / claude-opus-4.8-fast 接入**（commit `1a7479573`，#34003）
>
> Anthropic 2026-05-27 发布 Claude Opus 4.8（OpenRouter / Anthropic / Bedrock / Claude Platform on AWS）。三处注册，全部现行可验证：
> - `hermes_cli/models.py:35-36` — OpenRouter fallback 快照新增 `anthropic/claude-opus-4.8` + `anthropic/claude-opus-4.8-fast`（注 `"2x price, higher output speed"`）；`:144` Nous Portal curated list；`:296` Anthropic-native picker（`claude-opus-4-8`）。
> - `agent/model_metadata.py:144-145` — `DEFAULT_CONTEXT_LENGTHS`：`claude-opus-4-8` / `claude-opus-4.8` = **1,000,000**（与 4.6/4.7 一致）；`:98` 最大输出 `128_000`。
> - `agent/anthropic_adapter.py:80,85,89` — `4-8`/`4.8` 加入 `_XHIGH_EFFORT_SUBSTRINGS` / `_ADAPTIVE_THINKING_SUBSTRINGS` / `_NO_SAMPLING_PARAMS_SUBSTRINGS`：4.8 继承 Opus 4.7 API 契约（仅 adaptive thinking、支持 xhigh effort、采样参数 temperature/top_p/top_k 返回 400）。
>
> **关键差异**：`claude-opus-4.8-fast` 是**独立 model ID**、定价为基础模型 **2×**（旧 Opus 4.6/4.7 fast 溢价为 6×），**不是** Opus 4.6 那种 `speed: "fast"` 请求参数。live catalog 可达时自动 surface，fallback 快照仅 manifest 拉取失败时生效。详见 [[2026-05-28-update]]。

## v0.11.0 - v0.14.0 新增的 provider / 推理路径

| 路径 | 描述 | api_mode |
|------|------|---------|
| **xAI Grok via SuperGrok OAuth (1M ctx)** | grok-4.3 升 1M token；`hermes auth add xai-oauth` | xAI Responses |
| **GPT-5.5 via Codex OAuth** | ChatGPT Pro 订阅；live model discovery | Codex Responses |
| **AWS Bedrock 原生**（Converse API） | `agent/transports/bedrock.py` | bedrock_converse |
| **NVIDIA NIM** | 原生 | chat_completions |
| **Arcee AI** | — | chat_completions |
| **Step Plan**（StepFun） | — | chat_completions |
| **Google Gemini CLI OAuth** | `agent/google_code_assist.py` | chat_completions / native |
| **Gemini AI Studio 原生** | `agent/gemini_native_adapter.py` | gemini_native |
| **Vercel ai-gateway** | pricing + 动态发现 | chat_completions |
| **LM Studio**（升一等 provider） | live `/models`，doctor 检查 | chat_completions |
| **GMI Cloud** | 多模型直 API | chat_completions |
| **Azure AI Foundry** | 自动检测（`hermes_cli/azure_detect.py`） | chat_completions |
| **MiniMax OAuth** | PKCE device-code（OpenClaw 移植） | chat_completions |
| **Tencent Tokenhub** | — | chat_completions |
| **HuggingFace Inference** | — | chat_completions |

所有上述都以 `plugins/model-providers/<name>/` 的形式存在；可被 `$HERMES_HOME/plugins/model-providers/<name>/` 用户插件覆盖。

---


## 概述

> **注意**：本页涵盖**多个模块**的协作，而非仅 `agent/smart_model_routing.py`。`smart_model_routing.py` 本身只是一个约 195 行的轻量启发式模块，负责 cheap/strong 消息路由（决定用便宜模型还是强模型处理当前消息）。本页讨论的更广泛的模型基础设施——元数据解析、上下文长度探测、模型切换管道——分布在下列四个核心模块中。

Smart Model Routing 是 Hermes Agent 的**模型元数据解析与上下文长度自动检测**系统，由四个核心模块组成：

| 模块 | 源码（v0.12.0 实测） | 职责 |
|---|---|---|
| **model_metadata.py** | ~1827行 | 上下文长度检测、端点探测、token 估算 |
| **models_dev.py** | 25KB/781行 | models.dev 4000+ 模型数据库集成 |
| **model_switch.py** | 32KB/927行 | 模型切换管道（别名解析 → 凭证 → 元数据） |
| **model_normalize.py** | 外部模块 | 各提供商模型名称规范化 |

> **v0.12.0（2026-05-05）变更**：新 `providers/` 包成为 provider 元数据**单一来源**。`agent/model_metadata.py::_URL_TO_PROVIDER` 反向映射、`hermes_cli/models.py::CANONICAL_PROVIDERS`、`hermes_cli/auth.PROVIDER_REGISTRY`、`hermes_cli/doctor.py /models 健康检查`、`hermes_cli/runtime_provider.py` URL fallback 全部改从 `providers.list_providers()` / `get_provider_profile().get_hostname()` 喂养。29 个 bundled `plugins/model-providers/<name>/` 目录共注册 33 个 `ProviderProfile`（gemini/kimi-coding/opencode-zen 各 2 个，minimax 3 个，含 minimax_oauth）。`model_switch.py` 的 picker 也通过新 `list_picker_providers()`（`60235db`）按已配凭证过滤。详见 [[provider-transport-architecture]] 与 changelog `2026-05-05-update`。

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

### Nous Portal 作为模型元数据权威源（#24502）

对于 Nous Portal 模型，`_resolve_nous_context_length()` 现在以 **Portal 的 `/v1/models` 实时响应为权威源**（`source == "portal"`），而非先走 OpenRouter 缓存目录：

```python
def _resolve_nous_context_length(model, base_url, api_key):
    """
    1. Portal /v1/models 实时响应 → 权威（source="portal"）
       例如 qwen3.6-plus，Portal 正确给出 262144
    2. Portal 未列出该模型时，才回退 OpenRouter 目录（带后缀/版本匹配）
    """
```

关键行为：
- **只有 Portal 派生的值才会持久化到磁盘缓存**（`source == "portal"` 时才写盘）。缓存 OR-fallback 值会在首次 Portal 失败时把错误数字"冻结"进去。
- Nous Portal 模型会**绕过持久化缓存**直接查 Portal（内存中 300s 端点元数据缓存保证开销可控），Portal 不可达时不触碰磁盘文件。
- 配套 #24509「union paid recs from nous portal with static list」：付费推荐模型列表由 Nous Portal 与静态列表取并集（`hermes_cli/models.py`）。

### Nous Portal 统一客户端标签（#24779）

每个 Hermes 发往 Nous Portal 的请求现在都带同一个 `client=hermes-client-v<__version__>` 标签（如本版本 `client=hermes-client-v0.13.0`），值实时取自 `hermes_cli.__version__`，发布脚本的 regex bump 在每次发版自动对齐。逻辑集中在 `agent/portal_tags.py`，接线到全部四个调用点（含 `NousProfile.build_extra_body`，覆盖主 agent 循环每次 chat completion）。

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

> **注**：自 v2026.5+ provider 身份/auth/endpoint/quirks 全部声明在 `ProviderProfile`（`providers/base.py` ABC）+ `plugins/model-providers/<name>/__init__.py` 插件中。前缀解析仍走本节逻辑，但元数据查询如 `default_aux_model` / `fallback_models` / `aliases` / `hostname` → provider 反向映射 都从 profile 读取。详见 [[provider-transport-architecture]]。

```python
# agent/model_metadata.py — provider 前缀 + 常见别名（节选）
_PROVIDER_PREFIXES = frozenset({
    "openrouter", "nous", "openai-codex", "anthropic", "alibaba",
    "google", "glm", "kimi", "deepseek", "qwen", "novita", "xai-oauth", ...
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

### MiniMax OAuth

`minimax-oauth` 一等公民 provider，使用 OAuth 浏览器登录（Coding Plan，minimax.io）。`hermes_cli/providers.py` 中以 `auth_type="oauth_external"`、`transport="anthropic_messages"` 注册，base URL `https://api.minimax.io/anthropic`。picker 中显示为 “MiniMax (OAuth)”。辅助客户端把它归入 `_ANTHROPIC_COMPAT_PROVIDERS`（与 `minimax`、`minimax-cn` 并列），默认模型 `MiniMax-M2.7-highspeed`。

### xAI Grok OAuth（SuperGrok Subscription）

新增 `xai-oauth` 一等公民 provider（commit `b62c997`），让 SuperGrok 订阅用户用 xAI 的 OAuth 登录驱动 agent：

- `hermes_cli/providers.py` 以 `transport="codex_responses"`、`auth_type="oauth_external"` 注册，base URL `https://api.x.ai/v1`（`XAI_BASE_URL` 可覆盖）
- 别名：`grok-oauth` / `x-ai-oauth` / `xai-grok-oauth` → `xai-oauth`
- xAI 的 `/v1/responses` 端点说 OpenAI Responses API，因此走 `ResponsesApiTransport` / `CodexAuxiliaryClient`
- loopback PKCE 授权流（`hermes_cli/auth.py` 大幅扩展）
- 与 `xai`（直连 API key，Grok 模型）并存，互为独立 provider

### NovitaAI（commit `c76e879`）

新增 `novita` provider，以聚合器（`is_aggregator=True`）形式注册（90+ 模型，pay-per-use；AI-native cloud：Model API、Agent Sandbox、GPU Cloud）：

- `hermes_cli/providers.py` overlay：`transport="openai_chat"`，`base_url_env_var="NOVITA_BASE_URL"`
- 默认 base URL `https://api.novita.ai/openai/v1`
- 别名 `novita-ai` / `novitaai` → `novita`
- Live pricing：`_fetch_novita_pricing()` 从 `/v1/models` 取每百万 token 的 input/output 价格（与 openrouter、nous、ai-gateway 并列支持实时定价）
- 作为插件式 provider，源码在 `plugins/model-providers/novita/`

### Qwen Cloud（原 Alibaba Cloud 重命名，#24835）

provider **slug 仍为 `alibaba`**（config.yaml、`--provider` flag、env var `DASHSCOPE_BASE_URL` 不变），只是 picker 中的**显示名从 “Alibaba Cloud” 改为 “Qwen Cloud”**，描述更新为 “Qwen Cloud / DashScope Coding（Qwen + multi-provider）”，并在 picker 中重新排序。别名 `qwen` / `dashscope` / `aliyun` / `alibaba-cloud` 仍解析到 `alibaba`。`alibaba-coding-plan` 为同平台的独立 provider。

### NVIDIA NIM 计费来源 header（commit `13c3d4b`）

`nvidia` provider 对云端 NIM（`integrate.api.nvidia.com`）流量附加计费归属 header `X-BILLING-INVOKE-ORIGIN: HermesAgent`（`agent/auxiliary_client.py` 中的 `build_nvidia_nim_headers()`）。该 header **按 host 门控**——只对云端 NIM 端点发送，本地/on-prem NIM（经 `NVIDIA_BASE_URL` 自定义）不附加。主对话路径（`run_agent.py`）与辅助客户端路径均已接线。

### Step Plan（v2026.4.18+）

StepFun 首款 API-key provider（Step Plan），支持国际和中国区设置。从 `/step_plan/v1/models` 动态发现模型，离线有编码向 fallback 目录。

### Vercel AI Gateway（v2026.4.18+）

新增 `ai-gateway` provider（别名 `vercel-ai-gateway`），通过 Vercel AI Gateway 统一访问多家模型：
- 定制模型列表（`VERCEL_AI_GATEWAY_MODELS` in `hermes_cli/models.py`，OSS first，Kimi K2.5 推荐默认）
- Live pricing 翻译（Vercel input/output → prompt/completion 格式）
- 自动把免费 Moonshot 模型顶到 picker 首位
- 提供商 picker 排序优先级提升
- 使用 Vercel 的 deep-link 创建 API key

### NovitaAI 与 xAI Grok OAuth（新增 provider）

`CANONICAL_PROVIDERS`（`hermes_cli/models.py:925+`）新增两个 provider：

- `novita` — **NovitaAI**（AI-native cloud：Model API、Agent Sandbox、GPU Cloud）。支持 live pricing（`_fetch_novita_pricing`），并在 `model_metadata.py:1552` 有专门的上下文长度分支——当 `provider == "novita"` 或 base_url 命中 `api.novita.ai` 时走端点探测。
- `xai-oauth` — **xAI Grok OAuth (SuperGrok Subscription)**，通过 xAI 订阅 OAuth 接入 Grok 模型。

此外，`alibaba` slug 的展示标签从 "Alibaba Cloud" 重命名为 **"Qwen Cloud"**（Qwen Cloud / DashScope Coding），`dashscope` / `aliyun` / `qwen` / `alibaba-cloud` 等别名仍解析到 `alibaba`。

### OpenRouter 工具支持过滤（v2026.4.18+）

hermes-agent 是工具调用优先的 agent，只有支持 `tools` 的模型才能驱动 agent 循环。`fetch_openrouter_models()` 现在过滤掉 `supported_parameters` 明确不含 `tools` 的模型（如纯图像、completion-only）。

宽容模式：`supported_parameters` 缺失时默认允许（Nous Portal、私有镜像、旧 snapshot 可能不填）。只隐藏明确声明了但不含 `tools` 的模型。

### 新 Provider（v0.12.0，2026-04-30）

| Provider | 说明 | 验证 |
|----------|------|------|
| **GMI Cloud** | 一级 API-key provider，对标 Arcee/Kilocode/Xiaomi | `agent/model_metadata.py:54,374`、`agent/auxiliary_client.py:146-147` |
| **Azure AI Foundry** | 自动检测 + 全链路 | `agent/anthropic_adapter.py:545` |
| **LM Studio** | 从 custom-endpoint alias 升级为原生 provider：专属 auth、`hermes doctor` 检查、reasoning transport、live `/models` 列表 | `agent/lmstudio_reasoning.py`、`run_agent.py:568,597` |
| **Tencent Tokenhub** | 新 provider | `agent/model_metadata.py:55`、`agent/auxiliary_client.py:158-160` |

### 远程模型目录清单（v0.12.0+）

OpenRouter + Nous Portal 改为**远端 manifest 拉取**，新模型上线不再需要发版。

### ProviderProfile ABC + 插件化 model-providers（v0.13.0+）

`providers/base.py:39` 定义 `ProviderProfile` ABC，`plugins/model-providers/` 收纳 20+ provider 作为可拔插件。第三方 provider 无需改 core 即可接入。

### 新 Provider（v0.14.0，2026-05-16）

| Provider | 说明 | 验证 |
|----------|------|------|
| **xAI Grok SuperGrok OAuth** | 订阅者直接登 xAI 账户使用 Grok；无需 API key/独立计费；带 SSH-to-tunnel 远程 OAuth 文档 | `hermes_cli/auth.py:201` `xAI Grok OAuth (SuperGrok Subscription)` |
| **`grok-4.3` 上下文窗口 1M** | 配合 SuperGrok OAuth 启用 1,000,000 token 窗口 | `agent/model_metadata.py:217` |
| **NovitaAI** | 开源模型托管（Llama/Qwen/DeepSeek） | `agent/model_metadata.py`（"novita-ai"、"api.novita.ai"） |
| **Codex app-server runtime** | drive OpenAI Codex CLI 的可选 runtime：session 复用、wedged-session retire、OAuth refresh 分类 | `agent/codex_runtime.py` + `agent/codex_responses_adapter.py` |
| **Alibaba Cloud → Qwen Cloud rename** | UI 改名匹配业界叫法，旧 config key 仍生效 | `agent/model_metadata.py`、`agent/agent_runtime_helpers.py` |

### `hermes proxy` —— OpenAI-compatible 本地代理（v0.14.0+）

`hermes_cli/proxy/cli.py:30,78,102`（`cmd_proxy_start / cmd_proxy_status / cmd_proxy_list_providers`）+ `hermes_cli/proxy/server.py` + `hermes_cli/proxy/adapters/xai.py:31`：

跑 `hermes proxy` 起 `http://localhost:port` 端点，**OpenAI API 兼容**，背后是任意 OAuth provider（Claude Pro / ChatGPT Pro / SuperGrok）。**Codex CLI / Aider / Cline / Continue 直接复用你的订阅**。

### OpenRouter Pareto Code Router + `min_coding_score`（v0.14.0+）

`cli.py` 解析配置、`agent/chat_completion_helpers.py` 路由发出、`tests/providers/test_provider_profiles.py:106` 验证：

OpenRouter Pareto router 自动挑"满足质量底线最便宜的模型"。`min_coding_score` 把这个阈值专门用于 coding 任务，**少花顶级模型的钱**。

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

## 新增 Provider（2026-05）

### xAI Grok OAuth

新增 provider id `xai-oauth`，显示名 "xAI Grok OAuth (SuperGrok Subscription)"。通过 issuer `https://auth.x.ai` 进行 OAuth 认证，采用 PKCE loopback 回调 `127.0.0.1:56121/callback`。别名：`grok-oauth`、`x-ai-oauth`、`xai-grok-oauth`。与基于 API Key 的 `xai` provider 相互独立（`hermes_cli/auth.py:115-133,199-203`）。SuperGrok / X Premium+ 订阅者凭订阅直接调用 Grok 模型。

### Azure Foundry — Microsoft Entra ID 认证

新增 `agent/azure_identity_adapter.py`，提供 Azure Foundry 的**无密钥（keyless）认证**。通过 `azure-identity` SDK 的 `DefaultAzureCredential` 链获取 token，由 `model.auth_mode = entra_id` 激活。`build_token_provider()` 返回一个零参数 callable，OpenAI SDK 每次请求时调用它（透明刷新），不会把 JWT 持久化到 `auth.json`。scope 默认使用 Microsoft 文档化的 Foundry 推理 audience，可通过 `model.entra.scope` 覆盖。`azure-identity` 只在选用 `entra_id` 时才惰性导入。

### NVIDIA NIM 计费来源头

`build_nvidia_nim_headers()`（`agent/auxiliary_client.py:380-384`）为 `integrate.api.nvidia.com` 流量附加云端归因头（`X-BILLING-INVOKE-ORIGIN: HermesAgent`），用于 NVIDIA NIM 调用的计费来源标记。

## `config.yaml` `model.provider` 为单一 source of truth（2026-05-23，`e42fcc5`，#31222）

`gateway/run.py:_resolve_runtime_agent_kwargs`：移除从 `HERMES_INFERENCE_PROVIDER` env 读取 provider 的早期分支。

**之前**：`HERMES_INFERENCE_PROVIDER` env 可静默覆盖 `config.yaml model.provider`，从 gateway 路径切入时甚至完全 bypass config.yaml —— 行为漂移源。

**之后**：gateway 走 `resolve_runtime_provider()` 单一入口（无 `requested` override），`config.yaml model.provider` 为唯一权威。Policy：**"如果不是 secret 就进 config.yaml"** —— env 仅保存凭据，行为配置进 yaml。

文档同步更新 `website/docs/reference/environment-variables.md`、`website/docs/reference/cli-commands.md`、`website/docs/guides/minimax-oauth.md`、`website/docs/guides/xai-grok-oauth.md` 等 11 处。

## 与其他系统的关系

- [[provider-transport-architecture]] — ProviderProfile 驱动 transport 单路径
- [[context-compressor-architecture]] — 使用 get_model_context_length() 确定上下文限制
- [[prompt-caching-optimization]] — 缓存成本信息来自 models.dev，1h 前缀缓存策略与 model routing 紧密耦合
- [[auxiliary-client-architecture]] — 辅助模型通过 models.dev 解析上下文长度
- [[provider-transport-architecture]] — provider 插件返回的 api_mode 决定走哪个 transport

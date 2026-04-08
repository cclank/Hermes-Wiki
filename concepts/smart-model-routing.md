---
title: Smart Model Routing 智能模型路由
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, model-routing, performance, caching, anthropic]
sources: [agent/model_metadata.py, agent/models_dev.py, hermes_cli/model_switch.py, hermes_cli/model_normalize.py]
---

# Smart Model Routing — 智能模型路由

## 概述

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
    5. models.dev 注册表（提供商感知）
    6. OpenRouter 实时 API 元数据
    7. Nous 后缀匹配（通过 OpenRouter 缓存）
    8. 硬编码默认值（模糊匹配，最长 key 优先）
    9. 本地服务器最后尝试
    10. 默认回退: 128K
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
| 上下文长度 | 静态字典 | 10 级解析链 |
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

## 与其他系统的关系

- [[context-compressor-architecture]] — 使用 get_model_context_length() 确定上下文限制
- [[prompt-caching-optimization]] — 缓存成本信息来自 models.dev
- [[auxiliary-client-architecture]] — 辅助模型通过 models.dev 解析上下文长度

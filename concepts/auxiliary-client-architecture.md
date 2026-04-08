---
title: Auxiliary Client 辅助客户端架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, agent, tool]
sources: [agent/auxiliary_client.py]
---

# Auxiliary Client — 辅助客户端架构

## 概述

Auxiliary Client 位于 `agent/auxiliary_client.py`（85KB/2127行），是 Hermes Agent 的**辅助 LLM 客户端路由器**。它为所有非主对话的 LLM 任务（上下文压缩、会话搜索摘要、视觉分析、Web 提取、技能快照生成等）提供统一的提供商解析和调用接口。

核心理念：**所有辅助任务共享同一个提供商解析链，避免每个消费者重复实现 fallback 逻辑。**

## 架构原理

### 设计目标

辅助任务与主对话不同：
- **成本敏感**：不需要用最贵的模型，快速廉价即可
- **可靠性要求高**：不能因为一个 provider 欠费就整个功能不可用
- **多模态需求**：部分任务需要视觉能力
- **异步支持**：Web 提取等任务需要 async

Auxiliary Client 通过**多层 provider 解析 + 自动降级 + 客户端缓存**解决这些问题。

### 提供商解析链（Text 任务）

```
优先级（auto 模式）:
  1. 主提供商（如果不是聚合器）→ 直接用主模型凭证
  2. OpenRouter (OPENROUTER_API_KEY)
  3. Nous Portal (~/.hermes/auth.json 中的活跃提供商)
  4. 自定义端点 (config.yaml model.base_url + OPENAI_API_KEY)
  5. Codex OAuth (Responses API, gpt-5.2-codex)
  6. 原生 Anthropic
  7. 直接 API Key 提供商 (z.ai/GLM, Kimi/Moonshot, MiniMax 等)
  8. None → 功能不可用
```

**关键设计**：如果用户的主提供商是 Alibaba、DeepSeek、ZAI 等非聚合器，Auxiliary Client 会**直接使用主提供商的凭证**，无需额外配置 OpenRouter key。这大幅降低了使用门槛。

### 提供商解析链（Vision 任务）

```
  1. 主提供商（如果是支持的视觉后端）
  2. OpenRouter
  3. Nous Portal
  4. Codex OAuth (gpt-5.2-codex 支持 vision)
  5. 原生 Anthropic
  6. 自定义端点 (本地视觉模型: Qwen-VL, LLaVA, Pixtral)
  7. None
```

## 核心组件

### 1. 适配器层（Adapter Pattern）

Auxiliary Client 最大的架构亮点是**适配器模式**——让所有不同的 API 格式统一表现为 `client.chat.completions.create()` 接口。

#### Codex Responses API 适配器

```python
class _CodexCompletionsAdapter:
    """Drop-in shim: 接受 chat.completions.create() kwargs，
    路由到 Codex Responses streaming API"""

class CodexAuxiliaryClient:
    """OpenAI 客户端兼容包装器，通过 Codex Responses API 路由"""
```

**转换细节**：
- chat.completions 的 `content` 格式 → Responses API 的 `input` 格式
- `{"type": "text", "text": "..."}` → `{"type": "input_text", "text": "..."}`
- `{"type": "image_url", ...}` → `{"type": "input_image", ...}`
- 流式响应 → 收集 output items + text deltas → 重建 chat.completions 格式
- 支持工具调用（function_call）
- 当 `get_final_response()` 返回空时，从流事件回填

#### Anthropic Messages API 适配器

```python
class _AnthropicCompletionsAdapter:
    """OpenAI 客户端兼容包装器，基于原生 Anthropic 客户端"""
```

通过 `agent.anthropic_adapter` 中的 `build_anthropic_kwargs` 和 `normalize_anthropic_response` 实现双向转换。

#### 异步适配器

```python
class _AsyncCodexCompletionsAdapter:
    """通过 asyncio.to_thread() 包装同步适配器"""

class AsyncCodexAuxiliaryClient:
    """匹配 AsyncOpenAI.chat.completions.create() 的异步包装器"""
```

### 2. 中央路由器（resolve_provider_client）

```python
def resolve_provider_client(
    provider: str,          # "openrouter", "nous", "openai-codex", "auto"...
    model: str = None,      # 模型覆盖
    async_mode: bool = False,
    raw_codex: bool = False,
    explicit_base_url: str = None,
    explicit_api_key: str = None,
) -> Tuple[client, resolved_model]:
```

**单一入口点**：所有辅助消费者都应该通过此函数或公开辅助函数获取客户端，禁止临时查找认证环境变量。

### 3. 自动检测（_resolve_auto）

```python
def _resolve_auto():
    # Step 1: 非聚合器主提供商 → 直接用主模型
    main_provider = _read_main_provider()
    if main_provider not in {"openrouter", "nous"}:
        client, resolved = resolve_provider_client(main_provider, main_model)
        if client: return client, resolved
    
    # Step 2: 聚合器/降级链
    for label, try_fn in _get_provider_chain():
        client, model = try_fn()
        if client: return client, model
```

**优越性**：先用主提供商（减少额外配置），再走降级链（确保可靠性）。

### 4. 任务级配置系统

```python
def _resolve_task_provider_model(task, provider, model, base_url, api_key):
    """
    优先级:
      1. 显式参数 (provider/model/base_url/api_key)
      2. 环境变量覆盖 (AUXILIARY_{TASK}_*, CONTEXT_{TASK}_*)
      3. 配置文件 (auxiliary.{task}.* 或 compression.*)
      4. "auto" (完整自动检测链)
    """
```

**灵活性**：每个任务可以独立配置 provider、model、base_url、api_key。

### 5. 客户端缓存与事件循环管理

```python
_client_cache: Dict[tuple, tuple] = {}
_client_cache_lock = threading.Lock()
```

**缓存策略**：
- Key: `(provider, async_mode, base_url, api_key, loop_id)`
- 异步客户端包含 **事件循环 ID**，防止跨循环复用导致死锁
- 检测到循环关闭时自动清理过期缓存

**事件循环安全防护**：
```python
def neuter_async_httpx_del():
    """禁用 AsyncHttpxClientWrapper.__del__ 的 aclose() 调度
    
    当 AsyncOpenAI 客户端被 GC 时，__del__ 会在 prompt_toolkit 的事件
    循环上调度 aclose()，但底层 TCP transport 绑定在另一个循环上，
    导致 RuntimeError("Event loop is closed")
    """
    AsyncHttpxClientWrapper.__del__ = lambda self: None

def cleanup_stale_async_clients():
    """每轮 agent 循环后清理过期的异步客户端"""
    
def shutdown_cached_clients():
    """CLI 关闭前清理所有缓存客户端"""
```

这是 Hermes Agent 解决 **prompt_toolkit + async OpenAI SDK** 兼容性问题的关键代码。

### 6. 支付/配额耗尽自动降级

```python
def _is_payment_error(exc: Exception) -> bool:
    """检测 HTTP 402 和余额不足错误"""
    if status_code == 402: return True
    if "credits" in err or "insufficient funds" in err: return True
    if "can only afford" in err or "billing" in err: return True

def _try_payment_fallback(failed_provider, task):
    """跳过失败的提供商，尝试链中下一个可用提供商"""
```

**工作流程**：
1. 调用 LLM API
2. 如果遇到 max_tokens 参数错误 → 重试用 max_completion_tokens
3. 如果遇到支付错误（402/余额不足） → 自动切换到下一个可用 provider
4. 记录日志通知用户降级

### 7. 公开 API

| 函数 | 用途 |
|---|---|
| `get_text_auxiliary_client(task)` | 获取文本任务的同步客户端 |
| `get_async_text_auxiliary_client(task)` | 获取文本任务的异步客户端 |
| `get_vision_auxiliary_client()` | 获取视觉任务的同步客户端 |
| `get_async_vision_auxiliary_client()` | 获取视觉任务的异步客户端 |
| `call_llm(task, messages, ...)` | 中央同步 LLM 调用入口 |
| `async_call_llm(task, messages, ...)` | 中央异步 LLM 调用入口 |
| `extract_content_or_reasoning(response)` | 提取响应内容，支持 reasoning 模型 |
| `get_available_vision_backends()` | 获取当前可用的视觉后端列表 |
| `get_auxiliary_extra_body()` | 获取 provider 特定的 extra_body |
| `auxiliary_max_tokens_param(value)` | 返回正确的 max tokens 参数名 |

## 设计优越性

### 对比分散式方案

| 维度 | 分散方案（每个消费者独立实现） | Auxiliary Client（集中式） |
|---|---|---|
| 认证逻辑 | 每个文件各自读 env/config | 一处解析，处处使用 |
| Fallback | 每个消费者各自实现 | 统一的降级链 |
| 支付降级 | 通常缺失 | 自动检测 + 切换 |
| 客户端缓存 | 重复创建连接 | 共享缓存，减少开销 |
| 事件循环安全 | 容易遗漏 | 统一管理 |
| 新 provider 接入 | 需要改 N 个文件 | 只需加一个 try_* 函数 |

### 适配器模式的优越性

- **调用者零感知**：context_compressor、web_tools、session_search 都只调用 `client.chat.completions.create()`，不需要知道底层是 Chat Completions、Responses API 还是 Messages API
- **可测试性**：每个适配器可独立测试
- **可扩展性**：新 API 格式只需增加一个适配器类

## 配置与操作

### config.yaml 配置

```yaml
auxiliary:
  compression:
    provider: auto        # 或 openrouter, nous, custom
    model: gemini-3-flash
    timeout: 30
  vision:
    provider: auto
    model: claude-sonnet-4-5-20250514
  web_extract:
    provider: openrouter
    model: google/gemini-3-flash-preview
    api_key: sk-xxx
    base_url: https://custom-endpoint.com/v1
```

### 环境变量覆盖

```bash
# 为特定任务设置 provider
export AUXILIARY_VISION_PROVIDER=anthropic
export AUXILIARY_COMPRESSION_MODEL=claude-haiku-4-5
export AUXILIARY_WEB_EXTRACT_BASE_URL=https://my-endpoint/v1
export AUXILIARY_WEB_EXTRACT_API_KEY=sk-xxx
```

### 查看可用视觉后端

```python
from agent.auxiliary_client import get_available_vision_backends
print(get_available_vision_backends())
# 输出: ['openrouter', 'nous', 'anthropic'] (取决于配置)
```

## 与其他系统的关系

- [[context-compressor-architecture]] — 使用 get_text_auxiliary_client("compression")
- [[tool-registry-architecture]] — web_tools 和 browser_tool 通过 registry 注册
- [[credential-pool-and-isolation]] — 使用 load_pool() 获取凭证
- [[prompt-builder-architecture]] — 辅助客户端不参与主对话提示构建
- [[model-tools-dispatch]] — model_tools.py 通过 auxiliary_client 处理侧边任务

---
title: Provider Transport 架构
created: 2026-04-18
updated: 2026-05-06
type: concept
tags: [architecture, module, provider, transport, api-dispatch, plugin]
sources: [agent/transports/base.py, agent/transports/anthropic.py, agent/transports/chat_completions.py, agent/transports/bedrock.py, agent/transports/codex.py, agent/transports/types.py, agent/transports/__init__.py, providers/base.py, providers/__init__.py, plugins/model-providers/, run_agent.py]
---

# Provider Transport — API 路径统一抽象

## 概述

Provider Transport 是 **v2026.4.17+** 引入的架构级重构，用统一的 ABC 抽象了所有 provider 的 API 数据路径（Anthropic Messages、OpenAI Chat Completions、OpenAI Responses API、AWS Bedrock）。位于 `agent/transports/`（v0.12.0 实测 1495 行），替代了之前散落在 `run_agent.py` 各处的 `if api_mode == "anthropic_messages": ... elif ...` 分支判断。

**核心理念**：**一个 provider 的消息转换、工具转换、参数构建、响应规范化，应该聚合在一个类里，而不是散落在调用点。**

> **2026-05 二阶重构**：`providers/` 模块（`ProviderProfile` ABC）补全了"哪个 provider"那一半。Transport 管 `api_mode`（数据路径），Provider Profile 管 provider 身份/auth/endpoint/quirks/aux defaults，**两者正交**。33 个 provider profile 全部以 `plugins/model-providers/<name>/` 形式发布。详见下方"Provider Profile 插件系统"。

## 架构原理

### 四个抽象方法 + 三个可选钩子

```python
# agent/transports/base.py
class ProviderTransport(ABC):
    @property
    @abstractmethod
    def api_mode(self) -> str:
        """处理的 api_mode 字符串（如 'anthropic_messages'）"""

    @abstractmethod
    def convert_messages(self, messages, **kwargs) -> Any:
        """OpenAI 格式消息 → provider 原生格式"""

    @abstractmethod
    def convert_tools(self, tools) -> Any:
        """OpenAI 工具定义 → provider 原生格式"""

    @abstractmethod
    def build_kwargs(self, model, messages, tools=None, **params) -> Dict:
        """组装完整的 API 调用 kwargs（通常内部调用前两个方法）"""

    @abstractmethod
    def normalize_response(self, response, **kwargs) -> NormalizedResponse:
        """原始响应 → 共享的 NormalizedResponse 类型（唯一返回 transport 层类型的方法）"""

    # ── 可选钩子 ───────────────────────────────────────────
    def validate_response(self, response) -> bool: ...       # 结构校验
    def extract_cache_stats(self, response) -> Optional[Dict]: ...  # cache hit/create 提取
    def map_finish_reason(self, raw_reason) -> str: ...      # stop reason 映射
```

**设计要点**：
- Transport **只负责数据路径**，不管 client 生命周期、streaming、auth、credential refresh、retry、interrupt handling——这些都在 `AIAgent` 上
- `normalize_response` 是唯一返回 transport 层类型（`NormalizedResponse`）的方法，其他方法返回 provider 原生结构

### 已实现的 Transport

| Transport | 文件 | 行数（v0.12.0） | api_mode | 覆盖 |
|-----------|------|------|----------|------|
| `AnthropicTransport` | `transports/anthropic.py` | 179 | `anthropic_messages` | Claude（直连、Nous Portal） |
| `ChatCompletionsTransport` | `transports/chat_completions.py` | 597 | `chat_completions`、`openai` 等 | OpenAI、OpenRouter、Gemini、xAI、custom OpenAI 兼容 |
| `ResponsesApiTransport` | `transports/codex.py` | 246 | `openai_responses` | OpenAI Codex、Responses API |
| `BedrockTransport` | `transports/bedrock.py` | 154 | `bedrock_converse` | AWS Bedrock（Converse API） |
| `NormalizedResponse` | `transports/types.py` | 162 | — | 共享响应类型 |
| 基类 + 注册表 | `transports/base.py` + `__init__.py` | 89 + 68 | — | ABC + `get_transport()` 惰性发现 |
| `ProviderProfile` ABC | `providers/base.py` | 171 | — | 声明式 provider 元数据 + 4 钩子 |
| Provider 注册表 | `providers/__init__.py` | ~200 | — | `register_provider()` / `get_provider_profile()` / `list_providers()` 惰性发现 |
| Bundled provider 插件 | `plugins/model-providers/<name>/` | 29 目录，33 profile | — | anthropic / openrouter / gemini / minimax / kimi-coding / xai / openai-codex / bedrock / 等 |

### 注册表：惰性发现

```python
# agent/transports/__init__.py
def get_transport(api_mode: str) -> ProviderTransport:
    """按需 import 对应的 transport 模块，触发模块级 register_transport() 调用"""
    ...

def register_transport(api_mode: str, transport_cls: type) -> None:
    """transport 模块在 import 时调用，把自己注册到 registry"""
    ...
```

首次 `get_transport("anthropic_messages")` 调用时才 import `transports/anthropic.py`——**延迟到实际使用**，启动不会因为 import 一堆 SDK 而变慢。

## 在 run_agent.py 中的接入点

`AnthropicTransport`、`ChatCompletionsTransport`、`BedrockTransport`、`ResponsesApiTransport` 替代了 `run_agent.py` 中 **20+ 个直接调用 provider 适配器函数的位置**：

| 场景 | 新方法 |
|------|--------|
| 主 kwargs 构建（按 api_mode 派发） | `transport.build_kwargs(...)` |
| 记忆 flush（build_kwargs + normalize） | `_tflush.build_kwargs` / `_tfn.normalize_response` |
| 迭代上限摘要 + 重试 | `_tsum.build_kwargs` / `_tsum.normalize_response` |
| 响应结构校验 | `transport.validate_response` |
| finish reason 映射（Anthropic stop_reason → OpenAI） | `transport.map_finish_reason` |
| 截断响应的规范化 | `transport.normalize_response` |
| cache 命中/创建统计提取 | `transport.extract_cache_stats` |
| 主 normalize loop | `transport.normalize_response` |

所有 transport 方法调用路径下的 adapter import 完全收敛到 transport 类内部，`run_agent.py` 本身不再直接 import `anthropic_adapter` 等函数。

**零直接 adapter imports 残留**（指 transport 方法的调用路径）。

辅助客户端（`agent/auxiliary_client.py`）也迁移到 transport（compression、memory flush、session summarization 路径）。

## 设计优越性

### 对比旧架构

| 维度 | 旧方案 | Transport ABC |
|------|--------|---------------|
| 分支代码 | `run_agent.py` 散落 `if api_mode == ...` 判断 | 单点 `get_transport(api_mode)` |
| 添加新 provider | 改多处（转换、normalize、cache stats...） | 新增一个 transport 子类 |
| 测试 | 难以单独测消息/工具转换 | 每个方法可独立单元测 |
| 循环依赖 | 容易 | 零——transport 只 import `base` / `types` |
| 启动开销 | 可能 eager import 所有 SDK | 惰性 import，按需加载 |

### 单一职责

- **Transport**：消息/工具格式转换 + 响应规范化
- **AIAgent**：client 生命周期、streaming、auth、retry、interrupt
- **Adapter**（旧代码）：保留，transport 内部委托给它，逐步废弃

### 迁移状态

| Provider | Transport 覆盖 | 状态 |
|----------|---------------|------|
| Anthropic | AnthropicTransport（委托 `anthropic_adapter.py`） | 全路径完成 |
| Chat Completions（OpenAI 兼容） | ChatCompletionsTransport | 全路径完成 |
| OpenAI Responses API（Codex） | ResponsesApiTransport | 全路径完成 |
| AWS Bedrock | BedrockTransport | 全路径完成 |
| Auxiliary Client（压缩/记忆） | 已迁移到 Transport | 完成 |

## Provider Profile 插件系统（v2026.5+）

### 关注点拆分

| 维度 | Transport | Provider Profile |
|------|-----------|------------------|
| 抽象 | API **数据路径**（消息/工具/响应转换） | Provider **身份与配置**（auth/endpoint/quirks/aux defaults） |
| 数量 | 4 个（Anthropic / Chat Completions / Responses / Bedrock） | 33 个（每个真实 provider 一个） |
| 复用 | 多个 provider 共享同一 transport | 每个 provider 一个 profile，独立 |
| 位置 | `agent/transports/` | `providers/` + `plugins/model-providers/` |

### `ProviderProfile` 声明式 dataclass

```python
# providers/base.py
@dataclass
class ProviderProfile:
    name: str                              # 'openrouter'
    api_mode: str = "chat_completions"     # 决定用哪个 Transport
    aliases: tuple = ()                    # ('claude', 'claude-oauth')
    display_name: str = ""                 # 'GMI Cloud'
    description: str = ""                  # picker subtitle
    signup_url: str = ""

    # auth + endpoints
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""                   # default {base_url}/models
    auth_type: str = "api_key"             # api_key|oauth_device_code|oauth_external|copilot|aws_sdk

    fallback_models: tuple = ()
    hostname: str = ""                     # for URL → provider reverse mapping

    default_headers: dict = field(default_factory=dict)
    fixed_temperature: Any = None          # OMIT_TEMPERATURE 哨兵 = 不发送
    default_max_tokens: int | None = None
    default_aux_model: str = ""            # cheap aux 模型

    # 子类可覆盖 hooks：
    def fetch_models(self, *, api_key, timeout) -> list[str] | None: ...
    def prepare_messages(self, messages) -> list[dict]: ...
    def build_extra_body(self, *, session_id, **context) -> dict: ...
```

### 插件发现链（`providers/__init__.py:_discover_providers()`）

```
1. <repo>/plugins/model-providers/<name>/__init__.py    # bundled
2. $HERMES_HOME/plugins/model-providers/<name>/         # user (last-writer-wins)
3. providers/<name>.py                                  # legacy 单文件兼容
```

每个 `__init__.py` 调用 `register_provider(profile)` 即注册；用户 plugin **覆盖同名 bundled**——任何人 monkey-patch 或替换内置 profile 不必改 repo 源码。

### 33 个 Profile 在 28 个目录下

| 多 profile 目录 | 包含 profiles |
|---|---|
| `gemini/` | gemini + 1 其他 |
| `kimi-coding/` | kimi-coding + kimi |
| `opencode-zen/` | opencode-go + opencode-zen |
| `minimax/` | minimax + minimax-oauth + 1 其他 |

**24 个一目录一 profile**：anthropic、openrouter、bedrock、deepseek、xai、nous、nvidia、arcee、stepfun、ollama-cloud、azure-foundry、ai-gateway、alibaba、alibaba-coding-plan、copilot、copilot-acp、custom、gmi、huggingface、kilocode、openai-codex、qwen-oauth、xiaomi、zai。

### 实例：anthropic profile（plugins/model-providers/anthropic/__init__.py）

```python
from providers import register_provider
from providers.base import ProviderProfile

class AnthropicProfile(ProviderProfile):
    def fetch_models(self, *, api_key, timeout=8.0):
        # x-api-key header (not Bearer)
        ...

anthropic = AnthropicProfile(
    name="anthropic",
    aliases=("claude", "claude-oauth", "claude-code"),
    api_mode="anthropic_messages",
    env_vars=("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
    base_url="https://api.anthropic.com",
    auth_type="api_key",
    default_aux_model="claude-haiku-4-5-20251001",
)
```

`register_provider(anthropic)` 由 module-level 调用执行；`get_provider_profile("claude")` 经 alias 解析返回该 profile；`AIAgent` 读 `profile.api_mode` 选 transport，读其余字段构 client + 请求。

## 与其他系统的关系

- [[auxiliary-client-architecture]] — auxiliary_client 已迁移到 Transport
- [[smart-model-routing]] — transport 基于 api_mode 派发，provider profile 提供 fallback_models / aliases / hostname → provider 反向映射
- [[interrupt-and-fault-tolerance]] — 中断、retry 仍在 AIAgent 层，不属于 transport 职责
- [[prompt-caching-optimization]] — cache 统计通过 `extract_cache_stats` 钩子暴露

## 相关文件

- `agent/transports/base.py`（89 行） — `ProviderTransport` ABC
- `agent/transports/types.py`（142 行） — `NormalizedResponse` 共享类型
- `agent/transports/__init__.py`（51 行） — 注册表 + 惰性发现
- `agent/transports/anthropic.py`（177 行） — Anthropic Messages
- `agent/transports/chat_completions.py`（387 行） — Chat Completions
- `agent/transports/codex.py`（217 行） — OpenAI Responses API
- `agent/transports/bedrock.py`（154 行） — AWS Bedrock Converse
- `providers/base.py`（165 行） — `ProviderProfile` ABC
- `providers/__init__.py`（191 行） — Plugin 发现 + register_provider/get_provider_profile/list_providers
- `plugins/model-providers/<name>/__init__.py` × 28 — 各 provider 的声明式 profile
- `run_agent.py` — 10+ 接入点
- `agent/auxiliary_client.py` — 辅助路径已迁移

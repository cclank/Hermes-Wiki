---
title: Provider Transport 架构
created: 2026-04-18
updated: 2026-05-20
type: concept
tags: [architecture, module, provider, transport, api-dispatch, provider-profile]
sources: [agent/transports/base.py, agent/transports/, providers/base.py, providers/__init__.py, plugins/model-providers/]
---

# Provider Transport — API 路径统一抽象

## 概述

Provider Transport 是 **v2026.4.17+** 引入的架构级重构，用统一的 ABC 抽象了所有 provider 的 API 数据路径（Anthropic Messages、OpenAI Chat Completions、OpenAI Responses API、AWS Bedrock）。位于 `agent/transports/`，替代了之前散落在 `run_agent.py` 各处的 `if api_mode == "anthropic_messages": ... elif ...` 分支判断。

到 v0.14.0（HEAD 2026-05-19），这个架构已与**第二层抽象 `ProviderProfile`** 配合：transport 负责*协议路径*（按 `api_mode` 分四类），`ProviderProfile` 负责*单个 provider 的声明式配置与 quirk*。~33 个 provider 全部下沉为 `plugins/model-providers/<name>/` 下的可插拔插件。

**核心理念**：
- **Transport**：一个 provider 的消息转换、工具转换、参数构建、响应规范化，应该聚合在一个类里，而不是散落在调用点。
- **ProviderProfile**：一个 provider 的 auth、端点、客户端 quirk、请求 quirk，应该声明在一个数据类里，而不是把 20+ 个 boolean flag 传进 transport。

> **2026-05 二阶重构**：`providers/` 模块（`ProviderProfile` ABC）补全了"哪个 provider"那一半。Transport 管 `api_mode`（数据路径），Provider Profile 管 provider 身份/auth/endpoint/quirks/aux defaults，**两者正交**。33 个 provider profile 全部以 `plugins/model-providers/<name>/` 形式发布。详见下方"Provider Profile 插件系统"。

> **v0.13.0 起搭档新组件**：[[provider-plugin-system]] —— `providers/base.py:39 ProviderProfile` ABC + `plugins/model-providers/` 29 个内置插件。**Transport 拿数据路径，Profile 拿 provider 元信息**：transport 少而稳（4 个），profile 多且常新。

## HEAD 期 transport 注册表

`agent/transports/__init__.py:51-68` `_discover_transports()`：

```python
def _discover_transports() -> None:
    try: import agent.transports.anthropic       # api_mode == anthropic_messages
    except ImportError: pass
    try: import agent.transports.codex            # api_mode == codex_responses
    except ImportError: pass
    try: import agent.transports.chat_completions # api_mode == chat_completions (默认)
    except ImportError: pass
    try: import agent.transports.bedrock          # api_mode == bedrock_converse (v0.11.0 新增)
    except ImportError: pass
```

文件清单（HEAD，行数）：

```
anthropic.py            179   Anthropic Messages
chat_completions.py     629   OpenAI 风格（含大多数 provider）
bedrock.py              154   AWS Bedrock Converse（v0.11.0 #13814）
codex.py                283   OpenAI Responses + Codex
codex_app_server.py     399   Codex app-server（@kshitijk4poor）
codex_app_server_session.py 810
codex_event_projector.py 312
hermes_tools_mcp_server.py 233 MCP 出站
base.py                  89   ABC
types.py                162   NormalizedResponse / ToolCall / Usage
__init__.py              68   注册表 + 懒发现
```

`api_mode` 字符串是与 [[provider-plugin-system]] 的耦合点：

```python
profile = get_provider_profile("nvidia")         # ProviderProfile(api_mode="chat_completions", ...)
transport = get_transport(profile.api_mode)      # ChatCompletionsTransport()
```

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
| `AnthropicTransport` | `transports/anthropic.py` | 179 | `anthropic_messages` | Claude（直连、OAuth、Nous Portal） |
| `ChatCompletionsTransport` | `transports/chat_completions.py` | 614 | `chat_completions` | ~16 个 OpenAI 兼容 provider（OpenRouter、Nous、Gemini、DeepSeek、NVIDIA、Qwen、Ollama、Kimi、Novita、Azure Foundry 等） |
| `ResponsesApiTransport` | `transports/codex.py` | 283 | `codex_responses` | OpenAI Codex、xAI Grok（Responses API） |
| `BedrockTransport` | `transports/bedrock.py` | 154 | `bedrock_converse` | AWS Bedrock（Converse API） |
| `NormalizedResponse` 等 | `transports/types.py` | 162 | — | 共享响应类型（`NormalizedResponse`、`ToolCall`、`Usage`） |
| 基类 + 注册表 | `transports/base.py` + `__init__.py` | 89 + 68 | — | ABC + `get_transport()` 惰性发现 |

> 注意：实际 `api_mode` 字符串是 `anthropic_messages`、`chat_completions`、`codex_responses`、`bedrock_converse`（见各 transport 文件末尾的 `register_transport(...)` 调用）。

### Codex App Server 运行时（可选）

除上述四个数据路径 transport 外，`agent/transports/` 还有一组 **Codex App Server** 文件——一个 *runtime*（非 transport ABC 子类），当用户的活跃 provider 是本地 `codex` CLI 安装时启用：

| 文件 | 行数 | 职责 |
|------|------|------|
| `transports/codex_app_server.py` | 399 | `CodexAppServerClient`——驱动 `codex app-server` 子进程 |
| `transports/codex_app_server_session.py` | 810 | `CodexAppServerSession`——每个 `AIAgent` 一个会话，跨 turn 复用 |
| `transports/codex_event_projector.py` | 312 | 把 codex 事件投影回 Hermes 的 messages 列表 |
| `transports/hermes_tools_mcp_server.py` | 233 | 把 Hermes 工具暴露给 codex 子进程的 MCP server |
| `agent/codex_runtime.py` | 448 | `run_codex_app_server_turn` / `run_codex_stream` / `run_codex_create_stream_fallback`——从 `AIAgent` 抽出的 Codex 运行时函数 |

`codex_runtime.py` 的每个函数以 `agent`（父 `AIAgent`）为首参，`AIAgent` 保留薄转发方法做向后兼容。`run_codex_app_server_turn` 在 `agent.api_mode == "codex_app_server"` 时由 `run_conversation()` 调用，返回与 chat_completions 路径相同形状的 dict。

### 注册表：惰性发现

```python
# agent/transports/__init__.py
def get_transport(api_mode: str):
    """按需 import 对应的 transport 模块，触发模块级 register_transport() 调用。
    未注册时返回 None——调用点可检查 None 并回退到 legacy 路径。"""
    ...

def register_transport(api_mode: str, transport_cls: type) -> None:
    """transport 模块在 import 时调用，把自己注册到 registry"""
    ...
```

首次 `get_transport("anthropic_messages")` 调用时才 import `transports/anthropic.py`——**延迟到实际使用**，启动不会因为 import 一堆 SDK 而变慢。`get_transport()` 在 miss 时会再跑一次 `_discover_transports()`，避免测试或乱序 import 导致 registry 只被部分填充。`_discover_transports()` 对每个 transport 模块的 import 用 `try/except ImportError` 包裹——某个 provider SDK 没装时不影响其他 transport。

## ProviderProfile — 第二层抽象（可插拔 provider）

Transport 按 `api_mode` 分四类，但同一个 `api_mode` 下不同 provider 仍有大量差异（max_tokens 默认值、reasoning 配置位置、temperature 处理、extra_body 字段、模型目录端点……）。v0.14.0 把这些差异收敛到 **`ProviderProfile`** 数据类，并把 ~33 个 provider 全部下沉为插件。

### ProviderProfile ABC

```python
# providers/base.py
@dataclass
class ProviderProfile:
    # 身份
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()
    # 人类可读元数据
    display_name: str = ""
    description: str = ""
    signup_url: str = ""
    # auth 与端点
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""        # 显式 models 端点，缺省回退 {base_url}/models
    auth_type: str = "api_key"  # api_key|oauth_device_code|oauth_external|copilot|aws_sdk
    supports_health_check: bool = True
    # 模型目录
    fallback_models: tuple = ()
    hostname: str = ""
    # 客户端 / 请求 quirk
    default_headers: dict = field(default_factory=dict)
    fixed_temperature: Any = None        # OMIT_TEMPERATURE 哨兵 = 不发送
    default_max_tokens: int | None = None
    default_aux_model: str = ""          # 辅助任务用的廉价模型

    # ── 可覆盖钩子（复杂 provider 在子类里 override）──
    def get_hostname(self) -> str: ...
    def prepare_messages(self, messages) -> list: ...
    def build_extra_body(self, *, session_id=None, **ctx) -> dict: ...
    def build_api_kwargs_extras(self, *, reasoning_config=None, **ctx) -> tuple[dict, dict]: ...
    def fetch_models(self, *, api_key=None, timeout=8.0) -> list[str] | None: ...
```

`ProviderProfile` 是**声明式**的——它描述 provider 行为，不拥有 client 构建、credential rotation、streaming（这些仍在 `AIAgent`）。`fetch_models` 默认实现走 `{models_url or base_url}/models` 加 Bearer auth，并带 `hermes-cli/<ver>` UA（绕过某些 provider 的 WAF）；复杂 provider 在子类里 override：

- **`AnthropicProfile`** — 用 `x-api-key` + `anthropic-version` 头，而非 Bearer
- **`OpenRouterProfile`** — 公共目录（无需 auth）+ `_CACHE`；`build_extra_body` 注入 provider preferences 与 Pareto Code router；`build_api_kwargs_extras` 把 `reasoning_config` 整包塞进 `extra_body.reasoning`，并为经 OpenRouter 路由的 Grok 模型附 `x-grok-conv-id` 头
- **Gemini** — `thinking_config` 翻译

### 插件布局与注册表

```
plugins/model-providers/
├── README.md
├── openrouter/
│   ├── __init__.py      # import 时调用 register_provider(profile)
│   └── plugin.yaml      # 清单: name, kind: model-provider, version, description
├── anthropic/ ...
└── ...                  # 共 29 个 bundled 插件目录
```

`providers/__init__.py` 是注册表，提供 `register_provider()`、`get_provider_profile()`、`list_providers()`。发现是**惰性**的——首次调用 `get_provider_profile()` / `list_providers()` 时执行 `_discover_providers()`，按三步顺序：

1. **Bundled 插件** — `<repo>/plugins/model-providers/<name>/`（仓库自带，29 个目录）
2. **用户插件** — `$HERMES_HOME/plugins/model-providers/<name>/`（按 `register_provider()` 的 last-writer-wins，可覆盖任意 bundled profile）
3. **Legacy 单文件** — `providers/<name>.py`（向后兼容，via `pkgutil.iter_modules`）

每个插件目录的 `__init__.py` 在 import 时调用 `register_provider(profile)` 自注册。每个 `_import_plugin_dir()` 用 `try/except` 包裹——单个插件加载失败只 warn，不影响其他。

### 各层从 registry 自动接线

加新 provider 只需在 `plugins/model-providers/` 下放一个目录，无需改其他代码——以下各层都从 registry 读取：

| 层 | 用途 |
|----|------|
| `hermes_cli/auth.py` | 用每个 api-key profile 扩展 `PROVIDER_REGISTRY` |
| `hermes_cli/models.py` | 扩展 `CANONICAL_PROVIDERS`，在 `provider_model_ids()` 里调 `profile.fetch_models()` |
| `hermes_cli/doctor.py` | 为每个 `auth_type="api_key"` profile 加 `/models` 健康检查 |
| `hermes_cli/config.py` | 把每个 `env_var` 注入 `OPTIONAL_ENV_VARS` |
| `hermes_cli/runtime_provider.py` | URL 检测失败时回退读 `profile.api_mode` |
| `agent/model_metadata.py` | `profile.get_hostname()` 做 hostname→provider 反查 |
| `agent/auxiliary_client.py` | 优先读 `profile.default_aux_model` |
| `transports/chat_completions.py::_build_kwargs_from_profile()` | 每次调用都跑 `prepare_messages` / `build_extra_body` / `build_api_kwargs_extras` |
| `run_agent.py` | 传 `provider_profile=<ProviderProfile>`，transport 走 profile 路径而非 legacy flag 路径 |

### 2026-04-29 后新增的 provider

| Provider | 插件目录 | 要点 |
|----------|---------|------|
| xAI Grok | `xai/`（`api_mode=codex_responses`） | Grok 经 xAI Responses API；SuperGrok 订阅的 OAuth 在 credential 层处理（`auth.json` 的 `providers.xai-oauth`、`agent/credential_sources.py` 的 loopback PKCE），不是 profile |
| NovitaAI | `novita/` | OpenAI 兼容，`base_url=https://api.novita.ai/openai/v1` |
| Azure Foundry | `azure-foundry/` | OpenAI 兼容端点（每资源 base_url 由用户提供）；可选 Microsoft Entra ID 无密钥认证——见 `agent/azure_identity_adapter.py`，`auth_mode=entra_id` 时用 `azure-identity` 的 `DefaultAzureCredential` 链，惰性 import |
| NVIDIA NIM | `nvidia/` | `base_url=https://integrate.api.nvidia.com/v1`，`default_max_tokens=16384`；命中 NVIDIA Cloud base_url 时 `_apply_client_headers_for_base_url()` 附加 billing origin 头 |

此外，`hermes_cli/proxy/`（`__init__.py` / `cli.py` / `server.py` / `adapters/`）是一个**本地 OpenAI 兼容代理**：监听 `127.0.0.1:<port>`，丢弃客户端的 `Authorization` 头，把用户已登录的 OAuth provider 凭证附到转发请求上（凭证临近过期时自动刷新），让外部 app 借用用户的订阅。首个 first-class adapter 是 `nous`（Nous Portal）。

## Codex App-Server 运行时（可选 opt-in，#24182）

除上述四个标准 transport，Hermes 还提供一个**可选的替代运行时**：把 OpenAI/Codex 模型的每个回合交给一个 `codex app-server` 子进程处理，而非走 Hermes 自己的工具派发循环。**默认行为不变。**

| 模块 | 文件 | 行数 | 职责 |
|------|------|------|------|
| App-Server 客户端 | `transports/codex_app_server.py` | 368 | stdio 上的 newline-delimited JSON-RPC 2.0 speaker：spawn `codex app-server`、init 握手、请求/响应、通知队列、服务端发起的请求队列（审批往返）、可中断阻塞读 |
| 会话适配器 | `transports/codex_app_server_session.py` | 810 | `CodexAppServerSession`——每个 `AIAgent` 实例一个惰性会话 |
| 事件投影器 | `transports/codex_event_projector.py` | 312 | 把 codex 的 `item/*` 通知转回 Hermes 标准 `{role, content, tool_calls, tool_call_id}` 消息形状，使记忆/技能 review 仍可工作 |

启用方式：
- `_VALID_API_MODES` 新增 `codex_app_server`（`hermes_cli/runtime_provider.py`）
- `_maybe_apply_codex_app_server_runtime()` 在 `_resolve_runtime_from_pool_entry()` 末尾调用——**仅当** config.yaml 中 `model.openai_runtime: codex_app_server` **且** provider 属于 `{openai, openai-codex}` 时才把 api_mode 改写为 `codex_app_server`。其他 provider（anthropic、openrouter 等）不会被重路由
- `AIAgent.run_conversation()` 在 `self.api_mode == "codex_app_server"` 时调用 `_run_codex_app_server_turn()`，委托给 `CodexAppServerSession`

注意 `codex_app_server` 并非通过标准 `register_transport()` 注册的 transport——它是一条独立的运行时路径，由 `AIAgent` 直接分支，与四个标准 transport 平级但走子进程协议。

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

### codex app-server 运行时路径

除基于 transport 的同步数据路径外，还新增了一条独立的运行时路径：当 `agent.api_mode == "codex_app_server"` 时，`run_conversation()` 不再走 transport 的 `build_kwargs` / `normalize_response`，而是调用 `agent/codex_runtime.py:28` 的 `run_codex_app_server_turn()`，由它驱动一个 `codex app-server` 子进程完成整轮对话。该路径通过 `CodexAppServerSession`（`transports/codex_app_server_session.py`）管理会话，并用 `codex_event_projector.py` 把 app-server 事件投影回 Hermes 内部事件流。

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

| api_mode | Transport / Runtime | 状态 |
|----------|---------------------|------|
| `anthropic_messages` | AnthropicTransport（委托 `anthropic_adapter.py`） | 全路径完成 |
| `chat_completions` | ChatCompletionsTransport（profile 路径 + legacy flag 路径） | 全路径完成 |
| `codex_responses` | ResponsesApiTransport（委托 `codex_responses_adapter.py`） | 全路径完成 |
| `bedrock_converse` | BedrockTransport | 全路径完成 |
| `codex_app_server` | `codex_runtime.py` + `CodexAppServerSession`（可选子进程运行时） | 完成 |
| Provider 声明 | `ProviderProfile` 插件（29 个 bundled，~33 个 provider） | 完成 |
| Auxiliary Client（压缩/记忆） | 已迁移到 Transport | 完成 |

## ProviderProfile ABC —— Provider 完全插件化（v0.13.0+）

ProviderTransport 抽掉了**数据路径**；v0.13.0 进一步抽出了**Provider 元数据 + 集成生命周期**，让任何人能把第三方 provider 当**插件**接入，无需改 core。

`providers/base.py:39` 定义 `ProviderProfile` ABC；`plugins/model-providers/` 收纳 **20+ provider 子目录**作为可拔插件（每个含 `plugin.yaml` + 注册函数）。

```
providers/
├── base.py          # ProviderProfile ABC (line 39)
└── __init__.py      # 注册入口

plugins/
└── model-providers/
    ├── arcee/
    ├── azure-foundry/
    ├── gmi-cloud/
    ├── lm-studio/
    ├── minimax-oauth/
    ├── novita-ai/        # v0.14.0
    ├── tencent-tokenhub/
    └── ...
```

Provider 元数据（auth 方式、`hermes doctor` 检查项、模型发现 endpoint、定价 manifest 等）从 core 代码中迁出，模型目录现在是**纯数据 + 插件**驱动。

## 与其他系统的关系

- [[auxiliary-client-architecture]] — auxiliary_client 已迁移到 Transport
- [[smart-model-routing]] — transport 基于 api_mode 派发，与模型路由配合；ProviderProfile 提供模型元数据
- [[interrupt-and-fault-tolerance]] — 中断、retry 仍在 AIAgent 层，不属于 transport 职责
- [[prompt-caching-optimization]] — cache 统计通过 `extract_cache_stats` 钩子暴露

## 相关文件

- `providers/base.py`（184 行） — `ProviderProfile` 数据类 + `OMIT_TEMPERATURE` 哨兵
- `providers/__init__.py`（191 行） — provider 注册表 + 惰性插件发现
- `plugins/model-providers/<name>/` — 29 个 bundled provider 插件（`__init__.py` + `plugin.yaml`）
- `agent/transports/base.py`（89 行） — `ProviderTransport` ABC
- `agent/transports/types.py`（162 行） — `NormalizedResponse` 共享类型
- `agent/transports/__init__.py`（68 行） — transport 注册表 + 惰性发现
- `agent/transports/anthropic.py`（179 行） — Anthropic Messages
- `agent/transports/chat_completions.py`（614 行） — Chat Completions
- `agent/transports/codex.py`（283 行） — OpenAI Responses API
- `agent/transports/bedrock.py`（154 行） — AWS Bedrock Converse
- `agent/transports/codex_app_server*.py` — Codex App Server 子进程运行时
- `agent/codex_runtime.py`（448 行） — Codex 运行时函数（app-server / Responses 流式）
- `agent/azure_identity_adapter.py` — Azure Foundry 的 Microsoft Entra ID 适配器
- `hermes_cli/proxy/` — 本地 OpenAI 兼容代理（OAuth provider）
- `run_agent.py` — 10+ 接入点

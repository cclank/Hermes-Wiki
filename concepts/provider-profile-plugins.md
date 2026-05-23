---
title: Provider Profile —— 推理 Provider 插件化
created: 2026-05-14
updated: 2026-05-14
type: concept
tags: [provider, plugin, transport, abc, architecture, module]
sources: [providers/base.py, providers/__init__.py, plugins/model-providers/]
version: v0.13.0
---

# Provider Profile —— 推理 Provider 插件化

## 概述

v0.13.0 把"推理 Provider"从硬编码大表迁出成 plugin 插槽。所有 30 个 provider 都是 `plugins/model-providers/<name>/__init__.py` 下的一行声明，导入时调 `register_provider(profile)`。`AIAgent` / transport 层从 *声明* 里读取行为，而不再背 20 多个 bool flag。

> 设计要旨（`providers/base.py` 顶部）：**Provider profiles 是 DECLARATIVE** —— 它们描述 provider 的行为；**不**拥有 client 构造、凭证轮换、流式 —— 那些仍在 `AIAgent` 上。

## ABC：`ProviderProfile`

`providers/base.py:25`：

```python
@dataclass
class ProviderProfile:
    # ── Identity ─────────────────────────────────────────────
    name: str
    api_mode: str = "chat_completions"
    aliases: tuple = ()

    # ── Human-readable metadata ──────────────────────────────
    display_name: str = ""      # /model picker label
    description: str = ""       # picker subtitle
    signup_url: str = ""        # 引导用户注册时显示

    # ── Auth & endpoints ─────────────────────────────────────
    env_vars: tuple = ()
    base_url: str = ""
    models_url: str = ""        # 显式覆盖；缺省走 {base_url}/models
    auth_type: str = "api_key"  # api_key|oauth_device_code|oauth_external|copilot|aws_sdk
    supports_health_check: bool = True

    # ── Model catalog ─────────────────────────────────────────
    fallback_models: tuple = ()
    hostname: str = ""          # URL→provider 反查映射

    # ── Client-level quirks ──────────────────────────────────
    default_headers: dict[str, str] = field(default_factory=dict)

    # ── Request-level quirks ─────────────────────────────────
    fixed_temperature: Any = None           # 或 OMIT_TEMPERATURE 哨兵 (Kimi)
    default_max_tokens: int | None = None
    default_aux_model: str = ""             # 给辅助模型用的便宜 model
```

钩子方法（覆盖以处理复杂 provider）：

| 钩子 | 用途 |
|------|------|
| `prepare_messages(messages)` | 在 codex sanitize 之后、developer 角色 swap 之前的预处理 |
| `build_extra_body(*, session_id, **ctx)` | 给 API kwargs `extra_body` 加 provider-specific 字段（例：Nous 加 product tags） |
| `build_api_kwargs_extras(*, reasoning_config, **ctx)` → (extra_body, top_level) | reasoning 配置在 *哪个层级* 注入（OpenRouter: `extra_body.reasoning`；Kimi: `api_kwargs.reasoning_effort`） |
| `fetch_models(*, api_key, timeout)` | live model 列表，默认 `urllib` + Bearer，可覆盖 |
| `get_hostname()` | URL → provider 反向映射，缺省从 `base_url` 派生 |

## OMIT_TEMPERATURE 哨兵

`providers/base.py:21`：

```python
OMIT_TEMPERATURE = object()  # 哨兵：完全不发送 temperature 字段（例：Kimi 服务端自管）
```

`fixed_temperature = None` 表示 *使用 caller 默认*；`fixed_temperature = OMIT_TEMPERATURE` 表示 *根本不发*。

## 注册表（`providers/__init__.py`）

发现路径**两个**：

1. **Bundled plugins**：`plugins/model-providers/<name>/` —— 仓库自带
2. **User plugins**：`$HERMES_HOME/plugins/model-providers/<name>/` —— 用户安装

每个 plugin 目录：

- `__init__.py` —— 导入时调 `register_provider(profile)`
- `plugin.yaml` —— manifest (`name`、`kind: model-provider`、`version`、`description`)

**Discovery 懒加载**：第一次 `get_provider_profile()` / `list_providers()` 调用时扫描两个路径并导入。User plugin 同名时**覆盖** bundled（last-writer-wins）—— 第三方可以零侵入替换内置 profile。

**向后兼容**：`providers/*.py` 的单文件 profile 仍走 `pkgutil.iter_modules` 自动发现。新 profile 应**只**用 plugin 布局。

## 已迁移的 30 个 provider

```
ai-gateway, alibaba, alibaba-coding-plan, anthropic, arcee,
azure-foundry, bedrock, copilot, copilot-acp, custom, deepseek,
gemini, gmi, huggingface, kilocode, kimi-coding, minimax, nous,
novita, nvidia, ollama-cloud, openai-codex, opencode-zen, openrouter,
qwen-oauth, stepfun, xai, xiaomi, zai
```

每个目录有 `__init__.py` + `plugin.yaml`。

## 真实例子

### 简单：GMI Cloud（直接声明）

`plugins/model-providers/gmi/__init__.py`：

```python
from hermes_cli import __version__ as _HERMES_VERSION
from providers import register_provider
from providers.base import ProviderProfile

gmi = ProviderProfile(
    name="gmi",
    aliases=("gmi-cloud", "gmicloud"),
    display_name="GMI Cloud",
    description="GMI Cloud — multi-model direct API (slash-form model IDs)",
    signup_url="https://www.gmicloud.ai/",
    env_vars=("GMI_API_KEY", "GMI_BASE_URL"),
    base_url="https://api.gmi-serving.com/v1",
    auth_type="api_key",
    default_headers={"User-Agent": f"HermesAgent/{_HERMES_VERSION}"},
    default_aux_model="google/gemini-3.1-flash-lite-preview",
    fallback_models=(
        "zai-org/GLM-5.1-FP8",
        "deepseek-ai/DeepSeek-V3.2",
        ...
    ),
)
register_provider(gmi)
```

### 复杂：Nous（继承 + 钩子覆盖）

`plugins/model-providers/nous/__init__.py`：

```python
class NousProfile(ProviderProfile):
    def build_extra_body(self, *, session_id=None, **ctx):
        return {"tags": nous_portal_tags()}

    def build_api_kwargs_extras(self, *, reasoning_config=None,
                                supports_reasoning=False, **ctx):
        # Nous: passes full reasoning_config, but OMITS when disabled
        extra_body = {}
        if supports_reasoning and reasoning_config is not None:
            rc = dict(reasoning_config)
            if rc.get("enabled") is False:
                ...
```

需要写自定义类继承 `ProviderProfile` —— 因为 `build_extra_body` 要随 session 注入 portal tags，`build_api_kwargs_extras` 要按 reasoning_config 状态条件性 omit 字段。

## API 模式 (`api_mode`)

四个值（决定 transport 路径）：

| `api_mode` | Transport | 例子 |
|------------|-----------|------|
| `chat_completions` | OpenAI-compat Chat Completions | 绝大多数 |
| `responses` | OpenAI Responses API | OpenAI / Codex |
| `anthropic` | Anthropic Messages | Anthropic 直连 |
| `aws_sdk` / Bedrock | AnthropicBedrock SDK + boto3 Converse | Bedrock |

详见 [[provider-transport-architecture]]。

## auth_type

五种 auth：

| `auth_type` | 流程 |
|-------------|------|
| `api_key` | `env_vars` 第一项作为 Bearer |
| `oauth_device_code` | PKCE device-code（MiniMax、Codex） |
| `oauth_external` | 已存的 OAuth token 文件（Copilot、Gemini Cloud Code） |
| `copilot` | GitHub Copilot 专用刷新流 |
| `aws_sdk` | boto3 凭证链（IAM / API key / 实例 profile） |

详见 [[credential-pool-and-isolation]]。

## 新接入的 provider

v0.12 / v0.13 在这套机制下落地：

| Provider | 来源 |
|----------|------|
| **GMI Cloud** | first-class（salvage #11955） |
| **Azure AI Foundry** | 自动检测（`hermes_cli/azure_detect.py`） |
| **MiniMax OAuth** | PKCE browser flow（salvage #15203） |
| **Tencent Tokenhub** | salvage #16860 |
| **Xiaomi MiMo** | reasoning_content echo-back providers |
| **Novita AI** | 90+ model pay-per-use |
| **LM Studio** | 升级为 first-class native provider，专属 auth + `hermes doctor` + reasoning transport + live `/models`（salvage #17061） |
| **Qwen Cloud** | 原 Alibaba Cloud 改名（`1e01b25e7`） |

## 远程 model catalog manifest

OpenRouter + Nous Portal 的 model catalog 从 *远程 manifest* 拉取（`#16033`），新模型无需发版就能在 `/model` picker 里出现。

## 相关页面

- [[provider-transport-architecture]] — `api_mode` 决定的 transport 选路
- [[auxiliary-client-architecture]] — auxiliary client 与同一 provider profile 表共用解析链
- [[credential-pool-and-isolation]] — 每个 `env_vars` 项可能对应一个凭证池
- [[smart-model-routing]] — `/model` picker / models.dev / 远程 catalog manifest
- [[mcp-and-plugins]] — `ctx.register_web_search_provider` / `register_image_gen_provider` 等同模式

## 相关文件

- `providers/base.py` — `ProviderProfile` ABC
- `providers/__init__.py` — registry + 懒加载发现
- `plugins/model-providers/*/` — 30 个 provider 实现
- `plugins/model-providers/README.md` — 第三方贡献指南

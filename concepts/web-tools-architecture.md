---
title: Web Tools 搜索/提取架构
created: 2026-04-08
updated: 2026-05-17
type: concept
tags: [tool, toolset, architecture, component]
sources: [tools/web_tools.py, agent/web_search_provider.py, agent/web_search_registry.py, plugins/web/]
---

> **v2026.5.7 增量**：
>
> - **Per-capability backend selection**（@kshitijk4poor, #20061）—— search / extract / browse 各自独立选 backend（如 SearXNG 搜索 + Firecrawl 抽取）。
> - **新搜索 backend**：
>   - **SearXNG**（@kshitijk4poor, #20823）原生 search-only backend，配合 `searxng-search` optional skill。
>   - **Brave Search**（free tier）（commit `04193cf`）。
>   - **DDGS**（DuckDuckGo Search）（commit `04193cf`）。
> - 源码确认：`tools/web_tools.py:129` backend 列表完整为 `parallel / firecrawl / tavily / exa / searxng / brave-free / ddgs`，`tools/web_tools.py:142` `("searxng", _has_env("SEARXNG_URL"))` 注释「Free-tier backends (searxng / brave-free / ddgs) trail the paid ones so」。

# Web Tools — 搜索/提取架构

## 概述

Web Tools 位于 `tools/web_tools.py`（~1551行），提供**多后端 Web 搜索/提取/爬取**能力。支持 7 种后端提供商，所有后端对 Agent 暴露相同的 `web_search`、`web_extract`、`web_crawl` 工具接口。

核心理念：**内容获取优先于浏览器自动化**——简单信息检索使用 web_search/web_extract（更快、更便宜），仅在需要交互时才使用 browser 工具。

> **v2026.5.x 重大重构**：所有搜索后端从 `tools/web_tools.py` 内联实现迁移为**插件**（`plugins/web/`）。旧的 `tools/web_providers/` 目录已删除。`web_tools.py` 现在只做工具壳层 + 安全 + LLM 压缩，后端解析全部通过 `agent/web_search_registry` 完成。详见下文「Provider 插件化」。

## 架构原理

### 七大后端

| 后端 | Search | Extract | Crawl | 认证 |
|---|---|---|---|---|
| **Firecrawl** | ✅ | ✅ | ✅ | API Key 或 Nous Gateway |
| **Exa** | ✅ | ✅ | ❌ | EXA_API_KEY |
| **Parallel** | ✅ | ✅ | ❌ | PARALLEL_API_KEY |
| **Tavily** | ✅ | ✅ | ✅ | TAVILY_API_KEY |
| **brave-free** | ✅ | ❌ | ❌ | 免费 |
| **ddgs** | ✅ | ❌ | ❌ | 免费 |
| **searxng** | ✅ | ❌ | ❌ | SearXNG 实例 URL |

所有后端均为 `plugins/web/` 下的插件。

### Provider 注册架构

新架构以 **`WebSearchProvider`** ABC（`agent/web_search_provider.py:63`）为核心。每个 provider 通过 `supports_search` / `supports_extract` / `supports_crawl` 能力标志声明自己支持的能力，多能力 provider（Firecrawl、Tavily、Exa）可从单个类同时通告多种能力。

provider 实现打包为 `plugins/web/` 下的插件（`plugin.yaml` 声明 `kind: backend` 与 `provides_web_providers:`），通过 `ctx.register_web_search_provider()` 注册到 `agent/web_search_registry.py`。旧的 `tools/web_providers/` 目录已被删除。

三个 web 工具不再直接通过 `_get_backend()`（该函数仍存在），而是经 `agent.web_search_registry` 的 `get_active_search_provider()` / `get_active_extract_provider()` / `get_active_crawl_provider()` 按能力路由。

新增了**按能力的配置 key**：`web.search_backend` / `web.extract_backend` / `web.crawl_backend`，可分别覆盖各能力使用的后端。

**ABC — `agent/web_search_provider.py`（221 行）**：`WebSearchProvider(abc.ABC)`

```python
def _get_backend():
    """解析优先级:
    1. config.yaml web.backend (显式指定)
    2. FIRECRAWL_API_KEY / FIRECRAWL_API_URL / tool-gateway
    3. PARALLEL_API_KEY
    4. TAVILY_API_KEY
    5. EXA_API_KEY
    6. 默认: firecrawl (向后兼容)
    """
```

注意是**按能力**分别解析——search/extract/crawl 可以落在不同 provider 上。

### 七个内置 Provider

`plugins/web/<name>/{plugin.yaml, __init__.py, provider.py}`，全部支持 search + extract：

| Provider | 类 | Crawl | Async extract |
|---|---|---|---|
| **firecrawl** | `FirecrawlWebSearchProvider` | ✅ | ✅ |
| **tavily** | `TavilyWebSearchProvider` | ✅ | ❌ |
| **parallel** | `ParallelWebSearchProvider` | ❌ | ✅ |
| **exa** | `ExaWebSearchProvider` | ❌ | ❌ |
| **searxng** | `SearXNGWebSearchProvider` | ❌ | ❌ |
| **brave_free** | `BraveFreeWebSearchProvider` | ❌ | ❌ |
| **ddgs** | `DDGSWebSearchProvider` | ❌ | ❌ |

用户可在 `~/.hermes/plugins/web/` 放同名插件覆盖内置实现。

### Firecrawl 双路径架构

Firecrawl 插件保留两种连接模式，由 `web.use_gateway` 配置控制（两套凭证都存在时选哪个）：

| 模式 | 路径 / 环境变量 | 适用对象 |
|---|---|---|
| **直接模式** | `FIRECRAWL_API_KEY` / `FIRECRAWL_API_URL` | 所有用户 |
| **托管 Gateway** | Nous 托管的 tool-gateway（`FIRECRAWL_GATEWAY_URL` / `TOOL_GATEWAY_*`） | Nous 订阅者 |

`plugins/web/firecrawl/provider.py`（773 行）的 `_get_firecrawl_client()` + `_is_tool_gateway_ready()` 实现该判定，客户端按配置缓存。**优越性**：Nous 订阅者无需单独购买 Firecrawl。

## 核心组件

`tools/web_tools.py` 中的三个工具入口现在都是**注册表查找 + 委派**——具体后端逻辑全部在 `plugins/web/<name>/provider.py` 中。

### 1. web_search_tool — 网络搜索

```python
def web_search_tool(query: str, limit: int = 5) -> str:
    # 通过 agent.web_search_registry 分发:
    #   backend = _get_search_backend()
    #   provider = get_provider(backend) 或 fallback get_active_search_provider()
    #   response = provider.search(query, limit)
```

所有 7 个 provider 的 `search()` 均为同步实现。返回统一格式：`{"success": true, "data": {"web": [{"title", "url", "description", "position"}]}}`。无 provider 时返回错误，提示运行 `hermes tools`。

### 2. web_extract_tool — URL 内容提取

```python
async def web_extract_tool(
    urls: List[str],
    format: str = "markdown",      # markdown 或 html
    use_llm_processing: bool = True,
    model: Optional[str] = None,
    min_length: int = 5000         # 触发 LLM 处理的最小长度
) -> str:
```

**核心流程**：
1. 安全检查（密钥注入 + SSRF + 网站策略）
2. 注册表解析活跃 extract provider，调用 `provider.extract(urls, **kwargs)`——分发器用 `inspect.iscoroutinefunction` 检测并按需 `await`（Parallel 的 SDK 原生异步，Exa/Tavily/Firecrawl 同步）
3. LLM 智能压缩（`process_content_with_llm`）
4. 输出裁剪（只保留 url/title/content/error）

provider 的 `extract()` 返回统一的 `[{"url", "title", "content", "raw_content", "metadata"?, "error"?}, ...]` 列表。

### 3. web_crawl_tool — 网站爬取

```python
async def web_crawl_tool(
    url: str,
    instructions: str = None,    # 提取指令（仅 Tavily 支持）
    depth: str = "basic",        # basic 或 advanced
    use_llm_processing: bool = True
) -> str:
```

仅 **firecrawl** 和 **tavily** 的 provider 声明 `supports_crawl()=True`。分发逻辑：
- 配置的后端支持 crawl → 通过注册表 `get_active_crawl_provider()` 调用 `provider.crawl()`（同步/异步均可）
- 配置的后端 search-only（brave-free/ddgs/searxng，连 extract 也不支持）→ 返回 typed "search-only" 错误
- provider 被配置但不可用（如缺 `FIRECRAWL_API_KEY`）→ 提前短路返回顶层错误信封

crawl provider 返回 `{"results": [{"url", "title", "content", ...}]}`，再交由共享的 LLM 摘要后处理。

## LLM 内容处理引擎

这是 Web Tools 最具创新性的部分——用 LLM 自动压缩网页内容。

### 处理策略

```python
def process_content_with_llm(content, url, title, model, min_length):
    """
    内容分级处理:
    < 5000 chars → 跳过处理，直接返回原始内容
    5000 ~ 500K chars → 单次 LLM 摘要
    500K ~ 2M chars → 分块处理 + 合成
    > 2M chars → 拒绝处理
    """
```

### 分块处理（Chunked Processing）

```python
async def _process_large_content_chunked(content, chunk_size=100K):
    # 1. 将内容切分为 100K chars 的块
    # 2. 并行摘要每个块 (asyncio.gather)
    # 3. 合成所有块摘要为统一摘要
    # 4. 硬性限制: 最终输出 ≤ 5000 chars
```

**设计亮点**：
- 每个块使用**专门的 prompt**（"这是大文档的一节，不要写引言和结论"）
- 并行处理所有块，不串行等待
- 合成步骤**去除冗余**并整合为连贯摘要
- 如果合成失败，**回退为拼接所有块摘要**

### 压缩率

典型压缩比：10-50x（原始内容 → LLM 摘要）

```
原始: 50,000 chars → 处理后: 2,000 chars (4%)
原始: 200,000 chars → 处理后: 4,500 chars (2.25%)
```

## 安全设计

### 四层防护

| 层级 | 保护 | 实现 |
|---|---|---|
| **URL 密钥注入** | 阻止 URL 中嵌入 API Key | `_PREFIX_RE` 检测 |
| **SSRF 防护** | 阻止访问私有地址 | `is_safe_url()` |
| **网站策略** | 黑名单域名拦截 | `check_website_access()` |
| **重定向检查** | 阻止重定向到内部地址 | 提取后检查 `sourceURL` |

### Base64 图片清理

```python
def clean_base64_images(text: str) -> str:
    """移除 base64 编码图片，替换为 [BASE64_IMAGE_REMOVED]"""
    # 防止大量 base64 数据挤占上下文窗口
```

## 标准化层

不同后端返回不同的数据格式。每个 provider 在其插件模块内部完成标准化，使所有后端对外暴露 ABC 中定义的统一响应形状。重构后这些 vendor helper 已从 `web_tools.py` 移入各插件，再由 `web_tools.py` 重新 import 以保持兼容：

```python
# plugins/web/firecrawl/provider.py
_extract_web_search_results(response)    # Firecrawl 多格式提取
_to_plain_object(value)                  # SDK 对象 → Python dict
_normalize_result_list(values)           # 混合 SDK/list → dict list

# plugins/web/tavily/provider.py
_normalize_tavily_search_results(raw)    # Tavily → 标准格式
_normalize_tavily_documents(raw)         # Tavily extract/crawl → 标准格式
```

`WebSearchProvider` ABC 把响应形状契约写进文档并逐位保留旧的 in-tree 契约，因此工具 wrapper 无需做任何翻译。

**优越性**：Agent 永远收到统一格式的数据，不需要根据后端类型做不同的解析。

## Debug 模式

```bash
export WEB_TOOLS_DEBUG=true
```

启用后自动记录：
- 所有工具调用及参数
- 原始 API 响应
- LLM 压缩指标（原始大小/处理后大小/压缩比）
- 最终处理结果

日志保存到：`~/.hermes/logs/web_tools_debug_UUID.json`

## 设计优越性

### 对比直接调用 API

| 维度 | 直接调用 API | Web Tools |
|---|---|---|
| 后端切换 | 需要改代码 | config.yaml 一键切换 |
| 内容压缩 | 手动处理 | 自动 LLM 摘要 |
| 大内容处理 | 容易超上下文 | 分块 + 合成 |
| 安全防护 | 需要自己实现 | SSRF + 注入 + 策略三层防护 |
| 格式统一 | 每个 API 格式不同 | 统一输出格式 |
| 调试 | 需要手动打印 | 内置 Debug 模式 |

### LLM 处理的优越性

没有 LLM 处理时，Agent 收到的是原始 HTML/markdown 全文（可能数十万字）。有了 LLM 处理后：
- **上下文节省**：压缩 10-50x
- **信息密度提升**：只保留关键事实和数据
- **格式统一**：所有页面都是结构化 Markdown 摘要
- **优雅降级**：LLM 失败时回退为截断原始内容

## 配置与操作

### 选择后端

```yaml
# config.yaml
web:
  backend: firecrawl          # 共享 fallback (firecrawl/parallel/tavily/exa/searxng/brave-free/ddgs)
  search_backend: searxng     # 可选: 仅 web_search 用此后端
  extract_backend: firecrawl  # 可选: 仅 web_extract 用此后端
  crawl_backend: tavily       # 可选: 仅 web_crawl 用此后端
```

per-capability 键允许搜索与提取使用不同后端（例如 SearXNG 搜索 + Firecrawl 提取）。

### 环境变量

```bash
# Firecrawl 直接模式
export FIRECRAWL_API_KEY=fc-xxx
export FIRECRAWL_API_URL=https://your-self-hosted.com  # 可选

# Exa
export EXA_API_KEY=exa-xxx

# Parallel
export PARALLEL_API_KEY=par-xxx

# Tavily
export TAVILY_API_KEY=tav-xxx

# SearXNG (自托管 metasearch)
export SEARXNG_URL=https://your-searxng-instance

# Brave Search (免费层, 2k 查询/月)
export BRAVE_SEARCH_API_KEY=brave-xxx

# ddgs (DuckDuckGo) — 无需 Key, 仅需安装包

# LLM 处理配置
export AUXILIARY_WEB_EXTRACT_MODEL=google/gemini-3-flash-preview
```

### 禁用 LLM 处理

```python
# 快速提取，不需要压缩
content = await web_extract_tool(["https://example.com"], use_llm_processing=False)
```

## 与其他系统的关系

- [[mcp-and-plugins]] — 七大 Web 后端均为 `kind: backend` 内置插件，通过 `ctx.register_web_search_provider()` facade 注册
- [[auxiliary-client-architecture]] — LLM 内容处理通过 `async_call_llm(task="web_extract")` 调用
- [[tool-registry-architecture]] — web_search/web_extract 通过 registry 注册
- [[browser-tool-architecture]] — 文档建议简单信息获取优先用 web_tools
- [[context-compressor-architecture]] — 类似的 LLM 压缩理念应用于不同场景

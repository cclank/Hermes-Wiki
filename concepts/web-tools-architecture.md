---
title: Web Tools 搜索/提取架构
created: 2026-04-08
updated: 2026-05-16
type: concept
tags: [tool, toolset, architecture, component, plugins]
sources: [tools/web_tools.py, agent/web_search_provider.py, agent/web_search_registry.py, plugins/web/]
---

# Web Tools — 搜索/提取架构

## 概述

Web Tools 位于 `tools/web_tools.py`（1551 行），提供**多后端 Web 搜索/提取/爬取**能力。所有后端对 Agent 暴露相同的 `web_search`、`web_extract`、`web_crawl` 工具接口。

核心理念：**内容获取优先于浏览器自动化**——简单信息检索使用 web_search/web_extract（更快、更便宜），仅在需要交互时才使用 browser 工具。

> **v2026.5.x 重大重构**：所有搜索后端从 `tools/web_tools.py` 内联实现迁移为**插件**（`plugins/web/`）。旧的 `tools/web_providers/` 目录已删除。`web_tools.py` 现在只做工具壳层 + 安全 + LLM 压缩，后端解析全部通过 `agent/web_search_registry` 完成。详见下文「Provider 插件化」。

## 架构原理

### Provider 插件化（v2026.5.x）

后端不再硬编码在 `web_tools.py`，而是实现统一 ABC，作为 `kind: backend` 插件自动加载。

**ABC — `agent/web_search_provider.py`（221 行）**：`WebSearchProvider(abc.ABC)`

| 成员 | 说明 |
|---|---|
| `name` / `display_name` | provider 标识 |
| `is_available()` | 凭证/依赖是否就绪 |
| `supports_search()` | 能力标志，默认 `True` |
| `supports_extract()` | 能力标志，默认 `False` |
| `supports_crawl()` | 能力标志，默认 `False` |
| `search(query, limit=5)` | 搜索；未覆盖则 `NotImplementedError` |
| `extract(urls, **kwargs)` | 提取；**可为 `async def`** |
| `crawl(url, **kwargs)` | 爬取；**可为 `async def`** |
| `get_setup_schema()` | 供 `hermes tools` picker 使用 |

`extract`/`crawl` 允许是协程，dispatcher 通过 `inspect.iscoroutinefunction` 检测并 await。响应格式与旧契约**逐字节保持一致**，工具壳层无需翻译。

**注册门面**：`ctx.register_web_search_provider()`（PluginContext），每个插件 `__init__.py` 提供 `register(ctx)`。

### Registry 与解析链 — `agent/web_search_registry.py`（262 行）

线程锁保护的 `_providers` 字典，提供 `register_provider()` / `list_providers()` / `get_provider()`，以及**按能力**解析的 `get_active_search_provider()` / `get_active_extract_provider()` / `get_active_crawl_provider()`。

`_resolve()` 优先级：

```text
1. 显式配置 web.{cap}_backend 或 web.backend —— 即使不可用也优先（精确报错）
2. 唯一一个「有该能力且可用」的 provider —— 直接走捷径
3. _LEGACY_PREFERENCE 顺序按 is_available() 过滤：
   firecrawl → parallel → tavily → exa → searxng → brave-free → ddgs
4. 否则 None
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

| 模式 | 路径 | 适用对象 |
|---|---|---|
| **直接模式** | `FIRECRAWL_API_KEY` / `FIRECRAWL_API_URL` | 所有用户 |
| **托管 Gateway** | Nous 托管的 tool-gateway（`FIRECRAWL_GATEWAY_URL` / `TOOL_GATEWAY_*`） | Nous 订阅者 |

`plugins/web/firecrawl/provider.py`（773 行）的 `_get_firecrawl_client()` + `_is_tool_gateway_ready()` 实现该判定，客户端按配置缓存。**优越性**：Nous 订阅者无需单独购买 Firecrawl。

## 核心组件

### 1. web_search_tool — 网络搜索

```python
def web_search_tool(query: str, limit: int = 5) -> str:
    """
    后端路由:
    - parallel → _parallel_search() [支持 agentic/fast/one-shot 模式]
    - exa → _exa_search() [支持 highlights 提取]
    - tavily → _tavily_request("search")
    - firecrawl → client.search()
    """
```

返回统一格式：`{"success": true, "data": {"web": [{"title", "url", "description", "position"}]}}`

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
2. 后端提取（Firecrawl scrape / Exa get_contents / Parallel extract / Tavily extract）
3. LLM 智能压缩（`process_content_with_llm`）
4. 输出裁剪（只保留 url/title/content/error）

### 3. web_crawl_tool — 网站爬取

```python
async def web_crawl_tool(
    url: str,
    instructions: str = None,    # 提取指令（仅 Tavily 支持）
    depth: str = "basic",        # basic 或 advanced
    use_llm_processing: bool = True
) -> str:
```

目前仅 Firecrawl 和 Tavily 支持 crawl。Parallel 无 crawl API。

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

不同后端返回不同的数据格式。Web Tools 通过**标准化函数**统一输出：

```python
_extract_web_search_results(response)    # Firecrawl 多格式提取
_normalize_tavily_search_results(raw)    # Tavily → 标准格式
_normalize_tavily_documents(raw)         # Tavily extract/crawl → 标准格式
_to_plain_object(value)                  # SDK 对象 → Python dict
_normalize_result_list(values)           # 混合 SDK/list → dict list
```

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
  backend: firecrawl  # 或 exa, parallel, tavily
```

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

# LLM 处理配置
export AUXILIARY_WEB_EXTRACT_MODEL=google/gemini-3-flash-preview
```

### 禁用 LLM 处理

```python
# 快速提取，不需要压缩
content = await web_extract_tool(["https://example.com"], use_llm_processing=False)
```

## 与其他系统的关系

- [[auxiliary-client-architecture]] — LLM 内容处理通过 `async_call_llm(task="web_extract")` 调用
- [[tool-registry-architecture]] — web_search/web_extract 通过 registry 注册
- [[browser-tool-architecture]] — 文档建议简单信息获取优先用 web_tools
- [[context-compressor-architecture]] — 类似的 LLM 压缩理念应用于不同场景

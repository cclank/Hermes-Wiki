---
title: Web Tools 搜索/提取架构
created: 2026-04-08
updated: 2026-05-14
type: concept
tags: [tool, toolset, architecture, component, plugin]
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

Web Tools 提供**多后端 Web 搜索/提取/爬取**能力。所有后端对 Agent 暴露相同的 `web_search`、`web_extract`、`web_crawl` 工具接口。

**v0.13.0 重大重构**：所有 web provider 从硬编码迁出成 *plugin*。`agent/web_search_provider.py` 提供 `WebSearchProvider` ABC（镜像 `image_gen` 模板，`2cea98e14`），`agent/web_search_registry.py` 是 registry（`007a630b1`）。tools 现在按 *capability*（search / extract / crawl）独立选 provider，不再强制单一后端。`tools/web_providers/` 旧目录已删（`39b4ebfce`）。

核心理念：**内容获取优先于浏览器自动化**——简单信息检索使用 web_search/web_extract（更快、更便宜），仅在需要交互时才使用 browser 工具。

> **2026-05 重构**：search 与 extract 拆为**按能力独立选择 backend**（`tools/web_providers/` ABC + `web.search_backend` / `web.extract_backend`），便于"SearXNG 搜索 + Firecrawl 提取"等组合。

## 架构原理

### Provider Plugin 目录（v0.13.0）

`plugins/web/` 下 7 个独立 plugin：

| Plugin | Search | Extract | Crawl | 来源 commit | 备注 |
|---|---|---|---|---|---|
| **brave_free** | ✅ | ❌ | ❌ | `d403cf018` | 首批迁移，无 API key 免费 |
| **ddgs** | ✅ | ❌ | ❌ | `5c7d098be` | DuckDuckGo Search |
| **searxng** | ✅ | ❌ | ❌ | `0d085d945` | 自托管 SearXNG 实例（v0.13.0 新增） |
| **parallel** | ❌ | ✅ async | ❌ | `481664610` | 首个 async-extract plugin |
| **exa** | ✅ | ✅ | ❌ | `ec8449e9c` | 首个 multi-capability migration |
| **tavily** | ✅ | ✅ | ✅ | `31fcde876` | 首个 three-capability plugin |
| **firecrawl** | ✅ | ✅ async | ✅ | `143184e94` + `21e3a863b` | 最大迁移，dual auth（直连 + Nous Gateway） |

`hermes tools` → Web 现在可以**按 capability 独立选 provider**（例：search 用 brave_free，extract 用 firecrawl，crawl 用 tavily），不再强制单一后端。

### 插件 API

`hermes_cli/plugins.py:574 register_web_search_provider()`（`f29f02a73`）—— 第三方可以 ship 自己的 plugin。Image gen / video gen 走完全相同的模式：

```python
def register(ctx):
    ctx.register_web_search_provider(MyProvider())
```

### 后端选择链（v0.13.0 后）

picker / 配置在 plugin registry 上做 `is_available()` 过滤（`0a7cbd334`，"filter resolution by `is_available()` in web + image_gen registries"），未配置 / 未安装的 provider 自动跳过。`_LEGACY_PREFERENCE` 仍保留对老 7-provider 默认顺序的兼容（`657e6d87c`）。

旧版选择链（保留以备参考）：

```python
def _get_backend():
    """解析优先级:
    1. config.yaml web.backend (显式: parallel/firecrawl/tavily/exa/searxng/brave-free/ddgs)
    2. 付费后端（按出现顺序）: PARALLEL_API_KEY → FIRECRAWL_* → TAVILY_API_KEY → EXA_API_KEY
    3. 免费后端（trail paid）: SEARXNG_URL → BRAVE_SEARCH_API_KEY → ddgs 包
    4. 默认: firecrawl (向后兼容)
    """
```

**免费后端在付费后端之后做 fallback**——只要有付费 key 就优先付费，没有付费才走免费。

### Per-capability backend 拆分（v0.13.0+）

`web` 工具现支持给 search / extract / browse **分别**配后端（PR #20061 / #20823 / #20841）：

```yaml
web:
  search_backend: "searxng"     # 免费 SearXNG 自托管
  extract_backend: "firecrawl"  # 仍用 Firecrawl 提取页面
  crawl_backend: "tavily"
```

适用场景：自有 SearXNG 实例做 search 省钱、extract / crawl 走专业服务。

### Firecrawl 双路径架构

Firecrawl 是默认后端，支持两种连接模式：

| 模式 | 路径 | 适用对象 |
|---|---|---|
| **直接模式** | `FIRECRAWL_API_KEY` / `FIRECRAWL_API_URL` | 所有用户 |
| **托管 Gateway** | Nous 托管的 tool-gateway | Nous 订阅者 |

```python
def _get_firecrawl_client():
    """优先级:
    1. 直接 Firecrawl 配置 (api_key + api_url)
    2. Nous 托管 Gateway (nous_user_token + gateway_origin)
    """
    # 客户端缓存 —— 配置不变时复用同一实例
    if _firecrawl_client is not None and _firecrawl_client_config == client_config:
        return _firecrawl_client
```

**优越性**：Nous 订阅者无需单独购买 Firecrawl，通过 tool-gateway 共享访问。

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

---
title: MCP 集成与插件系统
created: 2026-04-07
updated: 2026-05-18
type: concept
tags: [architecture, mcp, plugins, extensibility]
sources: [tools/mcp_tool.py, tools/mcp_oauth.py, tools/mcp_oauth_manager.py, hermes_cli/plugins.py]
---

> **v2026.5.7 MCP 升级**：
>
> - **SSE transport** 支持（salvage #19135，#21227）—— `tools/mcp_tool.py:34` `transport: sse` 配置；line 199-204 SSE client 加载逻辑；line 1301 `# SSE transport (for MCP servers that implement the SSE transport protocol`。
> - **OAuth auth forward** + 长 SSE `sse_read_timeout` 提升（#21323）。
> - **Stale-pipe retry**：transport 失败当作 session-expired 处理并重连（#21289）。
> - **Image tool result** 走 MEDIA tag 而不是丢弃（#21328）。
> - **Periodic keepalive** to `_wait_for_lifecycle_event`（#20209）—— 长周期 lifecycle 等待中保持连接。
> - **Fix #21204**：`mcp add --command` 独立 argparse dest —— 之前会 silent launch chat 而不是注册 server。
> - **Fix #21347**：utility stub 按 server 通告的 capability gate（避免暴露未声明能力）。
>
> **插件系统新增钩子**（v2026.5.7+）：
>
> - **`transform_llm_output`**（#21235）—— 在 LLM 输出进入对话前 reshape / 过滤。源码 `run_agent.py:14279`，名见 `hermes_cli/plugins.py:86`。
> - **`env_enablement_fn`** + **`cron_deliver_env_var`**（#21331）—— 平台插件统一钩子，IRC / Teams / Google Chat 都用。

# MCP 集成与插件系统

## 设计原理

Hermes 通过 **MCP（Model Context Protocol）** 和**插件系统**实现可扩展性，允许连接外部工具和自定义行为。

## MCP v0.13.0 升级

| 改进 | 说明 |
|------|------|
| **SSE transport + OAuth forwarding** | SSE transport 接入 OAuth header 转发（`#21227`） |
| **Stale-pipe retries** | 长连接 pipe 失活时自动重试（`#21323`） |
| **Image 结果 → MEDIA tag** | image result 不再被丢弃，转成 `MEDIA:` 标签供 gateway 抽取并原生投递（`#21289`） |
| **Long-lived lifecycle keepalive** | long-running tool 等待时 keepalive 防止连接 idle 断（`#21328`） |
| **Stop retrying initial auth failures** | 首次 auth 失败不无限重试（`1247ff2dc`，v0.13.0 post-release） |

## MCP 集成

```python
# tools/mcp_tool.py (~2176 行)

class MCPServerTask:
    """MCP 服务器任务"""
    
    def __init__(self, config: dict):
        self.servers = {}
        self.tools = {}
    
    async def connect_server(self, name: str, config: dict):
        """连接 MCP 服务器"""
        transport = config.get("transport", "stdio")
        
        if transport == "stdio":
            process = await asyncio.create_subprocess_exec(
                *config["command"],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            self.servers[name] = {
                "process": process,
                "transport": transport,
            }
        elif transport == "http":
            self.servers[name] = {
                "url": config["url"],
                "transport": transport,
            }
        elif transport == "sse":              # v0.13.0
            # mcp.client.sse.sse_client，SSE 协议的 MCP 服务器
            # 走 mcp_tool.py:201 from mcp.client.sse import sse_client
            self.servers[name] = {
                "url": config["url"],
                "transport": transport,
            }
        
        # 获取服务器工具
        tools = await self._list_tools(name)
        for tool in tools:
            self.tools[f"{name}:{tool['name']}"] = tool
    
    async def call_tool(self, tool_name: str, args: dict) -> dict:
        """调用 MCP 工具"""
        server_name, tool_name = tool_name.split(":", 1)
        server = self.servers[server_name]
        
        if server["transport"] == "stdio":
            return await self._call_stdio_tool(server, tool_name, args)
        elif server["transport"] == "http":
            return await self._call_http_tool(server, tool_name, args)
```

### 并行工具调用 opt-in

每个 MCP 服务器可配置 `supports_parallel_tool_calls` 标志（`tools/mcp_tool.py:3219`）。当设为 `true` 时，该服务器的工具在批量工具调用中**可参与并行执行**；opt-in 的服务器登记在 `_parallel_safe_servers` 集合中，由 `is_mcp_tool_parallel_safe()` 在并行安全检测时查询。默认为 `false`（保守串行）。详见 [[parallel-tool-execution]]。

### MCP OAuth 支持

```python
# tools/mcp_oauth.py

async def authenticate_mcp_server(server_config: dict) -> dict:
    """MCP 服务器 OAuth 认证"""
    auth_type = server_config.get("auth", {}).get("type")
    
    if auth_type == "oauth":
        # 实现 OAuth 流程
        auth_url = server_config["auth"]["url"]
        client_id = server_config["auth"]["client_id"]
        # ...
        return {"access_token": token, "expires_at": expires}
    
    elif auth_type == "api_key":
        return {"api_key": server_config["auth"]["api_key"]}
    
    return {}
```

### v0.13.0 MCP 升级

| 改进 | 影响 |
|---|---|
| **SSE Transport** | `transport: sse` 通过 `mcp.client.sse.sse_client` 走 Server-Sent Events 协议（`tools/mcp_tool.py:201`） |
| **OAuth 转发** | OAuth token 跨 child server 转发，多层 MCP 服务器统一鉴权 |
| **Stale-pipe retry** | 长跑 stdio MCP server 的连接掉了能自动重连 |
| **Image results → MEDIA tag** | MCP 工具返回 image 现在以 `<MEDIA>` 形式进 conversation（之前 silent drop） |
| **Keepalive on long-lived lifecycle waits** | 长 init / shutdown 不会被 idle timeout 杀掉 |
| **TOCTOU 修复** | `mcp_oauth.py` 关闭 check-then-use 窗口（v0.13.0 安全 wave，详见 [[security-defense-system]]） |

## 插件系统

```python
# hermes_cli/plugins.py

class Plugin:
    """插件基类"""
    
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    
    def on_load(self):
        """插件加载时调用"""
        pass
    
    def on_unload(self):
        """插件卸载时调用"""
        pass

# 钩子系统
_HOOKS = {
    "on_session_start": [],
    "pre_llm_call": [],
    "post_llm_call": [],
    "on_tool_call": [],
    "on_session_end": [],
}

def register_hook(hook_name: str, callback: callable):
    """注册钩子回调"""
    if hook_name in _HOOKS:
        _HOOKS[hook_name].append(callback)

def invoke_hook(hook_name: str, **kwargs) -> list:
    """调用钩子"""
    results = []
    for callback in _HOOKS.get(hook_name, []):
        try:
            result = callback(**kwargs)
            results.append(result)
        except Exception as e:
            logger.warning(f"Hook {hook_name} failed: {e}")
    return results
```

### 内存插件

```python
# plugins/memory/__init__.py

class MemoryPlugin(Plugin):
    """内存插件（Honcho 集成）"""
    
    name = "honcho-memory"
    
    def on_session_start(self, session_id: str, **kwargs):
        """会话开始时预热缓存"""
        self._warm_cache(session_id)
    
    def pre_llm_call(self, user_message: str, **kwargs):
        """LLM 调用前注入上下文"""
        context = self._fetch_context(user_message)
        return {"context": context}
    
    def on_session_end(self, messages: list, **kwargs):
        """会话结束时持久化"""
        self._persist_session(messages)
```

### PluginContext 扩展 facade

`PluginContext` 为插件提供了一组扩展 facade（`hermes_cli/plugins.py`）：

| Facade | 位置 | 用途 |
|---|---|---|
| `ctx.register_tool(..., override=True)` | plugins.py:328 | 传 `override=True` 可替换已有的内置工具 |
| `ctx.llm` | plugins.py:298 | property,返回 `agent.plugin_llm.PluginLlm`,供插件做 host 所有的 LLM 调用 |
| `ctx.register_web_search_provider()` | plugins.py:585 | 注册 web 搜索/提取/爬取 provider |
| `ctx.register_browser_provider()` | plugins.py:613 | 注册云端浏览器 provider |

## 插件 CLI

```bash
# 插件管理
hermes plugins list           # 列出已安装插件
hermes plugins install <name> # 安装插件
hermes plugins remove <name>  # 移除插件
hermes plugins update <name>  # 更新插件
```

## v0.12.0 内置插件清单

`/tmp/hermes-agent/plugins/` 目录新增/扩展：

| 插件 | 路径 | 说明 |
|------|------|------|
| `spotify` | `plugins/spotify/` | 7 个 native tool（play / search / queue / playlists / devices）+ PKCE OAuth + 交互式 setup 向导，可在 `hermes tools` 中切换 |
| `google_meet` | `plugins/google_meet/` | 加入会议、转录、说话、跟进；OpenAI realtime transport + Node bot server，全管道 bundled |
| `observability/langfuse` | `plugins/observability/langfuse/` | Langfuse observability bundled |
| `hermes-achievements` | `plugins/hermes-achievements/` | 扫描全部 session 历史输出"成就" |
| `kanban` | `plugins/kanban/` | 看板插件 + per-platform home-channel 通知 toggle（v0.12.0 #19864） |
| `image_gen` | `plugins/image_gen/` | 图像生成 |
| `context_engine` | `plugins/context_engine/` | Context Engine 插件化 |
| `memory` | `plugins/memory/` | Memory provider |
| `disk-cleanup` / `example-dashboard` / `strike-freedom-cockpit` | … | 例示/工具型插件 |

平台插件目录 `plugins/platforms/`：

- `irc/`：v2026.4.23 加入，参考实现
- `teams/`：v0.12.0 新增（**第 19 个消息平台**），通过 `register(ctx)` 调 `ctx.register_platform(...)` 注入，最大消息长度 28KB

### 新增 Hook 类型（v0.12.0）

- `pre_gateway_dispatch`（#15050）：插件可在 gateway 派发前拦截
- `pre_approval_request` / `post_approval_response`（#16776）：审批请求前后注入
- `post_tool_call` 增加 `duration_ms` 字段（#15429，灵感来自 Claude Code 2.1.119）

### 直接 URL 安装

- 技能：`hermes skills install <https://...>`（#16323）
- NixOS module：`extraPackages` + 声明式插件安装（@alt-glitch，#15953/#17047）

## 配置

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  filesystem:
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/root/work"]
      supports_parallel_tool_calls: true  # 该服务器的工具可并行执行
    github:
      command: ["npx", "-y", "@modelcontextprotocol/server-github"]
      env:
        GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"

plugins:
  enabled:
    - honcho-memory
    - custom-plugin
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | Claude Code |
|------|--------|--------|-------------|
| MCP 支持 | ✅ 完整 | ✅ | ✅ |
| MCP OAuth | ✅ | ❌ | ✅ |
| 插件系统 | ✅ 钩子系统 | ❌ | ❌ |
| 自定义工具 | ✅ 注册表 | ❌ | ❌ |
| 插件 CLI | ✅ | N/A | N/A |

## Bundled Plugins（v2026.4.30 现状）

`plugins/` 目录下打包了下列 plugin（按 `plugins.enabled` 显式开启）：

| 插件目录 | 类型 | 简介 |
|------|------|------|
| `plugins/spotify/` | standalone | **7 工具**：`spotify_playback / devices / queue / search / playlists / albums / library`，PKCE OAuth + 交互式 wizard（v2026.4.30+） |
| `plugins/google_meet/` | standalone | 加入 Google Meet 会议、转录、语音回应；OpenAI Realtime + Node bot server（v2026.4.30+） |
| `plugins/observability/langfuse/` | standalone | 全链路 tracing（salvage #16845，v2026.4.30+） |
| `plugins/hermes-achievements/` | standalone | 扫描 session 历史，颁发 "成就"（v2026.4.30+） |
| `plugins/disk-cleanup/` | standalone | 磁盘清理 reference 实现（opt-in by default，v0.11.0+） |
| `plugins/kanban/` | standalone | Kanban 协作板（v0.11.0；多 profile 协作版本 #16081 已 revert） |
| `plugins/memory/` | backend | Honcho memory provider 集成 |
| `plugins/image_gen/` | backend | 可插拔 image_gen 后端（OpenAI、`openai-codex` gpt-image-2 over Codex OAuth） |
| `plugins/context_engine/` | backend | Context engine 可插拔实现 |
| `plugins/example-dashboard/` | standalone | Dashboard plugin 参考实现 |
| `plugins/strike-freedom-cockpit/` | standalone | 第三方 dashboard 参考 |
| `plugins/platforms/irc/` | platform | IRC 平台适配器（参考实现，v2026.4.23+） |
| `plugins/platforms/teams/` | platform | Microsoft Teams 平台适配器（v2026.4.30+，第 19 个平台） |

### Spotify 插件（v2026.4.30+）

`plugins/spotify/__init__.py:46-52` 静态注册 7 个工具：

```python
_TOOLS = [
    ("spotify_playback",  SPOTIFY_PLAYBACK_SCHEMA,  _handle_spotify_playback,  "🎵"),
    ("spotify_devices",   SPOTIFY_DEVICES_SCHEMA,   _handle_spotify_devices,   "🔈"),
    ("spotify_queue",     SPOTIFY_QUEUE_SCHEMA,     _handle_spotify_queue,     "📻"),
    ("spotify_search",    SPOTIFY_SEARCH_SCHEMA,    _handle_spotify_search,    "🔎"),
    ("spotify_playlists", SPOTIFY_PLAYLISTS_SCHEMA, _handle_spotify_playlists, "📚"),
    ("spotify_albums",    SPOTIFY_ALBUMS_SCHEMA,    _handle_spotify_albums,    "💿"),
    ("spotify_library",   SPOTIFY_LIBRARY_SCHEMA,   _handle_spotify_library,   "❤️"),
]
```

`hermes auth spotify` 完成 PKCE 后所有工具自动可用，`_check_spotify_available()` 在没有有效 token 时让工具优雅失败。

### Google Meet 插件（v2026.4.30+）

`plugins/google_meet/` 包含：
- `meet_bot.py` —— 控制浏览器加入 Meet
- `realtime/` —— OpenAI Realtime API 桥接（语音输入 / 语音回应）
- `node/` —— Node.js bot server（处理 Meet 协议）
- `audio_bridge.py` + `process_manager.py` —— 进程管理
- `cli.py` —— `hermes google-meet preflight / install / start` 命令

完整流水线作为 plugin 打包，按需 opt-in。

## 相关页面

- [[tool-registry-architecture]] — 插件通过 registry.register() 注册工具
- [[hook-system-architecture]] — 插件钩子系统与网关事件钩子互补，包含 v2026.4.30+ 新 hook（`pre_gateway_dispatch`、`pre_approval_request` / `post_approval_response`、`transform_tool_result` / `transform_terminal_output`）
- [[model-tools-dispatch]] — MCP 工具通过 discover 机制集成到编排层
- [[messaging-gateway-architecture]] — `platform` kind plugin（IRC、Teams）

## 相关文件

- `tools/mcp_tool.py` — MCP 服务器任务
- `tools/mcp_oauth.py` — MCP OAuth
- `hermes_cli/plugins.py` — 插件系统（VALID_HOOKS / `_VALID_PLUGIN_KINDS`）
- `plugins/` — 插件目录

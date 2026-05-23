---
title: MCP 集成与插件系统
created: 2026-04-07
updated: 2026-05-04
type: concept
tags: [architecture, mcp, plugins, extensibility]
sources: [hermes-agent 源码分析 2026-04-07, plugins/, hermes_cli/plugins.py, dashboard]
---

# MCP 集成与插件系统

## 设计原理

Hermes 通过 **MCP（Model Context Protocol）** 和**插件系统**实现可扩展性，允许连接外部工具和自定义行为。

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

## 插件 CLI

```bash
# 插件管理
hermes plugins list           # 列出已安装插件
hermes plugins install <name> # 安装插件
hermes plugins remove <name>  # 移除插件
hermes plugins update <name>  # 更新插件
```

## Bundled 插件（v2026.4.30+）

`feat(plugins): bundled platform plugins auto-load by default`（commit 4d36349）：随 Hermes 一起发布的插件首次启动时自动注册，无需用户安装：

```
plugins/
├── platforms/
│   ├── irc/                       # 第一个参考实现（v2026.4.23+）
│   └── teams/                     # Microsoft Teams（v2026.4.30+）
├── kanban/                        # Kanban 看板 + dashboard UI + systemd unit
├── hermes-achievements/           # 成就徽章插件，扫描完整会话历史（v2026.4.30+，#17754）
├── observability/                 # Langfuse 可观测性
├── context_engine/                # Context Engine
├── memory/                        # honcho memory provider
├── disk-cleanup/                  # 磁盘清理
├── example-dashboard/             # 仪表盘示例
├── google_meet/                   # Google Meet 集成
├── image_gen/                     # 图像生成
├── spotify/                       # Spotify
└── strike-freedom-cockpit/        # cockpit
```

`feat(nix): bundle plugins/ and expose it via HERMES_BUNDLED_PLUGINS`（commit 6e42daf）让 nix 安装路径也能识别 bundled 插件目录。

`feat(plugins): bundle hermes-achievements + scan full session history`（62a5d72 #17754）vendored 自 [@PCinkusz/hermes-achievements](https://github.com/PCinkusz/hermes-achievements)，60+ 成就徽章。

## Dashboard 插件页面（v2026.4.30+）

`feat(dashboard): add Plugins page with enable/disable, auth status, install/remove`（commit e2a4905）：

- `/dashboard/plugins` 页面：每行插件展示启用状态、auth 状态（OAuth 已登录/未登录）、安装/卸载按钮
- `feat(dashboard): add hide/show toggle for dashboard plugins in sidebar`（c73b799）：侧边栏可隐藏/显示 dashboard 标签页
- `refactor(plugins): move rescan button to page header, remove redundant title`（a523632）

## 异步插件命令

`fix(plugins): bound async plugin command await with 30s timeout`（447a2bb）+ `fix(plugins): await async handlers in CLI and TUI dispatch`（ca9a61a）：CLI/TUI 插件命令现在正确 await 异步 handler，超时 30 秒兜底。

`fix(plugins): register dynamically-loaded modules in sys.modules before exec`（718e4e2）：动态加载插件模块前先注册到 `sys.modules`，避免 dataclass 序列化出现重复类标识问题。

## /reload-mcp 缓存提示

`feat(gateway,cli): confirm /reload-mcp to warn about prompt cache invalidation`（4d7fc0f）：`/reload-mcp` 现在弹确认提示，警告 MCP 工具变更会**整体失效 prompt cache**。配合 `fix(gateway): refresh cached agents after MCP tool changes`（7fae87b）保证 reload 后 cached agent 看到最新工具列表。

## 配置

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  filesystem:
      command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/root/work"]
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

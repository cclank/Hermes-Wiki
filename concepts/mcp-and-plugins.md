---
title: MCP 集成与插件系统
created: 2026-04-07
updated: 2026-05-31
type: concept
tags: [architecture, mcp, plugins, extensibility, mcp-catalog, mcp-pgid, mcp-startup]
sources: [tools/mcp_tool.py, tools/mcp_oauth.py, tools/mcp_oauth_manager.py, hermes_cli/plugins.py, hermes_cli/mcp_catalog.py, hermes_cli/mcp_picker.py, hermes_cli/mcp_config.py, hermes_cli/mcp_startup.py, optional-mcps/]
---

> **2026-05-29 增量（hermes-agent `689ef5e2`）**：
>
> - **MCP mTLS 客户端证书**（HTTP + SSE，#33721 / `87e5b2fae`）—— `tools/mcp_tool.py:573-625` 新增 `_resolve_client_cert(server_name, config)`，接受三种形态：单 PEM 字符串（cert + key 合并）、`[cert, key]` 列表、或 `(cert, key, password)` 三元组；亦支持 `client_cert + client_key` 分离形式。配套 `tests/tools/test_mcp_client_cert.py` 与 `website/docs/reference/mcp-config-reference.md`。
> - **工具渐进式披露扩展到 MCP / 插件工具**（`feat(tools): progressive tool disclosure for MCP and plugin tools`，`369075dc9`）—— 新增 `tools/tool_search.py`；`agent/tool_executor.py` / `hermes_cli/config.py` / `model_tools.py` 接入。MCP 与插件工具不再一次性全量注入 system prompt，按需经检索披露；并在会话 toolsets 作用域内收敛（`fix(tool-search): scope bridge catalog + dispatch to the session's toolsets`，`7427b9d58`）。
> - **MCP 连接侧修复**：解析裸 `npx`/`npm`/`node` 至 `/usr/local/bin`（`e7c99651f`）、未取得 token 时不再误报 OAuth 成功（`27a2c4f36` #34807）、`CancelledError` isinstance 检查放宽到 `BaseException`（`9f5afc763`）。
>
> 详见 [[2026-05-29-update#4-mcp-mtls-客户端证书--解析与-oauth-修复]]。
>
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

### v0.14.0 MCP stdio SDK 缺失诊断（2026-05-23，`5acaeba`，#31450）

`tools/mcp_tool.py:+9 行` —— stdio MCP SDK（`mcp.client.stdio`）缺失时，调用 `_run_stdio` 抛 `ImportError` 并附带安装指引（"pip install mcp"），不再抛 `NameError: name '_stdio_client' is not defined`（原因：try/except ImportError 把 import 静默吞，names 留在 module scope 未绑定）。对齐 `_run_http` 早已存在的 `_MCP_HTTP_AVAILABLE` gate。

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

## MCP SSE Transport（v0.13.0+）

`tools/mcp_tool.py:5,35,52,203-208`：MCP 服务器现在支持三种 transport：

```yaml
# config.yaml
mcp:
  servers:
    my-sse-server:
      url: http://localhost:8000/sse
      transport: sse       # 替代默认 Streamable HTTP
```

- **SSE transport** 配 `transport: sse`
- **OAuth forwarding** for SSE：MCP server 后端的 OAuth 流可直接转发
- **Stale-pipe retries**：连接断开后自动重连
- **Image result 改作 MEDIA tag**（之前被直接丢弃）
- **Lifecycle keepalive** for 长 lived waits

## `transform_llm_output` 插件 lifecycle Hook（v0.13.0+）

`agent/conversation_loop.py:3936,3944` + `hermes_cli/plugins.py:136`：新增 lifecycle hook，让插件在 LLM 输出**回到对话之前**重塑/过滤。Context-window reducer 和内容过滤器用得上：

```python
def register(ctx):
    @ctx.transform_llm_output
    def shrink_excess(output: str) -> str:
        # 例如：截掉超过 10KB 的部分，加 [truncated] 标记
        return output[:10240] + "\n[...truncated]" if len(output) > 10240 else output
```

## Plugin `ctx.llm` + `tool_override`（v0.14.0+）

插件可走 active provider + credentials **直接发 LLM call**，无需手动 client wiring：

```python
def register(ctx):
    @ctx.register_tool("my_custom_search")
    async def search(query: str) -> str:
        # 走主 agent 同款 provider/model 路由 + 凭证
        return await ctx.llm.complete(f"Search: {query}", model="auto")
```

**`tool_override=True`** flag 允许插件**干净替换**一个 built-in 工具的实现，旧实现自动让位。

## Nous-Approved MCP Catalog（NEW 2026-05-26，feat #30870）

镜像 `optional-skills/` 模式的 curated MCP server 目录：**presence in `optional-mcps/` = approval**，no community tier, no trust signals。Entries 仅通过 PR 合入。

### 三入口 CLI（`hermes_cli/main.py:13023-13046`）

| 子命令 | 行为 |
|--------|------|
| `hermes mcp` / `hermes mcp picker` | 交互式 catalog picker（curses checklist） |
| `hermes mcp catalog` | Plain-text 列表，scriptable |
| `hermes mcp install <name>` | 安装指定 catalog entry |
| `hermes mcp configure <name>` | 安装后改 tool selection（重跑 checklist） |
| `hermes mcp login <name>` | 强制 OAuth re-auth |

Picker 行为（`hermes_cli/mcp_picker.py:160-228 _handle_row`）：

- **未安装** → install（必要时 clone/bootstrap，prompt creds）
- **已装但 off** → enable
- **已装且 on** → menu（disable / uninstall / reinstall）

### Manifest Schema — `optional-mcps/<name>/manifest.yaml`

`hermes_cli/mcp_catalog.py:151-264 _parse_manifest()`，`manifest_version: 1`：

- `transport`: `stdio`（command/args + `${INSTALL_DIR}` 子串替换 `mcp_catalog.py:427-435`）或 `http`（url）。
- `install`: 可选 `git_repo` clone + `bootstrap_commands` 链；npx/uvx 类零安装 server 可省略。
- `auth`: `api_key`（install 时 prompt → `~/.hermes/.env`）/ `oauth`（native MCP OAuth 或 third-party 如 Google）/ `none`。
- `tools.default_enabled`: 可选预 check 列表；未提供则 install 时全部预 check，用户 prune。
- `post_install`: 后续指引文案（如 OAuth restart 提示）。

### 仓内两个参考条目

- `optional-mcps/n8n/manifest.yaml` —— **stdio + api_key + git-bootstrap** 路径：clone `CyberSamuraiX/hermes-n8n-mcp` 到本地 venv 后 stdio 启动。
- `optional-mcps/linear/manifest.yaml` —— **http + native MCP OAuth** 路径：URL `https://mcp.linear.app/mcp`，OAuth 走 PKCE + Dynamic Client Registration（无需本地 install），`mcp_oauth_manager` 自动 discovery + token refresh。

### 设计原则与约束

- **Credentials 永远走 `~/.hermes/.env`**（`mcp_catalog.py:437-459 _prompt_env_vars`，line 14-15 注释引 `.env-is-for-secrets` 规则），从不落 per-server env block —— 统一凭证仓库便于 redact / rotate。
- **Catalog 从不自动更新** —— 用户显式 `hermes mcp install <name>` 才会拉新 manifest。manifest 修改要走 hermes-agent PR review。
- **Tool selection 在 install 时定型**：probe server tools → curses checklist 预 check → 写 `mcp_servers.<name>.tools.include`。Probe 失败 fallback 到 manifest `tools.default_enabled` 或全选 + 提示 `hermes mcp configure`。

### 三模块拆分（共 1901 行新增）

| 文件 | 行数 | 责任 |
|------|------|------|
| `hermes_cli/mcp_catalog.py` | 776 | manifest 解析、git/bootstrap install、tool probe、tool include 写入、uninstall |
| `hermes_cli/mcp_picker.py` | 322 | curses 交互层（`_Row` line 55 → `run_picker` line 274） |
| `hermes_cli/mcp_config.py` | 803 | 入口分发 + 旧 `hermes mcp add/remove/list/enable/disable/configure/login` 命令保持兼容 |

Tests：19 个 catalog 测试 + E2E install/uninstall round-trip。

## v0.15.1 维护窗口增量（2026-05-31，hermes `eb3cf9750`）

### 1. stdio MCP 子孙经进程组信号回收（`a29d64e50`）

**问题**：

- MCP SDK 用 `start_new_session=True` 启 stdio 子进程：每个直接子 = 自己的 session/pgroup leader（PGID == PID）。
- 该直接子若自己再 spawn helper（如 wrapper `openclaw mcp serve` 内部再起 `claude mcp serve`），孙子继承 PGID（除非自己 `setsid`）。
- 直接子退出后，孙子 reparent 到 `systemd --user` 但**保留原 PGID** —— 老 reaper 只 track 直接 PID 就**清不到孙子**，孙子在 systemd 下永生。

**修复**（`tools/mcp_tool.py`）：

| 行号 | 内容 |
|---|---|
| `:2270-2281` | `_stdio_pgids: Dict[int, int] = {}  # pid -> pgid` —— spawn 时捕获 PGID，与 `_stdio_pids` 分开存（即使直接子退出移出 active map，PGID 仍保留） |
| `:3699-3700` | 信号经 `os.killpg(pgid, sig)` 发给整 pgroup —— 孙子也吃到 |
| Windows | `_stdio_pgids` 空（`os.getpgid` POSIX-only），fallback 老 PID 路径 |

### 2. agent-capable startup 不再阻塞 MCP discovery（`0c6e133c0`）

`perf(cli): stop eager MCP discovery from blocking agent-capable startup`：

- 新文件 **`hermes_cli/mcp_startup.py`（59 行）** + tests 166 行。
- `hermes -z` / interactive / TUI 等 agent-capable 启动路径原同步 await 全部 MCP server discovery；多 server / 慢 server 时冷启冻几秒。
- 改 background task：startup 不 await，agent 首次需要 MCP 工具时如未就绪走 graceful degrade（log warning + skip）。

### 3. MCP OAuth 重连 poll 改 asyncio.sleep（`eb9bfd392`）

`fix(T5): replace time.sleep(0.25) with asyncio.sleep in MCP auth reconnect poll`：

- OAuth re-auth 重连 polling 用 `time.sleep(0.25)`，**阻塞 event loop** 250 ms × N 次。
- 改 `await asyncio.sleep(0.25)`，让出 loop 让其他任务（webhook、heartbeat）跑。

### 4. TUI 启动不被慢/死 MCP 卡住（`cbf851ae1`）

`perf(tui): stop slow/dead MCP servers from freezing TUI startup`。结构与 §2 同：discovery 异步化 + per-server timeout。

### 5. mcp_serve 包进 py-modules（`a57cc0008`）

`fix(packaging): include mcp_serve in py-modules so hermes mcp serve works on pip installs`：

- 顶层模块 `mcp_serve` 不在 `pyproject.toml` 的 `py-modules` 显式列表 → pip wheel 不打包 → `hermes mcp serve` 子命令 ImportError。
- 修：加 `mcp_serve` 进 `[tool.setuptools] py-modules`。

### 6. tool_output_limits 不再 cache（`91a98d151`）

`fix: tool_output_limits re-reads config on every call (no caching)`：

- 之前 module-level 一次读、cache 到 frozenset/dict；用户改 config 不生效（即使 `hermes reload` 也只重建 agent）。
- 改：每次 call 现读 config。性能损失可忽略（dict lookup 在 µs 级），换来 config 改动立即生效。

---

## 相关页面

- [[tool-registry-architecture]] — 插件通过 registry.register() 注册工具
- [[hook-system-architecture]] — 插件钩子系统与网关事件钩子互补，包含 v2026.4.30+ 新 hook（`pre_gateway_dispatch`、`pre_approval_request` / `post_approval_response`、`transform_tool_result` / `transform_terminal_output`）
- [[model-tools-dispatch]] — MCP 工具通过 discover 机制集成到编排层
- [[messaging-gateway-architecture]] — `platform` kind plugin（IRC、Teams）
- [[security-defense-system]] — MCP tool 结果走 `<untrusted_tool_result>` 包裹（`mcp_*` prefix 在 `_UNTRUSTED_TOOL_PREFIXES`）

## 相关文件

- `tools/mcp_tool.py` — MCP 服务器任务（SSE transport: lines 5,35,52,203-208）
- `tools/mcp_oauth.py` — MCP OAuth
- `hermes_cli/plugins.py` — 插件系统（transform_llm_output: line 136）
- `agent/conversation_loop.py` — transform_llm_output dispatch（lines 3936, 3944）
- `plugins/` — 插件目录
- `hermes_cli/mcp_catalog.py` — **NEW 2026-05-26** Catalog 解析与 install（776 行）
- `hermes_cli/mcp_picker.py` — **NEW 2026-05-26** Curses 交互选择器（322 行）
- `hermes_cli/mcp_config.py` — **NEW 2026-05-26** `hermes mcp ...` 命令分发（803 行）
- `optional-mcps/n8n/manifest.yaml` — **NEW 2026-05-26** 参考 manifest（stdio + api_key + git-bootstrap）
- `optional-mcps/linear/manifest.yaml` — **NEW 2026-05-26** 参考 manifest（http + native MCP OAuth）

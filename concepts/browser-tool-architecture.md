---
title: Browser Tool 浏览器自动化架构
created: 2026-04-08
updated: 2026-05-20
type: concept
tags: [tool, toolset, architecture, component, browser, cdp]
sources: [tools/browser_tool.py, tools/browser_supervisor.py, tools/browser_cdp_tool.py, hermes_cli/browser_connect.py]
---

# Browser Tool — 浏览器自动化架构

## 概述

Browser Tool 位于 `tools/browser_tool.py`，提供**多后端浏览器自动化**能力。所有后端对 Agent 暴露相同工具接口（navigate / click / type / scroll / vision / console / pdf 等）。

核心理念：**基于 accessibility tree（ariaSnapshot）的文本化页面表示**，使 LLM Agent 无需视觉能力即可操作网页。

## v0.14.0 关键变化

### 1. `browser_console` 180× 性能提升

源码：`tools/browser_tool.py:2819` 起 `_call_via_supervisor_cdp_ws()` 路径。

```python
# fast path: route through the supervisor's persistent CDP WS
```

历史上 `browser_console` 每次调用都会重建 DevTools session（连接 / 鉴权 / target attach），单次成本秒级。v0.14.0 引入 **supervisor 维护的持久 CDP WS 连接**，agent 全程共享同一条 socket，单次 `console` evaluate 从秒级 → 毫秒级。

### 2. Chromium-family 自动启动（CDP）

post-v0.14.0：`feat: auto-launch Chromium-family browser for CDP`（`hermes_cli/browser_connect.py`）。

- 检测系统已装的 Chromium / Chrome / Brave / Edge。
- 用合适的 `--remote-debugging-port` 自动起一个有头实例。
- CDP `--user-data-dir` 隔离避免和用户日常浏览器互锁。
- Brave binary 也支持（`test(cli): cover Brave binary CDP launch detection`）。

效果：用户不用先手动打开浏览器再让 hermes 连 —— `hermes` 自己起一个。

### 3. SSRF floor 强制

v0.13.0 安全潮一部分：浏览器**默认拒绝 cloud-metadata 地址**（`169.254.x.x`、`metadata.*`）。即使 SSRF 防护被错误关掉，这条底线是 floor，不可越过。

## 架构原理

### 多种后端

| 后端 | 模式 | 依赖 | 成本 |
|---|---|---|---|
| **本地 Chromium / Lightpanda** | 默认 | `agent-browser` CLI | 零成本 |
| **Browser Use** | 云端插件 | BROWSER_USE_API_KEY 或 Nous 托管网关 | 按量付费 |
| **Browserbase** | 云端插件 | BROWSERBASE_API_KEY + BROWSERBASE_PROJECT_ID | 按量付费 |
| **Firecrawl** | 云端插件 | FIRECRAWL_API_KEY（仅显式配置可用） | 按量付费 |
| **Camofox** | 本地反检测 | CAMOFOX_URL 环境变量 | 自建/付费 |
| **CDP Override** | 直连 | BROWSER_CDP_URL | 已有浏览器实例 |

### 本地引擎：Chrome 与 Lightpanda

本地模式可选择两种引擎，由 `config.yaml` 的 `browser.engine`（或 `AGENT_BROWSER_ENGINE` 环境变量）控制，合法值为 `auto`、`lightpanda`、`chrome`（`tools/browser_tool.py:675`）：

- **`auto`**（默认）：不传 `--engine`，agent-browser 默认使用 Chrome。
- **`lightpanda`**：转发 `--engine lightpanda`（需 agent-browser v0.25.3+）。Lightpanda 在导航上比 Chrome 快 1.3–5.8 倍，但**无图形渲染器**（无法截图）。
- **`chrome`**：显式使用 Chrome。

`--engine` 仅在非云端、非 Camofox 的本地会话且引擎非 `auto` 时注入（`_should_inject_engine`，`tools/browser_tool.py:686`）。

#### Lightpanda → Chrome 自动回退

Lightpanda 渲染不完整时，Hermes 会自动用 Chrome 重试。`_lightpanda_fallback_reason()`（`tools/browser_tool.py:704`）对可回退命令（`open/snapshot/screenshot/eval/click/fill/scroll/back/press/console/errors`）检测以下情况：

- 命令显式失败；
- `snapshot` 返回空或不足 20 字符的快照；
- `screenshot` 文件过小（< 20480 字节，即 Lightpanda 的占位图）。

回退在原始任务中开一个临时 Chrome 会话（`_run_chrome_fallback_command`，`tools/browser_tool.py:797`），结果会标注 `⚠ Lightpanda fallback` 警告并附带 `browser_engine_fallback` 元数据，让 CLI/TUI/网关用户看到引擎切换。

### 后端解析链

```python
def _get_cloud_provider() -> Optional[CloudBrowserProvider]:
    """解析优先级（tools/browser_tool.py:489）:
    1. config.yaml browser.cloud_provider == "local" → None（禁用云端）
    2. browser.cloud_provider 显式指定 → 经 agent.browser_registry 查找
    3. 自动检测：Browser Use → Browserbase（旧版优先级顺序）
    4. None → 本地模式
    """
```

解析结果在进程生命周期内缓存。显式配置分支会通过 `_registry_get_browser_provider()` 查询 `agent.browser_registry`，因此第三方浏览器插件（`~/.hermes/plugins/browser/<vendor>/`）也能参与显式配置解析。

**关键设计**：
- 如果 `cloud_provider` 设为 `local`，完全禁用云端回退，强制使用本地浏览器。
- **Firecrawl 不在自动检测顺序中**（`agent/browser_registry.py:107` 的 `_LEGACY_PREFERENCE` 只含 `browser-use`、`browserbase`）。用户必须显式设置 `browser.cloud_provider: firecrawl` 才会使用 Firecrawl 云浏览器——因为 Firecrawl 与 `plugins/web/firecrawl/`（web 抽取插件）共用 `FIRECRAWL_API_KEY`，避免为 web 抽取配了密钥的用户被静默路由到付费云浏览器。
- 显式配置分支故意忽略 `is_available()`，使派发器抛出精确的 “X_API_KEY is not set” 错误，而非静默切换后端（`agent/browser_registry.py:113-145`）。

## 核心组件

### 1. BrowserProvider ABC（插件接口）

`agent/browser_provider.py` 定义抽象基类 `BrowserProvider`，镜像 `WebSearchProvider` 的形态。子类必须实现 `name`、`is_available` 以及三个生命周期方法：

```python
class BrowserProvider(abc.ABC):
    """云端浏览器后端的抽象基类"""

    @property
    @abc.abstractmethod
    def name(self) -> str: ...          # 稳定短标识，如 browserbase / browser-use / firecrawl

    @property
    def display_name(self) -> str: ...  # hermes tools 中显示的名称，默认为 name

    @abc.abstractmethod
    def is_available(self) -> bool: ... # 廉价检查（环境变量/令牌/可选依赖），不得发网络请求

    @abc.abstractmethod
    def create_session(self, task_id) -> Dict: ...  # 返回会话元数据

    @abc.abstractmethod
    def close_session(self, session_id) -> bool: ...

    @abc.abstractmethod
    def emergency_cleanup(self, session_id) -> None: ...  # atexit/信号处理时调用，不得抛异常

    def get_setup_schema(self) -> Dict: ...  # 供 hermes tools picker 使用的元数据
```

**会话元数据契约**（从旧版 `CloudBrowserProvider` 逐字保留）：`create_session()` 必须返回至少含 `session_name`、`bb_session_id`（提供商会话 ID，旧键名沿用以保持向后兼容）、`cdp_url`、`features` 的 dict（`agent/browser_provider.py:90-108`）。

**向后兼容**：旧 ABC 暴露的 `is_configured()` / `provider_name()` 作为薄委托保留（`agent/browser_provider.py:169-175`），`tools.browser_tool` 中约 6 处旧调用点无需改动。`browser_tool.py` 顶部还把 ABC 别名为 `CloudBrowserProvider`、把三个插件类别名为 `BrowserbaseProvider` 等，作为旧导入面（`tools/browser_tool.py:91-103`）。

### 2. browser_registry 注册表与派发

`agent/browser_registry.py` 维护已注册提供商的中央 map：

```python
_providers: Dict[str, BrowserProvider] = {}   # 线程安全（_lock 保护）

def register_provider(provider: BrowserProvider) -> None: ...   # 插件 import 时调用
def get_provider(name: str) -> Optional[BrowserProvider]: ...
def get_active_browser_provider() -> Optional[BrowserProvider]: ...
```

插件在 import 时通过 `PluginContext.register_browser_provider()` 注册实例；`_get_cloud_provider()` 经注册表路由每一次云端模式 `browser_*` 调用。注册表只负责**选择**——不像 web 子系统有 search/extract/crawl 的“能力”拆分，每个浏览器提供商都实现完整的 `BrowserProvider` 生命周期（`agent/browser_registry.py:30-34`）。

### 3. 浏览器插件（`plugins/browser/`）

三个内置云端提供商插件，`kind: backend`，自动加载：

| 插件目录 | `provides_browser_providers` | provider 类 |
|---|---|---|
| `plugins/browser/browser_use/` | `browser-use` | `BrowserUseBrowserProvider` |
| `plugins/browser/browserbase/` | `browserbase` | `BrowserbaseBrowserProvider` |
| `plugins/browser/firecrawl/` | `firecrawl` | `FirecrawlBrowserProvider` |

每个插件镜像 `plugins/web/<vendor>/` 布局：`provider.py` 持有 provider 类，`__init__.py::register(ctx)` 实例化并调用 `ctx.register_browser_provider(...)` 注册，`plugin.yaml` 声明元数据。用户也可在 `~/.hermes/plugins/browser/<name>/` 放置自定义插件（需在 `plugins.enabled` 中显式启用，且只能通过显式 `cloud_provider` 配置生效）。

**优越性**：新增后端只需实现 ABC 的 5 个抽象成员并放入 `plugins/browser/`，工具逻辑完全不变。

### 4. 会话管理（线程安全）

**设计细节**：
- 每个 task_id 独立会话，支持子代理并行浏览器操作
- 双重检查锁模式：网络调用在锁外执行，避免持有锁阻塞其他线程
- 竞态保护：网络调用完成后再次检查活动会话表，防止重复创建

### 5. 命令执行架构

```python
def _run_browser_command(task_id, command, args, timeout):
    # 1. 找到 agent-browser CLI
    # 2. 获取会话信息（创建/复用）
    # 3. 构建命令：--cdp <websocket> (云) 或 --session <name> (本地)
    # 4. 使用临时文件（非管道）捕获 stdout/stderr
    # 5. 解析 JSON 输出
```

**关键决策 — 临时文件替代管道**：

`agent-browser` 启动后台 daemon 进程，daemon 继承文件描述符。如果使用 `capture_output=True`（管道），daemon 会保持管道 fd 打开，导致 `communicate()` 永远等不到 EOF 而超时。

解决方案：用 `os.open()` 创建临时文件，执行后立即关闭 fd，daemon 不再阻止读取。

### 6. 并发安全 — 独立 Socket 目录

```python
task_socket_dir = os.path.join(
    tempfile.gettempdir(),
    f"agent-browser-{session_name}"
)
os.makedirs(task_socket_dir, mode=0o700, exist_ok=True)
browser_env["AGENT_BROWSER_SOCKET_DIR"] = task_socket_dir
```

**问题**：并行子代理共享默认 socket 路径，导致 "Failed to create socket directory: Permission denied"。

**解决**：每个 task_id 独立的 socket 目录，权限 0o700 确保隔离。

### 7. macOS Unix Socket 路径修复

```python
def _socket_safe_tmpdir():
    """macOS TMPDIR=/var/folders/xx/.../T/ (~51 chars)
    追加 agent-browser-hermes_... 后超过 104 字节 AF_UNIX 限制
    → macOS 强制使用 /tmp"""
    if sys.platform == "darwin":
        return "/tmp"
    return tempfile.gettempdir()
```

## 安全设计

### 多层安全防护

| 层级 | 保护 | 实现 |
|---|---|---|
| **URL 注入防护** | 阻止 URL 中嵌入 API Key | `agent.redact._PREFIX_RE` 检测 `sk-ant-` 等前缀（`tools/browser_tool.py:2304`） |
| **SSRF 防护** | 阻止访问私有/内部地址 | `tools.url_safety` 的 `is_safe_url()`（导入为 `_is_safe_url`），安全模块不可用时 fail-closed |
| **网站策略** | 黑名单域名拦截 | `website_policy.check_website_access(url)` |
| **重定向后检查** | 阻止重定向到内部地址 | 导航后检查 `final_url`（`tools/browser_tool.py:2393`） |
| **密钥脱敏** | 快照发送给辅助 LLM 前脱敏 | `agent.redact.redact_sensitive_text()` |

**重要**：SSRF 防护仅对云端后端启用（`_is_local_backend()`，`tools/browser_tool.py:621`）。本地后端（Camofox、或无云端提供商的本地 Chromium/Lightpanda）跳过此检查，因为 Agent 已通过 terminal 工具获得完整的本地网络访问权限，远程内部资源不可达，检查无安全价值。

### Bot 检测预警

```python
# tools/browser_tool.py:2435-2441
blocked_patterns = [
    "access denied", "access to this page has been denied",
    "blocked", "bot detected", "verification required",
    "please verify", "are you a robot", "captcha",
    "cloudflare", "ddos protection", "checking your browser",
    "just a moment", "attention required"
]
if any(pattern in title_lower for pattern in blocked_patterns):
    response["bot_detection_warning"] = "..."
```

导航返回的页面标题包含 bot 检测关键词时，主动警告并提供解决方案（延迟操作/启用隐身模式/更换站点）。

## 工具集（10 个工具）

| 工具 | 功能 |
|---|---|
| `browser_navigate` | 导航到 URL，自动返回紧凑快照 |
| `browser_snapshot` | 获取页面 accessibility tree 快照 |
| `browser_click` | 点击 ref 标识的元素（@e1, @e5） |
| `browser_type` | 在输入框中输入文本 |
| `browser_scroll` | 上/下滚动（重复 5 次确保有效移动） |
| `browser_back` | 浏览器后退 |
| `browser_press` | 按键（Enter/Tab/Escape 等） |
| `browser_console` | 获取控制台输出和 JS 错误 |
| `browser_get_images` | 提取页面图片 URL 和 alt 文本 |
| `browser_vision` | 截图 + 视觉 AI 分析 |

### 自动快照优化

`browser_navigate` 成功后**自动获取紧凑快照**，模型无需额外调用 `browser_snapshot`。这减少了一次 API 往返。

### Vision 工具

```python
def browser_vision(question, annotate=False):
    # 1. 截图（支持 --annotate 叠加元素标签）
    # 2. Base64 编码
    # 3. 通过 call_llm(task="vision") 调用视觉模型
    # 4. 返回分析结果 + 截图路径
    # 5. 失败时保留截图文件供用户查看
```

**优雅降级**：如果截图成功但视觉分析失败，保留截图文件并告知用户可通过 `MEDIA:<path>` 查看。

### JavaScript 评估

`browser_console(expression="...")` 在页面上下文中执行 JavaScript，相当于 DevTools Console：

```javascript
// 示例：获取页面标题
document.title

// 示例：统计链接数量
document.querySelectorAll("a").length
```

## 生命周期管理

### 后台清理线程

```python
# tools/browser_tool.py:1183 — 可经 BROWSER_INACTIVITY_TIMEOUT 环境变量覆写
BROWSER_SESSION_INACTIVITY_TIMEOUT = int(os.environ.get("BROWSER_INACTIVITY_TIMEOUT", "300"))

def _browser_cleanup_thread_worker():
    """启动时先 reap 上次进程遗留的孤儿会话，
    随后每 30 秒检查一次，清理超时无活动的会话。
    睡眠按 1 秒分片，以便快速响应停止信号。"""
```

**设计考量**：超时设为 5 分钟，给 LLM 推理留足时间（特别是子代理执行多步骤浏览器任务时）。

### 紧急清理

```python
atexit.register(_emergency_cleanup_all_sessions)  # 进程退出时
```

**只使用 atexit，不劫持 SIGINT/SIGTERM**：早期版本安装信号处理器调用 `sys.exit()`，但与 prompt_toolkit 的异步事件循环冲突，导致进程无法被 kill。

### 自动录制

```yaml
# config.yaml
browser:
  record_sessions: true
```

首次导航时自动启动录制，会话关闭时保存 `.webm` 文件。超过 72 小时的录制自动清理。

## 设计优越性

### 对比传统 Selenium/Playwright 方案

| 维度 | 传统方案 | Hermes Browser Tool |
|---|---|---|
| 页面表示 | HTML/DOM（LLM 难以理解） | accessibility tree（结构化文本） |
| 元素定位 | XPath/CSS 选择器 | ref ID（@e1, @e5）|
| 多后端 | 需要重写代码 | 插件化 ABC + 注册表，后端自动选择 |
| 安全 | 无内置保护 | SSRF + 注入 + 策略三层防护 |
| 并发 | 需要手动管理 | task_id 自动隔离 |
| 清理 | 容易泄漏 | 后台线程 + atexit 双重保障 |
| 视觉 | 需要额外集成 | 内置 vision 工具 |

### Accessibility Tree 的优越性

传统 HTML 快照包含大量样式和结构噪声。Accessibility tree 只保留：
- 交互元素（按钮、链接、输入框）
- 语义角色（heading, button, link, textbox）
- 可见文本内容
- 元素关系

这使得 LLM 能以更少的 token 理解页面结构并做出操作决策。

## 配置与操作

### 本地模式（零成本）

```bash
# 安装 agent-browser
npm install -g agent-browser
agent-browser install --with-deps  # 下载 Chromium + 系统库
```

### 云端模式

```yaml
# config.yaml
browser:
  cloud_provider: browser-use  # 或 browserbase, firecrawl, local
  engine: auto                 # 本地引擎：auto / lightpanda / chrome
  allow_private_urls: false    # SSRF 保护（默认开启）
  command_timeout: 30          # 命令超时（秒）
  record_sessions: false       # 自动录制
  camofox:
    managed_persistence: false # Hermes 托管 Camofox profile 持久化
```

### CDP 直连模式

```bash
export BROWSER_CDP_URL="ws://localhost:9222/devtools/browser/xxx"
# 或 HTTP 发现端点
export BROWSER_CDP_URL="http://localhost:9222"
```

### Camofox 反检测模式

```bash
export CAMOFOX_URL="http://localhost:9377"
```

设置 `CAMOFOX_URL` 后所有浏览器操作改为通过 Camofox REST API 路由（而非 agent-browser CLI），Camofox 为本地后端，跳过 SSRF 检查。实现位于 `tools/browser_camofox.py`，`is_camofox_mode()` 返回 `bool(get_camofox_url())`。

**Hermes 托管持久化**：由 `config.yaml` 的 `browser.camofox.managed_persistence` 控制（`tools/browser_camofox.py:111`）。启用后 Hermes 发送从当前 profile 派生的确定性 `userId`（见 `tools/browser_camofox_state.py` 的 `get_camofox_identity()`，基于 `uuid5`），使 Camofox 跨重启映射到同一持久化浏览器 profile 目录。

**外部托管会话**：当某个集成自身拥有可见的 Camofox 浏览器时，可通过 `CAMOFOX_USER_ID` / `CAMOFOX_SESSION_KEY` 环境变量（或 `browser.camofox` 配置下的 `user_id` / `session_key`）设置共享身份，使 Hermes 在同一浏览器 profile 中操作而非新建私有会话（`_camofox_identity_override()`，`tools/browser_camofox.py:123`）。配合 `CAMOFOX_ADOPT_EXISTING_TAB`（或 `adopt_existing_tab` 配置）时，网关重启后 Hermes 会重新接管 Camofox 中已打开的标签页而非新建（`_adopt_existing_tab()`，`tools/browser_camofox.py:170`）。

## Lightpanda 引擎（v0.13.0+，PR #20451）

`tools/browser_tool.py:407+` 引入 `_get_browser_engine()`，支持选择本地 browser 引擎：

```yaml
# config.yaml
browser:
  engine: "auto"        # auto | lightpanda | chrome
```

**校验集合**（`browser_tool.py:559`）：`{"auto", "lightpanda", "chrome"}`，其他值拒绝。

| 引擎 | 优势 | 限制 |
|------|------|------|
| `chrome` | 完整功能、视频录制、扩展、复杂 JS 兼容 | 慢 |
| `lightpanda` | navigation **1.3-5.8x 比 Chrome 快**，资源占用极低 | 无 GUI、无视频录制、复杂 JS 可能不兼容 |
| `auto`（默认） | 让 agent-browser 自己决定 | 视环境而定 |

### 自动 Chrome fallback

`_lightpanda_fallback_reason(engine, command, result)`（`browser_tool.py:588`）—— Lightpanda 命令失败时自动用 Chrome 重试：

```
Lightpanda 'click' failed (timeout); retried with Chrome.
```

理由字段写进 user-visible reason 暴露给 agent，便于 LLM 理解为什么响应里出现"已切换"提示。

### 错误处理鲁棒化（v0.13.0 post-release）

- `48bf0ea24` — config 读失败时 fall-through 到 autodetect（不再硬错）
- `3170c8d44` — cloud provider 解析为 None 时**不 cache 这个 transient 状态**（避免错误 None 被永久缓存）

## 持久 CDP 连接 —— 180x 加速 `browser_console`（v0.14.0+）

`tools/browser_cdp_tool.py:301` `browser_cdp`：所有 `browser_console` 调用现在**共享一条到 Chrome 的 WebSocket 连接**，而不是每次起新 DevTools session。

| 模式 | 之前 | 现在 |
|------|------|------|
| 单次 `browser_console` | ~2 秒（建立 DevTools session） | ~10 ms |
| 加速倍数 | — | **~180×** |

实际页面交互从"卡顿"变"丝滑"。

## Cloud Metadata SSRF 底线（v0.13.0+）

`tools/url_safety.py:37-45`、`tools/browser_tool.py:2325,2334,2399-2411`：浏览器工具**硬拒**访问 cloud metadata endpoint（`169.254.169.254`、`metadata.google.internal` 等），即使用户配置 `allow_private_urls=true` 也无法绕过。返回："Blocked: URL targets a cloud metadata endpoint"。

闭合 v0.13.0 P0 之一。

## 与其他系统的关系

- [[auxiliary-client-architecture]] — browser_vision 通过 call_llm(task="vision") 调用
- [[tool-registry-architecture]] — 10 个浏览器工具通过 registry.register() 注册
- [[web-tools-architecture]] — 文档建议简单信息获取优先 web_search/web_extract
- [[security-defense-system]] — 浏览器工具的 SSRF 和注入防护是整体安全的一部分
- [[mcp-and-plugins]] — 云端浏览器后端现作为 `plugins/browser/<vendor>/` 插件加载

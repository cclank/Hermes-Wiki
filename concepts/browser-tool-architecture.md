---
title: Browser Tool 浏览器自动化架构
created: 2026-04-08
updated: 2026-05-18
type: concept
tags: [tool, toolset, architecture, component, browser]
sources: [tools/browser_tool.py, agent/browser_provider.py, agent/browser_registry.py, plugins/browser/]
---

# Browser Tool — 浏览器自动化架构

## 概述

Browser Tool 位于 `tools/browser_tool.py`（3796 行），提供**多后端浏览器自动化**能力。支持 4 种运行模式，所有模式对 Agent 暴露完全相同的工具接口（navigate/click/type/scroll/vision 等）。

核心理念：**基于 accessibility tree（ariaSnapshot）的文本化页面表示**，使 LLM Agent 无需视觉能力即可操作网页。

## 架构原理

### 多种后端

| 后端 | 模式 | 依赖 | 成本 |
|---|---|---|---|
| **本地 Chromium** | 默认 | `agent-browser` CLI + Chromium | 零成本 |
| **Browser Use** | 云端 | BROWSER_USE_API_KEY 或 Nous 托管 | 按量付费 |
| **Browserbase** | 云端 | BROWSERBASE_API_KEY + PROJECT_ID | 按量付费 |
| **Firecrawl** | 云端 | FIRECRAWL_API_KEY | 按量付费 |
| **Camofox** | 反检测 | CAMOFOX_URL 环境变量 | 自建/付费 |
| **CDP Override** | 直连 | BROWSER_CDP_URL | 已有浏览器实例 |

### Browser Engine：Lightpanda（2026-05 新增）

本地模式下可切换 Chromium / Lightpanda 引擎，agent-browser v0.25.3+ 支持 `--engine` flag。

```yaml
browser:
  engine: "lightpanda"  # auto | lightpanda | chrome
```

或 `AGENT_BROWSER_ENGINE` env。`auto`（默认）= 不传 `--engine`，agent-browser 默认 Chrome。

| 引擎 | 优势 | 限制 |
|------|------|------|
| **Chrome** | 完整 JS / 截图 / 视频 | 较重 |
| **Lightpanda** | 1.3-5.8x 更快导航 | **无图形渲染（无 screenshot）**，部分 JS 不支持 |

**自动 Chrome fallback**（`_lightpanda_fallback_reason()`）：Lightpanda 在已知不支持的命令（如 screenshot 请求、特定错误码）下自动切回 Chrome 重试，warning 透传到 user。仅在 **local + non-camofox** 模式注入 `--engine`，cloud / camofox 路径不受影响。

### 后端解析链

```python
def _get_cloud_provider():
    """解析优先级 (tools/browser_tool.py:489-591):
    1. config.yaml browser.cloud_provider (显式指定)
    2. Legacy 自动检测顺序 _LEGACY_PREFERENCE = ("browser-use", "browserbase")
       —— 按可用性过滤(Browser Use 优先,因其覆盖 managed Nous gateway
       和直接 API key 两条路径;Browserbase 为更老的直接凭证回退)
    3. None → 本地模式
    """
```

`_get_cloud_provider` 通过 `agent.browser_registry` 解析，调用前先执行 `_ensure_browser_plugins_loaded()` 加载浏览器插件。`_LEGACY_PREFERENCE = ("browser-use", "browserbase")` 是自动检测顺序。

**关键设计**：如果 `cloud_provider` 设为 `local`，完全禁用云端回退，强制使用本地 Chromium。显式 `cloud_provider` 指向未注册的插件时 → 记录 WARNING 并回退到自动检测。**Firecrawl 永不参与自动检测** — 只能通过显式 `browser.cloud_provider: firecrawl` 启用。

**Firecrawl 被有意排除在自动检测之外**：`_LEGACY_PREFERENCE` 不含 `firecrawl`，用户只有显式设置 `browser.cloud_provider: firecrawl` 才会获得 Firecrawl 云端浏览器，避免简单的 web 抓取被静默路由到付费云端浏览器。

## 核心组件

### 1. 统一 Provider 接口

浏览器 Provider 已从 in-tree 的 `tools/browser_providers/` 目录迁移到**插件系统**。抽象基类是 `agent/browser_provider.py:49` 的 `BrowserProvider(abc.ABC)`：

```python
class BrowserProvider(abc.ABC):
    """所有云端浏览器后端的抽象基类 (agent/browser_provider.py:61-125)"""
    @property
    @abc.abstractmethod
    def name() -> str            # 稳定短标识 (config 用)
    @property
    def display_name() -> str    # 非抽象，默认返回 name；hermes tools 展示用

    @abc.abstractmethod
    def is_available() -> bool   # 替代旧的 is_configured()
    @abc.abstractmethod
    def create_session(task_id) -> Dict
    @abc.abstractmethod
    def close_session(session_id) -> bool
    @abc.abstractmethod
    def emergency_cleanup(session_id) -> None   # 新增

    def get_setup_schema() -> Dict  # 可选，供 hermes tools 选择器

# 具体实现 (plugins/browser/*/provider.py)
class BrowserbaseBrowserProvider(BrowserProvider)
class BrowserUseBrowserProvider(BrowserProvider)
class FirecrawlBrowserProvider(BrowserProvider)
```

**优越性**：新增后端只需实现 5 个抽象成员（`name`、`is_available`、`create_session`、`close_session`、`emergency_cleanup`），工具逻辑完全不变。`is_configured()` / `provider_name()` 仅保留为向后兼容 shim。

`create_session` 返回契约：必须包含 `bb_session_id`（provider 会话 ID，所有 provider 都沿用此 legacy 键名）以及可选的 `external_call_id`。

### 1b. 插件系统与注册表

浏览器 Provider 现在是位于 `plugins/browser/{browser_use,browserbase,firecrawl}/` 的**插件**，每个插件包含 `__init__.py`（暴露 `register(ctx)`）、`plugin.yaml`、`provider.py`。内置插件以 `kind: backend` 自动加载；用户插件放在 `~/.hermes/plugins/browser/<name>/`。

新文件 `agent/browser_registry.py` 维护一个线程安全的 `_providers` dict。插件通过 `ctx.register_browser_provider(...)` 注册。注册表提供 `register_provider`、`list_providers`、`get_provider`、`get_active_browser_provider`、`_resolve` 等接口。`_LEGACY_PREFERENCE = ("browser-use", "browserbase")` 定义自动检测顺序。

### 2. 会话管理（线程安全）

```python
_active_sessions: Dict[str, Dict[str, str]] = {}  # task_id → session_info
_session_last_activity: Dict[str, float] = {}     # task_id → timestamp
_cleanup_lock = threading.Lock()
```

**设计细节**：
- 每个 task_id 独立会话，支持子代理并行浏览器操作
- 双重检查锁模式：网络调用在锁外执行，避免持有锁阻塞其他线程
- 竞态保护：网络调用完成后再次检查 `_active_sessions`，防止重复创建

### 3. 命令执行架构

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

### 4. 并发安全 — 独立 Socket 目录

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

### 5. macOS Unix Socket 路径修复

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

### 三层安全防护

| 层级 | 保护 | 实现 |
|---|---|---|
| **URL 注入防护** | 阻止 URL 中嵌入 API Key | `_PREFIX_RE` 检测 sk-ant- 等前缀 |
| **SSRF 防护** | 阻止访问私有/内部地址 | `_is_safe_url()` 检测 10.x/192.168x/localhost |
| **网站策略** | 黑名单域名拦截 | `check_website_access(url)` |
| **重定向后检查** | 阻止重定向到内部地址 | 导航后检查 final_url |
| **密钥脱敏** | 快照发送给辅助 LLM 前脱敏 | `redact_sensitive_text()` |

**重要**：SSRF 防护仅对云端后端启用。本地后端（Camofox/本地 Chromium）跳过此检查，因为 Agent 已通过 terminal 工具获得完整的本地网络访问权限。

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
BROWSER_SESSION_INACTIVITY_TIMEOUT = 300  # 5 分钟无活动

def _browser_cleanup_thread_worker():
    """每 30 秒检查一次，清理超过 5 分钟无活动的会话"""
    while _cleanup_running:
        _cleanup_inactive_browser_sessions()
        time.sleep(30)
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
| 多后端 | 需要重写代码 | 统一接口，后端自动选择 |
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
  allow_private_urls: false    # SSRF 保护（默认开启）
  command_timeout: 30          # 命令超时（秒）
  record_sessions: false       # 自动录制
```

### CDP 直连模式

```bash
export BROWSER_CDP_URL="ws://localhost:9222/devtools/browser/xxx"
# 或 HTTP 发现端点
export BROWSER_CDP_URL="http://localhost:9222"
```

### Camofox 反检测模式

```bash
export CAMOFOX_URL="http://camofox-server:8080"
```

设置后所有浏览器操作通过 Camofox REST API 路由。

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

## 与其他系统的关系

- [[auxiliary-client-architecture]] — browser_vision 通过 call_llm(task="vision") 调用
- [[tool-registry-architecture]] — 10 个浏览器工具通过 registry.register() 注册
- [[web-tools-architecture]] — 文档建议简单信息获取优先 web_search/web_extract
- [[security-defense-system]] — 浏览器工具的 SSRF 和注入防护是整体安全的一部分

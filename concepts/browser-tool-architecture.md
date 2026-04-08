---
title: Browser Tool 浏览器自动化架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [tool, toolset, architecture, component, browser]
sources: [tools/browser_tool.py, tools/browser_providers/]
---

# Browser Tool — 浏览器自动化架构

## 概述

Browser Tool 位于 `tools/browser_tool.py`（84KB/2202行），提供**多后端浏览器自动化**能力。支持 4 种运行模式，所有模式对 Agent 暴露完全相同的工具接口（navigate/click/type/scroll/vision 等）。

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

### 后端解析链

```python
def _get_cloud_provider():
    """解析优先级:
    1. config.yaml browser.cloud_provider (显式指定)
    2. Browser Use (managed Nous gateway 或直接 API key)
    3. Browserbase (直接凭证)
    4. None → 本地模式
    """
```

**关键设计**：如果 `cloud_provider` 设为 `local`，完全禁用云端回退，强制使用本地 Chromium。

## 核心组件

### 1. 统一 Provider 接口

```python
class CloudBrowserProvider:
    """所有云端浏览器提供商的抽象基类"""
    def is_configured() -> bool
    def create_session(task_id) -> Dict  # 返回 {session_name, cdp_url, features}
    def close_session(session_id) -> None
    def provider_name() -> str

# 具体实现
class BrowserbaseProvider(CloudBrowserProvider)
class BrowserUseProvider(CloudBrowserProvider)
class FirecrawlProvider(CloudBrowserProvider)
```

**优越性**：新增后端只需实现 4 个方法，工具逻辑完全不变。

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
blocked_patterns = ["access denied", "bot detected", "cloudflare", 
                    "captcha", "just a moment", "checking your browser"]
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

## 与其他系统的关系

- [[auxiliary-client-architecture]] — browser_vision 通过 call_llm(task="vision") 调用
- [[tool-registry-architecture]] — 10 个浏览器工具通过 registry.register() 注册
- [[web-tools-architecture]] — 文档建议简单信息获取优先 web_search/web_extract
- [[security-defense-system]] — 浏览器工具的 SSRF 和注入防护是整体安全的一部分

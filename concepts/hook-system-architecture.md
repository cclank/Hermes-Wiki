---
title: Hook 系统架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, extensibility, mcp, plugins]
sources: [gateway/hooks.py, hermes_cli/plugins.py]
---

# Hook 系统架构

## 概述

Hermes Agent 有两套互补的扩展系统：

| 系统                | 位置                    | 职责                                      | 源码量   |
| ----------------- | --------------------- | --------------------------------------- | ----- |
| **Gateway Hooks** | gateway/hooks.py      | 网关事件驱动钩子（startup/session/agent/command） | 170 行 |
| **Plugin System** | hermes_cli/plugins.py | 插件生命周期钩子 + 工具注册 + CLI 命令扩展              | 609 行 |

核心理念：**Hooks 处理事件通知，Plugins 处理功能扩展——两者互补。**

## 架构原理

### Gateway Hooks — 事件驱动

Gateway Hooks 是一个**轻量级事件系统**，在网关生命周期的关键点触发处理器：

| 事件 | 触发时机 |
|---|---|
| `gateway:startup` | 网关进程启动 |
| `session:start` | 新会话创建（首次消息） |
| `session:end` | 会话结束（用户执行 /new 或 /reset） |
| `session:reset` | 会话重置完成 |
| `agent:start` | Agent 开始处理消息 |
| `agent:step` | 工具调用循环中的每一轮 |
| `agent:end` | Agent 完成消息处理 |
| `command:*` | 任何斜杠命令执行（通配符） |

### Plugin System — 功能扩展

Plugin System 支持插件注册**工具、钩子回调、CLI 子命令**，以及向对话注入消息。

**三级插件来源**：
1. **用户插件** — `~/.hermes/plugins/<name>/`
2. **项目插件** — `./.hermes/plugins/<name>/`（需 `HERMES_ENABLE_PROJECT_PLUGINS`）
3. **Pip 插件** — 通过 `hermes_agent.plugins` entry-point 组安装

## 核心组件

### Gateway Hooks

#### HookRegistry

```python
class HookRegistry:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}  # event_type → handlers
        self._loaded_hooks: List[dict] = []             # 元数据

    def discover_and_load(self):
        """
        1. 注册内置钩子（boot-md）
        2. 扫描 ~/.hermes/hooks/ 目录
        3. 每个钩子目录需要:
           - HOOK.yaml (name, description, events)
           - handler.py (async def handle(event_type, context))
        4. 动态加载 handler.py 模块
        5. 注册每个声明的事件
        """
```

#### 事件发射

```python
async def emit(self, event_type, context=None):
    """
    触发所有注册的处理器:
    1. 精确匹配: handlers["agent:start"]
    2. 通配符匹配: handlers["command:*"] 匹配 "command:reset"
    3. 支持同步和异步处理器
    4. 错误捕获，不阻塞主流程
    """
```

#### 内置钩子: boot-md

```python
# gateway/builtin_hooks/boot_md.py
# 在网关启动时运行 ~/.hermes/BOOT.md
# 允许用户在网关启动时注入自定义初始化指令
```

#### 钩子目录结构

```
~/.hermes/hooks/
  notify-on-start/
    HOOK.yaml          # name: notify-on-start
                       # events: [agent:start]
    handler.py         # async def handle(event_type, context):
                       #     ...
```

### Plugin System

#### PluginContext — 插件的 API 面

```python
class PluginContext:
    """提供给插件的 facade，允许注册工具、钩子、CLI 命令"""
    
    def register_tool(name, toolset, schema, handler, ...):
        """注册工具到全局 registry"""
    
    def inject_message(content, role="user"):
        """
        向活跃对话注入消息:
        - Agent 空闲时 → 作为下一个输入排队
        - Agent 运行中 → 中断并注入
        """
    
    def register_cli_command(name, help, setup_fn, handler_fn):
        """注册 CLI 子命令 (如 hermes honcho ...)"""
    
    def register_hook(hook_name, callback):
        """注册生命周期钩子回调"""
```

#### PluginManager

```python
class PluginManager:
    def discover_and_load(self):
        """
        1. 扫描用户插件 (~/.hermes/plugins/)
        2. 扫描项目插件 (./.hermes/plugins/, 可选)
        3. 扫描 pip entry-points
        4. 加载每个插件的 register(ctx)
        5. 跳过 config 中禁用的插件
        """
```

#### 插件结构

```
~/.hermes/plugins/my-plugin/
  plugin.yaml          # name, version, description
                       # requires_env: [MY_API_KEY]
                       # provides_tools: [my_tool]
                       # provides_hooks: [pre_tool_call]
  __init__.py          # def register(ctx):
                       #     ctx.register_tool(...)
                       #     ctx.register_hook(...)
```

#### 生命周期钩子

```python
VALID_HOOKS = {
    "pre_tool_call",      # 工具调用前
    "post_tool_call",     # 工具调用后
    "pre_llm_call",       # LLM 调用前
    "post_llm_call",      # LLM 调用后
    "pre_api_request",    # API 请求前
    "post_api_request",   # API 请求后
    "on_session_start",   # 会话开始
    "on_session_end",     # 会话结束
}
```

#### 钩子调用

```python
def invoke_hook(self, hook_name, **kwargs):
    """
    调用所有注册的回调:
    1. 每个回调独立 try/except（错误不传播）
    2. 收集非 None 返回值
    3. 对于 pre_llm_call，可返回 context 注入到用户消息
    
    重要: context 注入到用户消息而非系统提示
    → 保持系统提示不变 → 缓存命中
    → 注入的内容是临时的，不持久化到 session DB
    """
```

#### Hook 调用点

`model_tools.py` 在 `handle_function_call()` 中调用插件钩子：

```python
def handle_function_call(function_name, function_args, ...):
    # pre_tool_call hook
    invoke_hook("pre_tool_call", tool_name=..., args=...)
    
    result = registry.dispatch(function_name, function_args, ...)
    
    # post_tool_call hook
    invoke_hook("post_tool_call", tool_name=..., args=..., result=...)
    
    return result
```

## 设计优越性

### Gateway Hooks vs Plugin System

| 维度 | Gateway Hooks | Plugin System |
|---|---|---|
| 作用域 | 仅 Gateway 模式 | CLI + Gateway |
| 注册方式 | 目录扫描 (HOOK.yaml) | 目录/entry-point 扫描 (plugin.yaml) |
| 功能 | 事件通知 | 工具注册 + 钩子 + CLI 命令 + 消息注入 |
| 复杂度 | 轻量 (170 行) | 完整 (609 行) |
| 使用场景 | 启动通知、审计、监控 | 扩展工具、自定义行为、第三方集成 |

### 错误隔离

```python
# 两个系统都采用 "错误不传播" 设计
try:
    result = fn(event_type, context)
except Exception as e:
    print(f"[hooks] Error in handler: {e}")  # 仅记录，不阻塞
```

**设计哲学**：扩展系统的错误不应影响核心 Agent 流程。

### 上下文注入的缓存友好设计

Plugin hooks 返回的 context 注入到**用户消息**而非系统提示：

```
系统提示 (缓存命中 ✓)
  ├── 身份定义 (不变)
  ├── 平台提示 (不变)
  └── 技能索引 (不变)

用户消息 (每轮不同)
  ├── 用户原始输入
  └── [注入的 context]  ← 钩子返回的内容
```

这确保了系统提示的 prompt cache 不会因为动态注入内容而失效。

## 配置与操作

### 禁用插件

```yaml
# config.yaml
plugins:
  disabled: ["some-plugin", "another-plugin"]
```

### 项目插件

```bash
export HERMES_ENABLE_PROJECT_PLUGINS=true
```

### 安装 pip 插件

```bash
# 插件包在 pyproject.toml 中声明:
# [project.entry-points."hermes_agent.plugins"]
# my-plugin = "my_plugin:register"

pip install hermes-agent-my-plugin
```

## 与其他系统的关系

- [[tool-registry-architecture]] — 插件通过 registry.register() 注册工具
- [[mcp-and-plugins]] — MCP 是另一种工具发现机制，与插件系统互补
- [[messaging-gateway-architecture]] — Gateway Hooks 在网关生命周期中触发
- [[model-tools-dispatch]] — pre/post_tool_call 钩子在 handle_function_call 中调用

---
title: Model Tools 工具编排与调度架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, tool, toolset]
sources: [model_tools.py, tools/registry.py, toolsets.py]
---

# Model Tools — 工具编排与调度架构

## 概述

Model Tools 位于 `model_tools.py`（22KB/577行），是 Tool Registry 之上的**轻量编排层**。它负责触发工具发现、过滤工具集、处理异步桥接、执行函数调用分发。

核心理念：**model_tools.py 不再维护自己的数据结构——所有数据来自 Tool Registry。**

## 架构原理

### 文件依赖链

```
tools/registry.py  (零外部依赖 — 被所有工具文件导入)
       ↑
tools/*.py  (每个文件在模块级别调用 registry.register())
       ↑
model_tools.py  (导入 registry + 触发 _discover_tools())
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

### 公共 API（向后兼容）

```python
# 这些 API 签名从原始 2400 行版本保留，下游代码直接使用
get_tool_definitions(enabled, disabled, quiet) → list
handle_function_call(name, args, task_id, user_task) → str
TOOL_TO_TOOLSET_MAP: dict          # 供 batch_runner.py 使用
TOOLSET_REQUIREMENTS: dict         # 供 cli.py, doctor.py 使用
get_all_tool_names() → list
get_available_toolsets() → dict
check_tool_availability(quiet) → tuple
```

## 核心组件

### 1. 异步桥接（_run_async）

这是 model_tools.py 最重要的基础设施——**同步到异步转换的单一真相源**：

```python
def _run_async(coro):
    """
    三种运行路径:
    
    1. 已有运行中的事件循环 (gateway/RL env)
       → 启动独立线程 + asyncio.run()，避免冲突
    
    2. 工作线程 (delegate_task 的 ThreadPoolExecutor)
       → 使用线程级持久循环 (_get_worker_loop)
       → 避免与主线程共享循环，同时防止 GC 关闭循环
    
    3. 主线程 (CLI 常规路径)
       → 使用全局持久循环 (_get_tool_loop)
       → 缓存的 httpx/AsyncOpenAI 客户端保持绑定到活跃循环
    """
```

**为什么不用 asyncio.run()**：`asyncio.run()` 创建循环、运行协程、然后**关闭**循环。但缓存的 httpx/AsyncOpenAI 客户端仍绑定到已关闭的循环，GC 时触发 `RuntimeError: Event loop is closed`。

### 2. 工具发现（_discover_tools）

```python
def _discover_tools():
    """导入所有工具模块，触发它们的 registry.register() 调用"""
    _modules = [
        "tools.web_tools",
        "tools.terminal_tool",
        "tools.file_tools",
        "tools.browser_tool",
        "tools.code_execution_tool",
        "tools.delegate_tool",
        # ... 20 个工具模块
    ]
    for mod_name in _modules:
        try:
            importlib.import_module(mod_name)
        except Exception:
            pass  # 可选工具导入失败不影响其他工具

# 注意：MCP 工具发现不在 _discover_tools() 的模块列表中，
# 而是在 _discover_tools() 外部单独处理（约 lines 173-177）：
#   from tools.mcp_tool import discover_mcp_tools
#   discover_mcp_tools()
```

**三层发现机制**：
1. **静态导入**：`_discover_tools()` 导入预定义模块列表
2. **MCP 发现**：从外部 MCP 服务器动态发现工具
3. **插件发现**：从用户/项目/pip 插件发现工具

### 3. 工具定义获取（get_tool_definitions）

```python
def get_tool_definitions(enabled_toolsets, disabled_toolsets, quiet_mode):
    """
    1. 根据 toolset 过滤确定要包含的工具名
    2. 向 registry 请求 schema（只返回 check_fn 通过的工具）
    3. 动态调整 execute_code schema（只列出可用的沙盒工具）
    4. 动态调整 browser_navigate 描述（web 工具不可用时移除引用）
    5. 记录 _last_resolved_tool_names 供 downstream 使用
    """
```

**关键设计——动态 schema 调整**：

```python
# 问题: execute_code 的 schema 中列出所有可能的沙盒工具
# 但如果 web_search 的 API key 没配置，模型看到 "web_search 可用"
# 就会尝试调用不存在的工具 → hallucination

# 解决: 根据实际可用的工具重建 schema
if "execute_code" in available_tool_names:
    sandbox_enabled = SANDBOX_ALLOWED_TOOLS & available_tool_names
    dynamic_schema = build_execute_code_schema(sandbox_enabled)
```

同样的模式应用于 browser_navigate：

```python
# 当 web_search/web_extract 不可用时，从 browser_navigate 描述中移除
# "prefer web_search or web_extract" 引用
if not {"web_search", "web_extract"} & available_tool_names:
    desc = desc.replace("For simple information retrieval, prefer web_search...", "")
```

### 4. 参数类型强制（coerce_tool_args）

```python
def coerce_tool_args(tool_name, args):
    """
    LLM 经常返回:
    - 数字作为字符串: "42" 而非 42
    - 布尔值作为字符串: "true" 而非 true
    
    对比 JSON Schema 并安全转换类型
    """
    # 支持: integer, number, boolean, 联合类型 [integer, string]
    # 安全: 转换失败保留原始值
```

### 5. 函数调用分发（handle_function_call）

```python
def handle_function_call(function_name, function_args, task_id, ...):
    """
    1. 参数类型强制 (coerce_tool_args)
    2. 通知 read-loop tracker (重置 read_file 连续计数器)
    3. 拦截 Agent 级工具 (todo, memory, session_search, delegate_task)
    4. 触发 pre_tool_call 插件钩子
    5. 分发到 registry.dispatch()
    6. 触发 post_tool_call 插件钩子
    """
```

**Agent 级工具拦截**：

```python
_AGENT_LOOP_TOOLS = {"todo", "memory", "session_search", "delegate_task"}

if function_name in _AGENT_LOOP_TOOLS:
    return json.dumps({"error": f"{function_name} must be handled by the agent loop"})
```

这些工具需要 Agent 级状态（TodoStore, MemoryStore 等），在 `run_agent.py` 中直接处理。

### 6. 向后兼容映射

```python
_LEGACY_TOOLSET_MAP = {
    "web_tools": ["web_search", "web_extract"],
    "terminal_tools": ["terminal"],
    "browser_tools": ["browser_navigate", "browser_snapshot", ...],
    "rl_tools": ["rl_list_environments", "rl_select_environment", ...],
    # ...
}
```

旧的 toolset 名称（如 `"web_tools"`）自动映射到新的工具名列表。

## 设计优越性

### 从 2400 行到 577 行

| 指标 | 重构前 | 重构后 |
|---|---|---|
| 代码行数 | 2400+ | 577 |
| 数据结构 | 平行维护多个 dict | 全部委托给 Registry |
| 可用性检查 | 分散在 model_tools.py | Registry 集中处理 |
| 异步桥接 | 多处复制 | 单一 _run_async() |
| 测试难度 | 难以 mock | Registry 可替换 |

### 动态 Schema 调整的优越性

传统的静态 schema 会导致模型看到不可用的工具引用。Model Tools 通过**运行时动态调整**确保：
- execute_code 只列出当前可用的沙盒工具
- browser_navigate 只在 web 工具可用时建议优先使用它们
- 所有 cross-tool 引用都基于实际可用状态

## 与其他系统的关系

- [[tool-registry-architecture]] — 所有数据来自 Registry
- [[toolsets-system]] — 工具集解析和验证通过 toolsets.py
- [[large-tool-result-handling]] — execute_code schema 动态调整
- [[mcp-and-plugins]] — MCP 和插件工具通过 discover 机制集成

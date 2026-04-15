---
title: Tool Registry 工具注册系统架构
created: 2026-04-08
updated: 2026-04-15
type: concept
tags: [tool, toolset, tool-registry, architecture, component]
sources: [tools/registry.py, model_tools.py]
---

# Tool Registry — 工具注册系统架构

## 概述

Tool Registry 是 Hermes Agent 工具系统的**中央骨架**，位于 `tools/registry.py`（275行/10KB）。它实现了**声明式工具注册 + 集中式调度**的设计模式，取代了早期 `model_tools.py` 中分散维护的平行数据结构。

所有工具文件（`tools/*.py`）在模块导入时通过 `registry.register()` 自动注册，`model_tools.py` 只负责查询注册表并触发发现流程。

## 架构原理

### 导入链（循环导入安全）

```
tools/registry.py  (零外部依赖 — 被所有工具文件导入)
       ↑
tools/*.py  (每个文件在模块级别调用 registry.register())
       ↑
model_tools.py  (导入 registry + 触发 _discover_tools())
       ↑
run_agent.py, cli.py, batch_runner.py
```

这个设计**完全避免了循环导入**问题：registry 不导入任何工具文件，工具文件只导入 registry，model_tools 是唯一同时导入 registry 和所有工具的模块。

### 核心数据结构

```python
class ToolEntry:
    """单个工具的元数据"""
    __slots__ = (
        "name", "toolset", "schema", "handler", "check_fn",
        "requires_env", "is_async", "description", "emoji",
    )

class ToolRegistry:
    """单例注册表，收集所有工具的 schema + handler"""
    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}         # 工具名 → 元数据
        self._toolset_checks: Dict[str, Callable] = {}  # toolset → 检查函数
```

**设计亮点**：使用 `__slots__` 减少内存开销（每个 ToolEntry 约节省 40% 内存），这在注册 100+ 工具时效果显著。

### 自动发现内置工具（2026-04-14）

早期 `model_tools.py` 维护一个 hardcoded 的工具 import 列表,添加新工具需要同时改两个文件。现在 `tools/registry.py` 提供 `discover_builtin_tools()`,由 `model_tools.py` 在启动时调用:

```python
def discover_builtin_tools(tools_dir=None) -> List[str]:
    """扫描 tools/*.py,导入所有自注册工具模块"""
    tools_path = Path(tools_dir) or Path(__file__).resolve().parent
    module_names = [
        f"tools.{path.stem}"
        for path in sorted(tools_path.glob("*.py"))
        if path.name not in {"__init__.py", "registry.py", "mcp_tool.py"}
        and _module_registers_tools(path)  # AST 检查
    ]
    # importlib.import_module() 每个,触发模块级 registry.register()
```

**AST 级过滤**:`_module_registers_tools()` 用 `ast.parse` 解析模块,只在**模块顶层**检测到 `registry.register(...)` 调用才会 import。这样:
- 普通工具文件(`tools/terminal_tool.py` 等)会被识别并加载
- 辅助模块(不在顶层注册工具)被跳过
- 帮助函数内部的 `registry.register()` 调用不会被误判

**豁免列表**:`__init__.py`、`registry.py` 本身、`mcp_tool.py`(MCP 工具按需动态加载,不走这个路径)。

**添加新工具流程简化**:以前要改 3 处(工具文件 + `model_tools.py` import + toolsets 定义),现在只要两处(工具文件 + toolsets 定义),auto-discovery 自动拿起新文件。

## 核心操作

### 1. 注册（register）

每个工具文件在导入时自动注册：

```python
# tools/terminal_tool.py 中
registry.register(
    name="terminal",
    toolset="terminal",
    schema={"name": "terminal", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: terminal_tool(...),
    check_fn=lambda: True,           # 可用性检查
    requires_env=[],                 # 环境变量依赖
    is_async=False,
)
```

- **名称冲突检测**：如果同名工具属于不同 toolset，发出 warning 并覆盖
- **check_fn 缓存**：每个 toolset 只记录第一个 check_fn，避免重复检查

### 2. 可用性检查（get_definitions）

返回 OpenAI 格式的工具 schema 列表，仅包含通过 check_fn 的工具：

```python
def get_definitions(self, tool_names: Set[str], quiet: bool = False) -> List[dict]:
    # 缓存 check_fn 结果 — 同一 toolset 只检查一次
    check_results: Dict[Callable, bool] = {}
    for name in sorted(tool_names):
        entry = self._tools.get(name)
        if entry.check_fn:
            if entry.check_fn not in check_results:
                check_results[entry.check_fn] = bool(entry.check_fn())
            if not check_results[entry.check_fn]:
                continue  # 跳过不可用工具
        result.append({"type": "function", "function": {**entry.schema, "name": entry.name}})
    return result
```

**优越性**：
- **按需过滤**：只有环境依赖满足的工具才会被发送给 LLM，避免模型调用不存在的工具
- **检查缓存**：同一 toolset 的 check_fn 只执行一次，而非每个工具各执行一次
- **静默模式**：`quiet=True` 抑制调试日志，适合批量查询

### 3. 调度执行（dispatch）

```python
def dispatch(self, name: str, args: dict, **kwargs) -> str:
    entry = self._tools.get(name)
    if not entry:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        if entry.is_async:
            from model_tools import _run_async
            return _run_async(entry.handler(args, **kwargs))
        return entry.handler(args, **kwargs)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {type(e).__name__}: {e}"})
```

**优越性**：
- **统一错误格式**：所有异常被捕获并返回 `{"error": "..."}` JSON，保证 LLM 能解析
- **异步桥接**：自动检测 `is_async` 标志并通过 `_run_async` 桥接，调用者无需关心
- **未知工具安全失败**：返回 JSON 错误而非抛出异常

### 4. 动态注销（deregister）

```python
def deregister(self, name: str) -> None:
    entry = self._tools.pop(name, None)
    # 如果该 toolset 没有其他工具了，清理 check_fn
    if entry.toolset in self._toolset_checks and not any(
        e.toolset == entry.toolset for e in self._tools.values()
    ):
        self._toolset_checks.pop(entry.toolset, None)
```

**使用场景**：MCP 动态工具发现 — 当 MCP 服务器发送 `notifications/tools/list_changed` 时，需要 nuke-and-repave 旧工具并重新注册。

### 5. 查询辅助方法

| 方法 | 用途 |
|---|---|
| `get_all_tool_names()` | 返回所有已注册工具名（排序） |
| `get_schema(name)` | 绕过 check_fn 获取原始 schema，用于 token 估算 |
| `get_toolset_for_tool(name)` | 查询工具所属 toolset |
| `get_emoji(name)` | 获取工具对应的 emoji |
| `get_tool_to_toolset_map()` | 返回 `{tool_name: toolset_name}` 映射 |
| `is_toolset_available(toolset)` | 检查 toolset 是否满足要求 |
| `check_toolset_requirements()` | 返回所有 toolset 的可用性状态 |
| `get_available_toolsets()` | 返回 toolset 元数据（工具列表、环境依赖等） |
| `check_tool_availability()` | 返回可用/不可用 toolset 分类 |

## 设计优越性

### 对比旧架构

| 维度 | 旧方案（分散在 model_tools.py） | 新方案（Tool Registry） |
|---|---|---|
| 数据结构 | 平行维护多个 dict | 单一注册表 |
| 循环导入 | 容易出错 | 零依赖，导入安全 |
| 扩展性 | 添加工具需改 model_tools.py | 只需在工具文件调用 register() |
| 动态发现 | 不支持 | 支持 deregister + 重新注册 |
| 测试 | 难以 mock | 单例可替换 |
| 可用性检查 | 分散逻辑 | 集中缓存 |

### 单一职责原则

- **Registry**：只管注册、查询、调度
- **Tool files**：只管实现和注册自己
- **Model tools**：只管发现和路由
- **Run agent**：只管执行循环

每个模块职责清晰，依赖方向是单向的。

## 配置与操作

### 添加新工具

1. 在 `tools/your_tool.py` 中实现工具函数
2. 在文件末尾调用 `registry.register(...)`
3. 在 `hermes_cli/toolsets.py` 中添加工具集

> 注意:**不再需要**手改 `model_tools.py` 的 import 列表。`discover_builtin_tools()` 会在启动时扫描 `tools/*.py`,只要顶层有 `registry.register(...)` 调用,模块就会被自动 import。

### 查看已注册工具

```python
from tools.registry import registry
print(registry.get_all_tool_names())
print(registry.get_tool_to_toolset_map())
```

### 查看工具集可用性

```python
print(registry.check_toolset_requirements())
# 输出: {'terminal': True, 'web': False, 'browser': True, ...}
```

## 与其他系统的关系

- [[toolsets-system]] — Registry 按 toolset 组织工具
- [[model-tools-dispatch]] — model_tools.py 通过 Registry 发现工具
- [[mcp-and-plugins]] — MCP 使用 deregister/register 实现动态工具发现
- [[large-tool-result-handling]] — 调度结果经过统一错误格式处理
- [[fuzzy-matching-engine]] — patch 工具使用的 8 层模糊匹配引擎
- [[code-execution-sandbox]] — execute_code 沙箱工具

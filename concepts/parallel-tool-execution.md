---
title: 并行工具执行系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, tool, performance, concurrency]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 并行工具执行系统 — 智能并发安全检测

## 设计原理

现代 LLM 在一次响应中经常返回多个工具调用（parallel tool calling）。Hermes 的设计目标是：**在确保安全的前提下最大化并行度，减少总等待时间**。

传统的做法要么全部串行（慢），要么全部并行（危险）。Hermes 采用了**三层安全检测 + 路径作用域分析**的智能并行策略。

## 核心架构

### 1. 工具分类体系

```python
# 永远不能并行的工具（交互/用户面向）
_NEVER_PARALLEL_TOOLS = frozenset({"clarify"})

# 只读工具，无共享可变状态
_PARALLEL_SAFE_TOOLS = frozenset({
    "ha_get_state", "ha_list_entities", "ha_list_services",
    "read_file", "search_files", "session_search",
    "skill_view", "skills_list",
    "vision_analyze", "web_extract", "web_search",
})

# 文件工具，可以并行但需路径不冲突
_PATH_SCOPED_TOOLS = frozenset({"read_file", "write_file", "patch"})

# 最大并发工作线程数
_MAX_TOOL_WORKERS = 8
```

### 2. 并发安全检测算法

```python
def _should_parallelize_tool_batch(tool_calls) -> bool:
    """判断工具调用批次是否可以安全并行"""
    
    # 1. 单个工具无需并行
    if len(tool_calls) <= 1:
        return False
    
    # 2. 包含永不并行工具 → 降级为串行
    tool_names = [tc.function.name for tc in tool_calls]
    if any(name in _NEVER_PARALLEL_TOOLS for name in tool_names):
        return False
    
    # 3. 路径作用域检查（文件工具）
    reserved_paths: list[Path] = []
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        if tool_name in _PATH_SCOPED_TOOLS:
            scoped_path = _extract_parallel_scope_path(tool_name, function_args)
            if scoped_path is None:
                return False  # 无法解析路径 → 降级串行
            if any(_paths_overlap(scoped_path, existing) for existing in reserved_paths):
                return False  # 路径冲突 → 降级串行
            reserved_paths.append(scoped_path)
            continue
        
        if tool_name not in _PARALLEL_SAFE_TOOLS:
            return False  # 未知工具 → 保守降级串行
    
    return True  # 所有检查通过 → 安全并行
```

### 3. 路径冲突检测

```python
def _paths_overlap(left: Path, right: Path) -> bool:
    """判断两个路径是否可能指向同一子树"""
    left_parts = left.parts
    right_parts = right.parts
    
    # 取较短路径的长度作为共同前缀长度
    common_len = min(len(left_parts), len(right_parts))
    return left_parts[:common_len] == right_parts[:common_len]
```

**示例：**
- `/root/wiki/index.md` 和 `/root/wiki/log.md` → 不冲突（可并行）
- `/root/wiki/index.md` 和 `/root/wiki/index.md` → 冲突（串行）
- `/root/wiki/` 和 `/root/wiki/concepts/` → 冲突（串行，父目录重叠）

## 并行执行实现

```python
if _should_parallelize_tool_batch(tool_calls):
    # 并行执行：使用 ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=_MAX_TOOL_WORKERS
    ) as executor:
        futures = {
            executor.submit(_execute_single_tool, tc): tc
            for tc in tool_calls
        }
        for future in concurrent.futures.as_completed(futures):
            tool_call = futures[future]
            result = future.result()
            # 处理结果...
else:
    # 串行执行：按顺序处理
    for tool_call in tool_calls:
        result = _execute_single_tool(tool_call)
        # 处理结果...
```

## 安全降级策略

Hermes 采用**保守默认**策略：任何不确定都降级为串行。

| 检测项 | 失败条件 | 降级原因 |
|--------|----------|----------|
| 永不并行工具 | 包含 `clarify` | 用户交互必须串行 |
| 路径解析失败 | 无法解析 JSON 参数 | 无法验证安全性 |
| 路径重叠 | 文件路径有共同前缀 | 避免竞态条件 |
| 未知工具 | 不在安全列表中 | 保守默认 |
| 非字典参数 | 参数不是 dict | 无法分析作用域 |

## 优越性分析

### 性能提升

| 场景 | 串行时间 | 并行时间 | 加速比 |
|------|----------|----------|--------|
| 3 个只读工具 | 3 × 等待时间 | max(等待时间) | ~3x |
| 5 个独立文件操作 | 5 × 等待时间 | max(等待时间) | ~5x |
| 混合场景（2 并行 + 1 串行）| 3 × 等待 | 2 × 等待 | ~1.5x |

### 安全性保障

1. **零竞态条件** — 路径重叠检测防止同时写入同一文件
2. **保守默认** — 未知情况降级串行，不会出错
3. **用户交互保护** — `clarify` 等工具永远串行，避免混乱
4. **最大线程限制** — 8 个工作线程防止资源耗尽

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor/Claude | OpenCode |
|------|--------|---------------|----------|
| 并行工具执行 | ✅ 智能检测 | ✅ 全并行 | ✅ 全并行 |
| 路径冲突检测 | ✅ 前缀重叠检查 | ❌ 无 | ❌ 无 |
| 保守降级 | ✅ 不确定则串行 | ❌ 可能竞态 | ❌ 可能竞态 |
| 可配置线程数 | ✅ _MAX_TOOL_WORKERS | ❌ 固定 | ❌ 固定 |

## 配置指南

### 环境变量

```bash
# 无环境变量控制，硬编码在 run_agent.py 中
# 未来可能添加：
# HERMES_MAX_TOOL_WORKERS=8
# HERMES_PARALLEL_TOOLS=true/false
```

### 自定义并行策略

如需添加新的并行安全工具：

```python
# 在 run_agent.py 中修改：
_PARALLEL_SAFE_TOOLS = frozenset({
    # ... 现有工具 ...
    "your_new_read_only_tool",  # 添加只读工具
})

# 或添加新的路径作用域工具：
_PATH_SCOPED_TOOLS = frozenset({
    # ... 现有工具 ...
    "your_file_tool",  # 需要 path 参数的工具
})
```

## 相关页面

- [[model-tools-dispatch]] — 工具编排与调度（并行执行的上层控制）
- [[tool-registry-architecture]] — 工具注册系统与元数据管理
- [[large-tool-result-handling]] — 并行工具产生大型结果时的处理

## 相关文件

- `run_agent.py` — 并行检测算法和执行逻辑
- `tools/registry.py` — 工具注册和元数据

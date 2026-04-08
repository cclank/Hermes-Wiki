---
title: 迭代预算与子代理委派系统
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, agent, delegation, performance]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# 迭代预算与子代理委派系统

## 设计原理

Hermes 需要解决两个核心问题：
1. **防止无限循环** — Agent 可能在工具调用中陷入死循环
2. **并行处理复杂任务** — 单个 Agent 串行处理太慢，需要委派给多个子代理

解决方案：**独立的迭代预算系统 + 子代理委派机制**。

## 迭代预算系统

### IterationBudget 类

```python
class IterationBudget:
    """线程安全的迭代计数器"""
    
    def __init__(self, max_total: int):
        self.max_total = max_total  # 最大迭代次数（默认 90）
        self._used = 0
        self._lock = threading.Lock()  # 线程安全
    
    def consume(self) -> bool:
        """尝试消费一次迭代，返回是否允许"""
        with self._lock:
            if self._used >= self.max_total:
                return False
            self._used += 1
            return True
    
    def refund(self) -> None:
        """退还一次迭代（用于 execute_code 等优化路径）"""
        with self._lock:
            if self._used > 0:
                self._used -= 1
    
    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self.max_total - self._used)
```

### 预算压力警告

当 Agent 接近预算限制时，系统会自动注入警告：

```python
# 70% — 开始提醒
self._budget_caution_threshold = 0.7

# 90% — 紧急警告
self._budget_warning_threshold = 0.9
```

警告注入到工具结果的 JSON 中（不是单独的消息），这样：
- 不会破坏消息结构
- 不会使 Anthropic prefix cache 失效
- 模型会收到"开始收尾"或"立即响应"的信号

## 子代理委派系统

### 委派工具（delegate_task）

```python
def delegate_task(
    goal: str,                    # 任务目标（必须自包含）
    context: str = "",            # 背景信息
    toolsets: list = None,        # 启用的工具集
    max_iterations: int = 50,     # 子代理最大迭代次数
    tasks: list = None,           # 批量模式（最多 3 个并行任务）
) -> dict:
```

### 子代理创建流程

```python
def _build_child_agent(parent, goal, context, toolsets, max_iterations, task_index):
    # 1. 工具集限制
    parent_tools = set(parent.valid_tool_names)
    if toolsets:
        # 解析工具集
        child_tools = resolve_multiple_toolsets(toolsets)
        # 交集：子代理不能获得父代理没有的工具
        child_tools = child_tools & parent_tools
    else:
        child_tools = parent_tools
    
    # 2. 移除交互工具（子代理不能问用户问题）
    child_tools -= {"clarify", "delegate_task"}
    
    # 3. 继承认证信息
    api_key = parent.api_key
    base_url = parent.base_url
    
    # 4. 独立的迭代预算
    child_budget = IterationBudget(min(max_iterations, 50))
    
    # 5. 创建子代理
    child = AIAgent(
        model=parent.model,
        base_url=base_url,
        api_key=api_key,
        max_iterations=max_iterations,
        enabled_toolsets=toolsets,
        platform=parent.platform,
        session_id=f"{parent.session_id}-sub-{task_index}",
        iteration_budget=child_budget,  # 独立预算
        log_prefix=f"[subagent-{task_index}]",
        # ... 更多参数
    )
    
    return child
```

### 并行委派（批量模式）

```python
# 支持最多 3 个任务并行
if tasks and len(tasks) <= 3:
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {
            executor.submit(_run_subagent, task, i): i
            for i, task in enumerate(tasks)
        }
        results = {}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
    return results
```

### 预算隔离

关键设计：**父代理和子代理有独立的预算**。

```python
# 父代理预算
parent_budget = IterationBudget(90)  # 默认 90

# 每个子代理独立预算
child_budget = IterationBudget(50)  # 默认 50，可配置

# 这意味着：父代理 + N 个子代理的总迭代次数可以超过 90
# 用户通过 delegation.max_iterations 控制每个子代理的上限
```

### execute_code 优化

`execute_code` 工具（Python 脚本编程式调用工具）会**退还预算**：

```python
# execute_code 执行后
budget.refund()  # 不消耗迭代次数
```

这是因为 execute_code 可以在一次调用中完成多个工具调用，不应该消耗宝贵的迭代预算。

## 中断传播

```python
# 父代理可以中断所有子代理
def _propagate_interrupt(self):
    with self._active_children_lock:
        for child in self._active_children:
            child._interrupt_requested = True
```

## 上下文隔离

子代理**不知道**父代理的对话历史：

```python
# 子代理的系统提示
child_system_prompt = f"""
You are a focused subagent working on a specific delegated task.

Task: {goal}
Context: {context}

You have your own conversation, terminal session, and toolset.
The parent agent knows nothing about your internal process — only the summary matters.
"""

# 不传递父代理的 conversation_history
child.run_conversation(goal)  # 只有任务目标
```

## 配置指南

### config.yaml

```yaml
delegation:
  max_iterations: 50      # 每个子代理的最大迭代次数
  base_url: ""            # 可选：子代理使用不同的 API 端点
  model: ""               # 可选：子代理使用不同的模型（如便宜/快速的模型）
```

### 使用场景

**适合委派的任务：**
- 独立的子任务可以并行处理
- 需要不同工具集的任务
- 长时间运行的调试/分析任务

**不适合委派的任务：**
- 需要与用户交互的任务（子代理不能用 clarify）
- 简单的一步任务（委派开销大于收益）
- 需要完整上下文的复杂推理

## 优越性分析

### 性能提升

| 场景 | 串行时间 | 并行委派时间 | 加速比 |
|------|----------|--------------|--------|
| 3 个独立研究任务 | 3 × T | T | ~3x |
| 代码审查 + 测试 | T1 + T2 | max(T1, T2) | ~2x |
| 多文件分析 | N × T | T | ~Nx |

### 成本优化

```yaml
# 父代理使用强大模型
model: "anthropic/claude-opus-4.6"

# 子代理使用便宜模型
delegation:
  model: "openai/gpt-4o-mini"
  base_url: "https://openrouter.ai/api/v1"
```

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | OpenCode |
|------|--------|--------|----------|
| 子代理委派 | ✅ 独立预算 | ❌ 无 | ❌ 无 |
| 并行任务 | ✅ 最多 3 个 | ❌ 无 | ❌ 无 |
| 预算隔离 | ✅ 独立计数 | N/A | N/A |
| 模型路由 | ✅ 子代理可用不同模型 | N/A | N/A |
| 工具隔离 | ✅ 交集限制 | N/A | N/A |
| 中断传播 | ✅ 父→子 | N/A | N/A |

## 相关文件

- `run_agent.py` — IterationBudget 类
- `tools/delegate_tool.py` — 委派工具实现
- `tools/code_execution_tool.py` — execute_code 工具

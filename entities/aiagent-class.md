---
title: AIAgent Class
created: 2026-04-07
updated: 2026-05-17
type: entity
tags: [component, agent, module]
sources: [hermes-agent 源码分析 2026-04-07]
---

# AIAgent Class

## 位置

`AIAgent` 类仍定义在 `run_agent.py:326`，但 `run_agent.py` 不再是单块实现：核心逻辑已抽到 `agent/` 子模块。`__init__`（`run_agent.py:349`）是一个转发器，委派给 `agent/agent_init.py` 的 `init_agent()`；`run_conversation`（`run_agent.py:3840`）同样是转发器，委派给 `agent/conversation_loop.py` 的 `run_conversation()`。

## 概述

AIAgent 是 Hermes Agent 的核心对话循环类，负责管理 LLM 交互、工具调用和会话状态。

## 构造函数

```python
class AIAgent:
    def __init__(self,
        model: str = "",  # 默认空字符串，运行时解析为 "anthropic/claude-opus-4.6"
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,           # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        # ... 更多参数：provider, api_mode, callbacks, routing params
    ):
```

## 核心方法

### `chat(self, message: str, stream_callback: Optional[callable] = None) -> str`

简单接口，返回最终响应字符串。

### `run_conversation(self, user_message: str, system_message: str = None, conversation_history: List[Dict] = None, task_id: str = None, stream_callback: Optional[callable] = None, persist_user_message: Optional[str] = None) -> Dict[str, Any]`

完整接口，返回 `{final_response, messages}` 字典。

## 对话循环

对话循环本身现在实现在 `agent/conversation_loop.py`，`run_agent.py` 仅保留转发入口。下面的代码现已位于 `agent/conversation_loop.py`：

```python
while api_call_count < self.max_iterations and self.iteration_budget.consume():  # consume() 原子地检查并递减剩余预算
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tool_schemas
    )
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id, tool_call.id, session_id, user_task, enabled_tools)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

## 关键特性

- **完全同步** — 不使用 asyncio
- **工具循环** — 支持多轮工具调用
- **迭代预算** — 控制最大 API 调用次数
- **平台感知** — 根据平台注入不同提示
- **记忆集成** — 自动加载和注入记忆
- **技能集成** - 构建技能索引
- **上下文压缩** — 自动管理上下文长度
- **模块化实现** — 类壳定义在 `run_agent.py`，初始化、对话循环、系统提示、工具执行、上下文压缩等核心逻辑均已抽到 `agent/` 子模块，`run_agent.py` 中的对应方法多为转发器

## 相关页面

- [[agent-loop-and-prompt-assembly]] — Agent 核心循环与系统提示组装
- [[multi-agent-architecture]] — 子代理委派与迭代预算系统
- [[prompt-builder-architecture]] — 系统提示构建架构

## 相关文件

- `run_agent.py` — `AIAgent` 类定义（`run_agent.py:326`）；`__init__`/`run_conversation`/`_compress_context` 等为转发器
- `agent/agent_init.py` — `init_agent()`，AIAgent 初始化逻辑
- `agent/conversation_loop.py` — `run_conversation()`，对话循环实现
- `agent/system_prompt.py` — 系统提示三层组装编排
- `agent/tool_executor.py` — 工具执行
- `agent/conversation_compression.py` — 上下文压缩驱动逻辑
- `model_tools.py` — 工具编排
- `agent/prompt_builder.py` — 系统提示组件构建器

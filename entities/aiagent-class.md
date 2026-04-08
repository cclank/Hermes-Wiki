---
title: AIAgent Class
created: 2026-04-07
updated: 2026-04-07
type: entity
tags: [component, agent, module]
sources: [hermes-agent 源码分析 2026-04-07]
---

# AIAgent Class

## 位置

`run_agent.py`

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

## 相关页面

- [[agent-loop-and-prompt-assembly]] — Agent 核心循环与系统提示组装
- [[multi-agent-architecture]] — 子代理委派与迭代预算系统
- [[prompt-builder-architecture]] — 系统提示构建架构

## 相关文件

- `run_agent.py` — 实现
- `model_tools.py` — 工具编排
- `agent/prompt_builder.py` — 系统提示构建

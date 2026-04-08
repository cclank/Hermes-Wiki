---
title: Context Compression
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [context-compression, architecture, agent-loop]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Context Compression

## Overview

上下文压缩系统自动管理对话历史长度，防止超出模型上下文窗口限制。

## ContextCompressor

```python
# agent/context_compressor.py
class ContextCompressor:
    def __init__(self, max_tokens, compression_ratio=0.5):
        ...
    
    def compress(self, messages, keep_recent=True):
        """压缩对话历史"""
```

## 压缩策略

### 1. 边界检测

系统持续跟踪当前 token 使用量，当接近限制时触发压缩。

### 2. 保留最新消息

压缩时保留最近的 N 条消息（通常是最近的用户消息和助手响应），压缩较早的对话。

### 3. 摘要生成

使用辅助 LLM（auxiliary_client）生成对话摘要：

```python
# 使用辅助模型生成摘要
summary = auxiliary_client.chat.completions.create(
    model="claude-sonnet-4",  # 更便宜的模型
    messages=[
        {"role": "system", "content": "Summarize this conversation..."},
        {"role": "user", "content": old_messages_text}
    ]
)
```

## 触发条件

```
while api_call_count < max_iterations and iteration_budget.remaining > 0:
    # 检查 token 预算
    if token_usage > threshold:
        compressed = compressor.compress(messages, keep_recent=True)
        messages = [system_prompt] + [compressed] + recent_messages
```

## 与 Prompt Caching 的交互

Anthropic 的 prompt caching 对系统提示前缀最有效。压缩策略：

1. **保持系统提示不变** — 最大化缓存命中
2. **只压缩对话历史** — 消息部分可变
3. **使用相同的系统提示结构** — 缓存键稳定

## 压缩边界

压缩创建"边界"标记，指示哪些内容被压缩：

```
[Previous conversation compressed - summary follows]

User asked about X. Assistant explained Y and provided Z examples.
User then requested A. Assistant performed B and returned C.

[End compressed summary - recent messages continue below]
```

## 相关文件

- `agent/context_compressor.py` — 压缩实现
- `agent/prompt_caching.py` — Anthropic prompt 缓存
- `agent/auxiliary_client.py` — 辅助 LLM 客户端
- `run_agent.py` — AIAgent 循环中的压缩调用

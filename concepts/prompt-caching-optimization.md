---
title: Prompt 缓存优化与 Anthropic 适配
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, performance, cost-optimization, anthropic]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Prompt 缓存优化与 Anthropic 适配

## 设计原理

Anthropic Claude 模型支持 **Prompt Caching**，可以缓存对话历史的前缀，大幅降低多轮对话的输入成本。Hermes 实现了智能的 `system_and_3` 缓存策略，在最多 4 个断点处设置缓存控制。

## system_and_3 缓存策略

```
对话结构：
[系统提示] ← 断点 1（所有轮次相同）
[用户消息 1]
[助手回复 1] ← 断点 2（滚动窗口）
[用户消息 2]
[助手回复 2] ← 断点 3（滚动窗口）
[用户消息 3]
[助手回复 3] ← 断点 4（滚动窗口）
[用户消息 4] ← 最新（无缓存，每次重新计算）
```

### 核心实现

```python
def apply_anthropic_cache_control(
    api_messages: List[Dict],
    cache_ttl: str = "5m",      # 默认 5 分钟 TTL
    native_anthropic: bool = False,
) -> List[Dict]:
    """应用 system_and_3 缓存策略"""
    
    messages = copy.deepcopy(api_messages)
    marker = {"type": "ephemeral"}
    if cache_ttl == "1h":
        marker["ttl"] = "1h"
    
    breakpoints_used = 0
    
    # 断点 1：系统提示（所有轮次稳定）
    if messages[0].get("role") == "system":
        _apply_cache_marker(messages[0], marker, native_anthropic)
        breakpoints_used += 1
    
    # 断点 2-4：最后 3 个非系统消息（滚动窗口）
    remaining = 4 - breakpoints_used  # Anthropic 最多 4 个断点
    non_sys = [i for i in range(len(messages)) if messages[i].get("role") != "system"]
    for idx in non_sys[-remaining:]:
        _apply_cache_marker(messages[idx], marker, native_anthropic)
    
    return messages
```

### 缓存标记应用

```python
def _apply_cache_marker(msg: dict, cache_marker: dict, native_anthropic: bool = False):
    """为消息添加 cache_control 标记"""
    
    role = msg.get("role", "")
    content = msg.get("content")
    
    if role == "tool":
        if native_anthropic:
            msg["cache_control"] = cache_marker
        return
    
    if content is None or content == "":
        msg["cache_control"] = cache_marker
        return
    
    if isinstance(content, str):
        # 字符串内容 → 转换为数组格式
        msg["content"] = [
            {"type": "text", "text": content, "cache_control": cache_marker}
        ]
        return
    
    if isinstance(content, list) and content:
        # 多部分内容 → 标记最后一部分
        last = content[-1]
        if isinstance(last, dict):
            last["cache_control"] = cache_marker
```

## 自动启用条件

```python
# run_agent.py __init__()
is_openrouter = self._is_openrouter_url()
is_claude = "claude" in self.model.lower()
is_native_anthropic = self.api_mode == "anthropic_messages"

# 自动启用缓存
self._use_prompt_caching = (is_openrouter and is_claude) or is_native_anthropic
self._cache_ttl = "5m"  # 默认 5 分钟 TTL（1.25x 写入成本）
```

### 启用场景

| 场景 | 启用缓存 | 原因 |
|------|----------|------|
| OpenRouter + Claude | ✅ | OpenRouter 支持 Anthropic 缓存 |
| 原生 Anthropic API | ✅ | 原生支持 |
| OpenRouter + GPT | ❌ | OpenAI 不支持此缓存 |
| 其他提供商 | ❌ | 不兼容 |

## 缓存 TTL 选择

```python
# 5m TTL（默认）
# 写入成本：1.25x 正常输入
# 读取成本：0.1x 正常输入（90% 节省）
# 适用场景：多轮对话，5 分钟内多次调用

# 1h TTL
# 写入成本：2x 正常输入
# 读取成本：0.1x 正常输入
# 适用场景：长时间运行的任务
```

## 成本优化效果

### 示例：10 轮对话

**无缓存：**
```
每轮输入：10,000 tokens
10 轮总输入：100,000 tokens
成本：$0.30（假设 $3/MTok）
```

**有缓存（system_and_3）：**
```
第 1 轮：10,000 tokens（写入缓存）→ $0.0375（1.25x）
第 2 轮：10,000 tokens（写入缓存）→ $0.0375
第 3 轮：10,000 tokens（写入缓存）→ $0.0375
第 4-10 轮：每轮 7,500 tokens 读取缓存 → $0.0075 × 7
第 4-10 轮：每轮 2,500 tokens 新输入 → $0.0075 × 7

总成本：约 $0.15（节省 50%+）
轮次越多，节省越大
```

### 实际节省

| 对话轮次 | 无缓存成本 | 有缓存成本 | 节省 |
|----------|------------|------------|------|
| 5 轮 | $0.15 | $0.10 | ~33% |
| 10 轮 | $0.30 | $0.15 | ~50% |
| 20 轮 | $0.60 | $0.20 | ~67% |
| 50 轮 | $1.50 | $0.35 | ~77% |

## 与上下文压缩的协同

```python
# 压缩后重建系统提示 → 缓存失效 → 重新缓存
if compression_occurred:
    self._cached_system_prompt = None  # 清除缓存
    # 下次调用会重建系统提示并重新设置缓存断点
```

## 与系统提示缓存的协同

```python
# 系统提示在会话期间保持稳定
if self._cached_system_prompt is None:
    self._cached_system_prompt = self._build_system_prompt()
    # 存储到 SessionDB 以便后续轮次重用
    self._session_db.update_system_prompt(self.session_id, self._cached_system_prompt)
else:
    # 继续会话 → 使用存储的系统提示
    # 这样 Anthropic 缓存前缀匹配，命中缓存
    self._cached_system_prompt = stored_prompt
```

## 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | Claude Desktop |
|------|--------|--------|----------------|
| Prompt Caching | ✅ system_and_3 | ✅ 自动 | ✅ 自动 |
| 可配置 TTL | ✅ 5m/1h | ❌ 固定 | ❌ 固定 |
| 成本估算 | ✅ 实时显示 | ❌ 无 | ❌ 无 |
| 压缩后重建 | ✅ 自动清除 | ✅ 自动 | N/A |

## 配置指南

### 启用/禁用

```yaml
# ~/.hermes/config.yaml
agent:
  prompt_caching: true  # 默认启用（Claude 模型）
  cache_ttl: "5m"       # 或 "1h"
```

### 环境变量

```bash
# 无环境变量控制，硬编码在 run_agent.py 中
```

## 相关文件

- `agent/prompt_caching.py` — 缓存控制实现
- `run_agent.py` — 自动启用逻辑
- `agent/context_compressor.py` — 压缩后缓存重建

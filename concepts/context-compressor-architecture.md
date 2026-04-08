---
title: Context Compressor 上下文压缩架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, agent, context-compression]
sources: [agent/context_compressor.py, run_agent.py, hermes_state.py]
---

# Context Compressor — 上下文压缩架构

## 概述

Context Compressor 位于 `agent/context_compressor.py`（30KB/696行），是一个**自动上下文窗口压缩**类。当对话接近模型上下文限制时，使用辅助 LLM（廉价/快速模型）对中间轮次进行结构化摘要，同时保护头部和尾部上下文。

核心理念：**长对话不需要丢弃上下文——用结构化摘要替代旧轮次，保留关键信息。**

## 架构原理

### 压缩算法

```text
算法流程:
  1. 修剪旧工具输出（廉价预处理，无需 LLM）
  2. 保护头部消息（系统提示 + 首轮交互）
  3. 按 token 预算保护尾部（最近 ~20K tokens）
  4. 用结构化 LLM 提示摘要中间轮次
  5. 后续压缩时迭代更新之前的摘要
```

### 对比 v1 的改进

| 改进 | v1 | v2 (当前) |
|---|---|---|
| 摘要模板 | 无结构 | Goal/Progress/Decisions/Files/Next Steps |
| 摘要更新 | 每次从头生成 | 迭代更新（保留旧信息） |
| 尾部保护 | 固定消息数 | Token 预算（按比例缩放） |
| 工具输出修剪 | 无 | 廉价预处理替换旧结果为占位符 |
| 摘要预算 | 固定 | 按压缩内容比例缩放 |
| 工具调用完整性 | 可能丢失 | _sanitize_tool_pairs 修复孤儿对 |

## 核心组件

### 1. Token 预算管理

```python
class ContextCompressor:
    def __init__(self, model, threshold_percent=0.50):
        self.context_length = get_model_context_length(model)
        self.threshold_tokens = int(self.context_length * 0.50)  # 50% 触发
        self.tail_token_budget = int(self.threshold_tokens * 0.20)  # 尾部预算
        self.max_summary_tokens = min(int(self.context_length * 0.05), 12_000)  # 摘要上限
```

**缩放设计**：尾部预算和摘要上限都与模型上下文窗口成比例，大窗口模型获得更丰富的摘要。

### 2. 工具输出修剪（廉价预处理）

```python
def _prune_old_tool_results(messages, protect_tail_count):
    """
    从后向前遍历，保护尾部 protect_tail_count 条消息
    更早的工具结果（内容 > 200 chars）替换为占位符
    返回 (pruned_messages, pruned_count)
    """
```

**效果**：无需 LLM 调用即可减少大量 token。一个大型工具输出可能占数千 token，替换为 50 字符占位符立竿见影。

### 3. 摘要预算计算

```python
def _compute_summary_budget(turns_to_summarize):
    content_tokens = estimate_messages_tokens_rough(turns_to_summarize)
    budget = int(content_tokens * 0.20)  # 压缩到 20%
    return max(2000, min(budget, self.max_summary_tokens))
```

**设计**：摘要预算与待压缩内容成比例，但上下限受控。

### 4. 序列化为摘要文本

```python
def _serialize_for_summary(turns):
    """
    将对话轮次序列化为带标签的文本:
    [TOOL RESULT xxx]: 内容 (截断为 3000 chars: 前2000 + ... + 后800)
    [ASSISTANT]: 内容 + [Tool calls: tool_name(args), ...]
    [USER]: 内容 (截断为 3000 chars)
    """
```

**关键**：包含工具调用名称和参数，使摘要器能保留具体的文件路径、命令和输出。

### 5. 结构化摘要生成

#### 首次压缩

```text
## Goal
[用户要完成什么]

## Constraints & Preferences
[用户偏好、编码风格、约束、重要决策]

## Progress
### Done
[已完成工作 — 包含具体文件路径、命令、结果]
### In Progress
[正在进行的工作]
### Blocked
[遇到的障碍]

## Key Decisions
[重要技术决策及原因]

## Relevant Files
[读取/修改/创建的文件]

## Next Steps
[下一步需要做什么]

## Critical Context
[具体值、错误消息、配置细节等不能丢失的信息]
```

#### 迭代更新

当已有旧摘要时，Prompt 变为：

```text
PREVIOUS SUMMARY: [旧摘要]
NEW TURNS TO INCORPORATE: [新轮次]

更新摘要，保留所有仍有用的旧信息，添加新进展。
将 "In Progress" 标记为 "Done"，仅在明显过时时才移除信息。
```

### 6. 失败冷却机制

```python
_SUMMARY_FAILURE_COOLDOWN_SECONDS = 600  # 10 分钟

def _generate_summary(self, turns):
    if time.monotonic() < self._summary_failure_cooldown_until:
        return None  # 冷却期内跳过
    
    try:
        response = call_llm(task="compression", ...)
        self._summary_failure_cooldown_until = 0.0  # 成功则重置
    except Exception:
        self._summary_failure_cooldown_until = time.monotonic() + 600  # 失败则冷却
```

**设计考量**：如果辅助 LLM 不可用或调用失败，冷却 10 分钟再尝试，避免每轮都浪费资源。

### 7. 工具调用对完整性保障

```python
def _sanitize_tool_pairs(messages):
    """
    修复压缩后孤儿 tool_call / tool_result 对:
    
    故障模式 1: 工具结果引用的 call_id 对应的 assistant tool_call 被移除
    → API 报错 "No tool call found for function call output..."
    → 解决: 删除孤儿结果
    
    故障模式 2: assistant 有 tool_calls 但对应的结果被丢弃
    → API 报错 "every tool_call must be followed by a tool result..."
    → 解决: 插入存根结果 "[Result from earlier conversation]"
    """
```

**重要性**：不修复会导致 API 拒绝整个消息列表，压缩失败。

### 8. 边界对齐

```python
def _align_boundary_forward(messages, idx):
    """如果边界落在 tool result 上，向前推到非工具消息"""

def _align_boundary_backward(messages, idx):
    """如果边界落在 tool call/result 组中间，向后拉回完整包含该组"""
```

**防止数据丢失**：避免拆分 assistant + tool_results 组，否则 `_sanitize_tool_pairs` 会移除尾部孤儿结果导致静默数据丢失。

### 9. 尾部 token 预算保护

```python
def _find_tail_cut_by_tokens(messages, head_end, token_budget):
    """
    从末尾向前累加 token，直到达到预算
    保证至少保护 protect_last_n 条消息
    不切割工具调用组
    如果预算过小（小于固定保护），回退到固定数量保护
    """
```

### 10. 摘要角色选择

```python
# 摘要消息插入时，选择合适的 role 避免连续同角色
if last_head_role in ("assistant", "tool"):
    summary_role = "user"
else:
    summary_role = "assistant"

# 如果选择的角色与尾部冲突，尝试翻转
# 如果两种角色都会造成冲突 → 合并到第一条尾部消息中
```

## 上下文管理全景

### 无限轮对话

Hermes **不限制对话轮数**。没有 `max_history`、没有固定轮数截断。全部对话历史保留在内存中，靠压缩器循环压缩维持：

```text
对话开始 → 消息累积 → 达到上下文窗口 50% → 自动压缩
                                              │
                                        修剪 + 摘要 + 重组
                                              │
                                        继续累积 → 再次达到 50% → 再次压缩 → ...
```

理论上可以无限对话。每次压缩生成迭代更新的摘要，不是从头重新摘要。

### Session 分裂

压缩时会**拆分 session**，目的是保留完整原始消息供 `session_search` 日后检索。

```text
压缩前:
  session "abc" (DB 中已有 msg 0-49 完整原始消息)
  内存中 msg 2-40 即将被压缩成摘要

压缩后:
  session "abc" (结束, reason="compression")
    → DB 中 msg 0-49 完整保留 ← session_search 可搜到原始内容

  session "abc-2" (新建, parent_session_id="abc")
    → 摘要 + 尾部消息 + 后续新消息
    → _last_flushed_db_idx 重置为 0

多次压缩形成链:
  abc → abc-2 → abc-3 → ...
  每一段都是完整的，通过 parent_session_id 链保持血缘
```

**为什么不原地替换？** 如果把压缩后的消息覆盖回同一个 session，DB 里前半段是原始消息、后半段是摘要，session_search 搜到的是不一致的数据。分裂保证每个 session 片段内容完整一致。

### 消息持久化机制

消息**不是实时逐条写入 DB**，而是在退出点批量 flush：

```python
def _flush_messages_to_session_db(self, messages, conversation_history):
    # 增量写入：从上次水位线开始，只写新增消息
    flush_from = max(start_idx, self._last_flushed_db_idx)
    for msg in messages[flush_from:]:
        db.append_message(session_id, role, content, ...)
    self._last_flushed_db_idx = len(messages)  # 更新水位线
```

**触发时机**（代码中 20 个调用点，覆盖所有退出路径）：

| 场景 | 保证 |
|------|------|
| 对话正常完成 | ✅ 写入 |
| API 错误 max retry 耗尽 | ✅ 放弃前写入 |
| 用户中断（Ctrl+C） | ✅ 中断前写入 |
| Rate limit 等待中被中断 | ✅ 写入 |
| 413/context overflow 压缩失败 | ✅ 写入 |
| 工具执行异常 | ✅ 写入 |
| Fallback provider 全部失败 | ✅ 写入 |

**水位线防重复**：`_last_flushed_db_idx` 记录已写入位置。即使多个退出路径重复调用 `_persist_session()`，同一条消息不会写入两次（修复了 issue #860）。

```text
第一次 flush:  messages[0:15] → DB,  水位线 = 15
第二次 flush:  messages[15:23] → DB, 水位线 = 23
第三次 flush:  messages[23:23] → 跳过（无新消息）
```

## 设计优越性

### 对比丢弃旧消息

| 维度 | 丢弃旧消息 | Context Compressor |
|---|---|---|
| 信息保留 | 完全丢失 | 结构化摘要保留关键信息 |
| 连续性 |  Agent 忘记已完成的工作 | 知道进度和决策 |
| 文件追踪 | 丢失 | 列出相关文件 |
| 迭代更新 | 不适用 | 摘要可迭代更新 |
| 用户体验 | Agent 重复工作 | Agent 从摘要接续 |

### 成本效益

压缩使用**辅助 LLM**（廉价模型，如 Gemini 3 Flash），而非主对话模型。典型场景：
- 辅助模型成本：$0.01-0.05/次压缩
- 避免的重复工作成本：远超压缩成本
- 上下文节省：30-70%

## 配置与操作

### 配置参数

```yaml
# config.yaml
compression:
  summary_provider: auto      # 或 openrouter, nous, custom
  summary_model: ""           # 空=自动选择
  threshold_percent: 0.50     # 50% 上下文使用时触发
```

### 环境变量

```bash
# 为压缩任务设置特定模型
export AUXILIARY_COMPRESSION_MODEL=claude-haiku-4-5
export CONTEXT_COMPRESSION_PROVIDER=openrouter
```

### 运行时状态

```python
compressor.get_status()
# 返回: {
#   "last_prompt_tokens": 45000,
#   "threshold_tokens": 65536,
#   "context_length": 131072,
#   "usage_percent": 34,
#   "compression_count": 2
# }
```

## 与 Prompt Caching 的交互

Anthropic 的 prompt caching 对系统提示前缀最有效。压缩策略与缓存协调：

1. **保持系统提示不变** — 最大化缓存命中
2. **只压缩对话历史** — 消息部分可变
3. **使用相同的系统提示结构** — 缓存键稳定

## Agent 循环中的触发

```python
while api_call_count < max_iterations and iteration_budget.remaining > 0:
    # 检查 token 预算
    if token_usage > threshold:
        compressed = compressor.compress(messages, current_tokens=token_usage)
        messages = [system_prompt] + [compressed] + recent_messages
```

## 与其他系统的关系

- [[auxiliary-client-architecture]] — 压缩通过 `call_llm(task="compression")` 调用
- [[smart-model-routing]] — 使用 get_model_context_length() 获取上下文窗口
- [[prompt-builder-architecture]] — 压缩后的消息传给 prompt builder 重建提示
- [[prompt-caching-optimization]] — 压缩策略与 prompt caching 协调
- [[large-tool-result-handling]] — 工具输出修剪与大型结果处理理念相通
- [[session-search-and-sessiondb]] — Session 分裂后原始消息保留在 DB 中供检索
- [[memory-system-architecture]] — 压缩前 flush_memories 和 on_pre_compress 通知

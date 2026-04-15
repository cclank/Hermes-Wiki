---
title: Context Compressor 上下文压缩架构
created: 2026-04-08
updated: 2026-04-15
type: concept
tags: [architecture, module, component, agent, context-compression]
sources: [agent/context_engine.py, agent/context_compressor.py, run_agent.py, hermes_state.py, plugins/context_engine/__init__.py]
---

# Context Compressor — 上下文压缩架构

## 概述

Context Compressor 位于 `agent/context_compressor.py`，是一个**自动上下文窗口压缩**类。当对话接近模型上下文限制时，使用辅助 LLM（廉价/快速模型）对中间轮次进行结构化摘要，同时保护头部和尾部上下文。

### Context Engine 插件化（2026-04-10）

之前上下文管理只有一种方式——`ContextCompressor`（摘要压缩），想换策略就得改源码。现在抽出了 `ContextEngine` ABC，`ContextCompressor` 变成它的一个实现，第三方可以写插件替换，不用改 Hermes 源码。

**本质：把"上下文快满了怎么办"这个决策从硬编码变成了可插拔。**

```yaml
# config.yaml — 一行切换
context:
  engine: "compressor"   # 默认摘要压缩；设为插件名切换（如 "lcm"）
```

**可能的替代引擎举例：**

| 引擎 | 策略 | 适用场景 |
|------|------|---------|
| compressor（内置） | LLM 摘要压缩 | 通用，默认 |
| lcm（假设） | 旧对话存向量数据库，按需语义检索 | 超长会话，需要精确回忆 |
| sliding-window（假设） | 简单滑动窗口截断，不做摘要 | 低成本，不需要 auxiliary 模型 |

**ContextEngine ABC 要求实现 3 个核心方法**：
- `name` — 引擎标识（property）
- `should_compress(prompt_tokens)` — 是否需要压缩
- `compress(messages, current_tokens)` — 执行压缩，返回新消息列表

**可选方法**：`on_session_start/end`、`get_tool_schemas`（引擎可暴露工具给 agent，如 `lcm_grep`）、`handle_tool_call`、`update_model`。

**插件目录**：`plugins/context_engine/<name>/`，包含 `plugin.yaml` + `__init__.py`（实现 `register(ctx)` 或暴露 `ContextEngine` 子类）。

**只允许一个引擎活跃**，同 MemoryProvider 的 "至多一个外部" 约束。

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

### 演进历史

| 改进 | v1 | v2 | v3（2026-04-14+） |
|---|---|---|---|
| 摘要模板 | 无结构 | Goal/Progress/Decisions/Files/Next Steps | **编号的 Completed Actions + Active State**（action-log 风格） |
| 摘要更新 | 每次从头生成 | 迭代更新 | 迭代更新（继续编号） |
| 尾部保护 | 固定消息数 | Token 预算（按比例缩放） | 同 v2 |
| 工具输出修剪 | 无 | 通用占位符 `_PRUNED_TOOL_PLACEHOLDER` | **Smart Collapse**：按工具类型生成信息化单行摘要 |
| 去重 | 无 | 无 | **MD5 去重**：相同 tool result 只保留最新一份 |
| tool_call 参数 | 原样保留 | 原样保留 | **>500 字符自动截断到 200 字符** |
| 摘要预算 | 固定 | 按压缩内容比例缩放 | 同 v2，但 `max_tokens` 从 2× 降到 **1.3×**（防膨胀） |
| 反颠簸 | 无 | 无 | **连续 2 次压缩<10%→跳过**，避免抖动循环 |
| 多模态消息 | 可能崩溃 | 可能崩溃 | 在 dedup/prune 路径上跳过 list content |
| 压缩 note 幂等 | 仅首次压缩追加 | 同 v1 | **检测已存在**则不重复追加 |
| Failure cooldown | 10 分钟固定 | 10 分钟固定 | **无 provider 10 分钟，瞬态错误 60 秒** |
| 工具调用完整性 | 可能丢失 | _sanitize_tool_pairs 修复孤儿对 | 同 v2 |

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

### 2. 工具输出修剪（三段式预处理）

`_prune_old_tool_results()` 现在做三件事，全部不调 LLM：

**Pass 1 — MD5 去重**：相同的 tool result（>200 chars，非 multimodal）按 MD5 hash 去重，只保留最新一份，旧副本替换为：
```
[Duplicate tool output — same content as a more recent call]
```
典型场景：反复 read 同一个文件,或反复 search 相同 pattern。

**Pass 2 — Smart Collapse**（2026-04-14）：按 `tool_call_id` 查出工具名 + 参数,生成**信息化的 1 行摘要**替代原本的通用占位符。不同工具有不同模板:

```text
[terminal] ran `npm test` -> exit 0, 47 lines output
[read_file] read config.py from line 1 (1,200 chars)
[search_files] content search for 'compress' in agent/ -> 12 matches
[patch] replace in config.py (1,500 chars result)
[web_search] query='cache control' (5,200 chars result)
[delegate_task] 'refactor auth module' (8,400 chars result)
[memory] save on long-term
```

相比旧的 `_PRUNED_TOOL_PLACEHOLDER`,摘要保留了**具体命令 / 文件路径 / 结果规模**,模型看历史时仍然知道"之前做过什么"。内置模板覆盖 terminal / read_file / write_file / search_files / patch / browser_* / web_search / web_extract / delegate_task / execute_code / skill_* / vision_analyze / memory / todo / clarify / text_to_speech / cronjob / process,其他工具走通用 fallback。

**Pass 3 — tool_call 参数截断**:assistant 消息里如果有 `tool_calls.function.arguments` 长度 > 500,截断到前 200 字符 + `...[truncated]`。修复场景:`write_file(content=50KB)` 这种调用即使工具结果被修剪,参数本身仍然占上下文。

**多模态保护**:所有三个 Pass 都检测 `isinstance(content, list)` 跳过多模态消息,避免破坏图像/音频内容。

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

#### 首次压缩（v3 action-log 模板，2026-04-14）

```text
## Goal
[用户要完成什么]

## Constraints & Preferences
[用户偏好、编码风格、约束、重要决策]

## Completed Actions
[编号动作列表,每条格式: N. ACTION target — outcome [tool: name]
例:
1. READ config.py:45 — found `==` should be `!=` [tool: read_file]
2. PATCH config.py:45 — changed `==` to `!=` [tool: patch]
3. TEST `pytest tests/` — 3/50 failed: test_parse, test_validate, test_edge [tool: terminal]
要求具体:文件路径、命令、行号、结果都必须保留]

## Active State
[当前工作状态:
- 工作目录和分支
- 已修改/创建的文件及简要说明
- 测试状态 (X/Y passing)
- 运行中的进程或服务器
- 关键环境信息]

## In Progress
[压缩触发时正在进行的工作]

## Blocked
[未解决的阻塞/错误,包含完整错误消息]

## Key Decisions
[重要技术决策及其 WHY]

## Resolved Questions
[用户问过且已回答的问题 — 包含答案,避免下一任 agent 重复回答]

## Pending User Asks
[用户问过但尚未回答的问题]

## Remaining Work
[未完成的任务]

## Relevant Files
[读取/修改/创建的文件]

## Critical Context
[具体值、错误消息、配置细节等不能丢失的信息]
```

**v3 相比 v2 的关键差异**:
- **Progress / Done / In Progress 合并** → `Completed Actions`(编号) + `Active State` + `In Progress`
- **Next Steps** 改名 `Remaining Work`(避免被模型当成活动指令执行)
- **新增 Resolved Questions / Pending User Asks**(防止模型重复回答)
- 删掉了 v2 的 `Tools & Patterns` 节(信息已融入 Completed Actions)
- 摘要预算从 `max_tokens = budget * 2` 改为 `budget * 1.3`,限制膨胀

#### 迭代更新

当已有旧摘要时，Prompt 变为：

```text
PREVIOUS SUMMARY: [旧摘要]
NEW TURNS TO INCORPORATE: [新轮次]

更新摘要,保留所有仍有用的旧信息。
ADD 新的 completed actions 到编号列表(继续编号)。
把 "In Progress" 移到 "Completed Actions"(完成时)。
把已答问题移到 "Resolved Questions"。
更新 "Active State" 反映当前状态。
仅在明显过时时才移除信息。
```

### 6. 自适应失败冷却机制

```python
_SUMMARY_FAILURE_COOLDOWN_SECONDS = 600   # 10 分钟,用于无 provider
_TRANSIENT_COOLDOWN_SECONDS      = 60    # 1 分钟,用于瞬态错误

def _generate_summary(self, turns):
    if time.monotonic() < self._summary_failure_cooldown_until:
        return None  # 冷却期内跳过

    try:
        response = call_llm(task="compression", ...)
        self._summary_failure_cooldown_until = 0.0  # 成功则重置
    except RuntimeError:
        # 无 provider 配置 — 10 分钟内不会自己恢复
        self._summary_failure_cooldown_until = time.monotonic() + 600
    except Exception:
        # 瞬态错误(超时/限流/网络) — 短冷却快速重试
        self._summary_failure_cooldown_until = time.monotonic() + 60
```

**设计考量**(2026-04-14 改进):区分两类失败,`RuntimeError` 表示配置问题走 10 分钟长冷却,其他异常默认是瞬态问题走 60 秒短冷却,让压缩能更快从短暂故障中恢复。

### 6b. 反颠簸保护（Anti-Thrashing，2026-04-14）

```python
def should_compress(self, prompt_tokens=None) -> bool:
    if tokens < self.threshold_tokens:
        return False
    # 连续 2 次压缩节省 <10%,跳过本次
    if self._ineffective_compression_count >= 2:
        logger.warning(
            "Compression skipped — last %d compressions saved <10%% each. "
            "Consider /new to start a fresh session, or /compress <topic> ..."
        )
        return False
    return True
```

每次压缩后根据 `saved_estimate / display_tokens` 计算实际节省百分比:
- `>= 10%` → 重置 `_ineffective_compression_count = 0`
- `< 10%`  → `_ineffective_compression_count += 1`

**解决的问题**:某些场景下(尾部 + 头部 + 摘要本身已经很大)压缩只能挤出 1-2 条消息,每轮都触发但几乎没用,形成压缩抖动循环。连续两次都无效就放弃,提示用户 `/new` 或 `/compress <topic>` 手动处理。

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
    # 硬底线：至少保护 3 条尾部消息
    min_tail = min(3, n - head_end - 1)
    
    # 软上限：允许预算 1.5 倍超额，避免在超大消息中间切割
    soft_ceiling = int(token_budget * 1.5)
    
    # 从末尾向前累加，直到超过 soft_ceiling 且已满足 min_tail
    # 如果预算不足以覆盖 min_tail → 回退到 n - min_tail（强制保护 3 条）
    # 如果预算覆盖全部 → 强制在 head 之后切割，确保压缩仍执行
```

关键变化（2026-04-09）：从固定消息数保护改为 **token 预算 + 硬底线 min_tail=3**，对长消息和短消息都更合理。

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

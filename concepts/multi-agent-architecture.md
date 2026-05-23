---
title: Hermes 多 Agent 架构
created: 2026-04-08
updated: 2026-05-14
type: concept
tags: [architecture, module, agent, delegation, concurrency, kanban]
sources: [tools/delegate_tool.py, tools/mixture_of_agents_tool.py, tools/kanban_tools.py, hermes_cli/kanban.py, run_agent.py]
---

# Hermes 多 Agent 架构

## 概述

Hermes 的多 Agent 能力分为**五种运行时机制**，触发面 / lifetime / 持久性各不相同：

| 机制                    | 触发方式                  | 用途                   | 持久性 |
| --------------------- | --------------------- | -------------------- | --- |
| **Delegate Task**     | LLM tool call（模型自主决定） | 并行子任务，最多 3 路         | 单 turn |
| **Mixture of Agents** | LLM tool call（模型自主决定） | 多模型协同推理              | 单 turn |
| **Background Review** | 系统计数器自动触发             | 后台提炼经验 → 创建/改进 skill | 单 turn fork |
| **Goal Loop / Ralph** | 用户 `/goal` + judge 循环 | 跨 turn 自动续转直到达成      | 单 session（`state_meta` 持久化） |
| **Kanban 看板**         | dispatcher + worker 协议 | 跨 profile 共享任务队列，可靠性栈 | **跨 session、跨 profile、SQLite 持久** |

详见各专题：[[goal-loop-architecture]] · [[kanban-architecture]]。

## 触发机制

四种机制分为两类触发方式：

### LLM 自主调用（Delegate Task / MoA）

和 `web_search`、`read_file` 完全一样 — 模型在系统 prompt 中看到工具描述，根据用户问题**自己判断**是否调用，没有任何代码逻辑强制触发。

```text
用户提问 → LLM 推理 → 决定调用 delegate_task / mixture_of_agents
                              │
                              ▼
                  run_agent._invoke_tool()
                              │
            ┌─────────────────┼──────────────────┐
            ▼                                    ▼
    delegate_task                          registry.dispatch()
    (特殊分支，需注入                        → mixture_of_agents
     parent_agent 引用)
```

LLM 看到的工具描述：

| 工具                  | LLM 看到的描述（决策依据）                                                                                             |
| ------------------- | ----------------------------------------------------------------------------------------------------------- |
| `delegate_task`     | *"Spawn subagents to work on tasks in isolated contexts. Only the final summary is returned."*              |
| `mixture_of_agents` | *"Route a hard problem through multiple frontier LLMs collaboratively. Makes 5 API calls — use sparingly."* |

`delegate_task` 在 `_invoke_tool()` 中有显式分支（line 6108），因为需要注入 `parent_agent`。`mixture_of_agents` 走通用 registry dispatch。

### 系统自动触发（Background Review）

**LLM 不参与决定**。两个独立计数器在主循环中静默递增，阈值到达后在**用户拿到回复之后**自动触发：

```python
# run_agent.py — 两个独立计数器

# 记忆 review：每个 LLM turn +1（line 7008）
self._turns_since_memory += 1
if self._turns_since_memory >= self._memory_nudge_interval:  # 默认 10
    _should_review_memory = True
    self._turns_since_memory = 0

# 技能 review：每次 tool call +1（line 7242）
self._iters_since_skill += 1
if self._iters_since_skill >= self._skill_nudge_interval:    # 默认 10
    _should_review_skills = True
    self._iters_since_skill = 0
```

```text
用户提问 → Agent 推理 + 工具调用 → 回复交付给用户
                                        │
                                  检查计数器（line 9158）
                                        │
                                   超阈值？──否──→ 什么都不做
                                        │
                                       是
                                        │
                                        ▼
                              _spawn_background_review()
                              （守护线程，非阻塞）
                                        │
                                        ▼
                                  静默 AIAgent fork
                                  max_iterations=8
                                  stdout → /dev/null
                                        │
                                  审视对话历史
                                  "有没有试错、改变策略的经验？"
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                      skill_manage()         memory.add()
                      创建/改进 skill         提取持久事实
                              │                   │
                              └─────────┬─────────┘
                                        ▼
                              callback: "💾 Skill updated"
```

**关键区别**：用户已经拿到回复了，review 是后台静默行为。类似 GC（垃圾回收）— 定期自动跑，用户无感知。

## 一、Delegate Task — 子代理委派

Agent 运行时的核心多 Agent 能力。父 Agent 生成隔离的子 Agent 执行独立任务。

### 核心常量

```python
# tools/delegate_tool.py
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # 禁止递归委派
    "clarify",         # 子代理不能向用户提问
    "memory",          # 不能写入共享 MEMORY.md
    "send_message",    # 不能产生跨平台副作用（send_message 是消息投递工具，不属于多 Agent 机制）
    "execute_code",    # 子代理应逐步推理
])

MAX_DEPTH = 2                # 父(0) → 子(1) → 孙子被拒绝(2)
MAX_CONCURRENT_CHILDREN = 3  # 最多 3 个并行子代理
DEFAULT_MAX_ITERATIONS = 50  # 每个子代理默认迭代上限
DEFAULT_TOOLSETS = ["terminal", "file", "web"]
```

### Orchestrator 角色 + 可配置深度（v2026.4.18+）

`delegate_task` 新增 `role` 参数，支持 `leaf`（默认）和 `orchestrator`：

```yaml
# config.yaml
delegation:
  max_concurrent_children: 3   # 并发数下限，无上限
  max_spawn_depth: 1           # 1=扁平（默认），2-3 解锁嵌套委派
  orchestrator_enabled: true   # 全局开关
```

- **leaf**：和之前一样，子 agent 不能再 delegate
- **orchestrator**：子 agent 保留 `delegation` toolset，可以继续派生自己的 worker

**默认扁平姿态**：`max_spawn_depth=1` 时，orchestrator 角色静默降级为 leaf。用户主动把 `max_spawn_depth` 调到 2 或 3 才解锁嵌套委派。

新增 `DelegateEvent` enum（带 legacy 字符串向后兼容），供 gateway/ACP/CLI 进度消费者使用。

### 跨 Agent 文件状态协调（v2026.4.18+）

多个并发子 agent 同时修改文件时，父 agent 现在能看到一致的文件状态：
- 子 agent 写入的文件对其他子 agent 可见
- 父 agent 收到汇总时能看到所有子 agent 的文件操作
- 防止并发 patch 丢失

### 函数签名

```python
def delegate_task(
    goal: Optional[str] = None,          # 单任务模式
    context: Optional[str] = None,       # 背景信息
    toolsets: Optional[List[str]] = None,# 可用工具集
    tasks: Optional[List[Dict]] = None,  # 批量模式（最多 3 个）
    max_iterations: Optional[int] = None,
    acp_command: Optional[str] = None,   # ACP 子进程命令
    acp_args: Optional[List[str]] = None,
    parent_agent=None,                   # 由框架自动注入
) -> str:  # 返回 JSON
```

两种模式：
- **单任务**：传 `goal`，直接执行（无线程池开销）
- **批量**：传 `tasks` 数组，`ThreadPoolExecutor(max_workers=3)` 并行

### 隔离模型

```text
从父 Agent 继承                    子代理独有（完全隔离）
─────────────────                 ─────────────────────
✓ Model / Provider / API Key      ✗ 对话历史（空白开始）
✓ 工作目录 (cwd)                   ✗ 终端 session（独立）
✓ Credential Pool（同 provider）   ✗ 中间工具调用（父不可见）
✓ 平台 / session_db 引用           ✗ 推理过程（父不可见）
✓ Max tokens / reasoning config   ✗ 上下文文件（skip_context_files=True）
                                   ✗ 记忆（skip_memory=True）
```

### 子代理构建流程（`_build_child_agent`）

```python
def _build_child_agent(
    task_index: int,              # 在批量中的索引
    goal: str,                    # 委派目标
    context: Optional[str],       # 背景
    toolsets: Optional[List[str]],# 工具集（与父取交集，减去黑名单）
    model: Optional[str],         # 可覆盖父模型
    max_iterations: int,          # 独立迭代上限
    parent_agent,                 # 父 Agent 引用
    override_provider=None, override_base_url=None,
    override_api_key=None, override_api_mode=None,
    override_acp_command=None, override_acp_args=None,
):
```

**工具集计算规则**：子代理永远不能获得比父级更多的工具。

```text
子代理工具 = (用户指定 ∩ 父级可用) - DELEGATE_BLOCKED_TOOLS
```

### 凭证池共享

```python
def _resolve_child_credential_pool(effective_provider, parent_agent):
    # 同 provider → 共享父级 pool（轮换同步）
    # 不同 provider → 加载该 provider 自己的 pool
    # 无 pool → 继承父级固定凭证
```

### 中断传播

```python
# run_agent.py — 父 Agent 的 interrupt() 方法
with self._active_children_lock:
    children_copy = list(self._active_children)
for child in children_copy:
    child.interrupt(message)  # 线程安全传播
```

子代理在 `_build_child_agent` 时注册到 `_active_children`，执行完成后在 `finally` 中注销。

### 结果结构

父 Agent 只看到这个结构化摘要，**不看到子代理的中间工具调用和推理**：

```json
{
  "results": [
    {
      "task_index": 0,
      "status": "completed",
      "summary": "Fixed the login bug by...",
      "api_calls": 12,
      "duration_seconds": 45.3,
      "model": "qwen3.6-plus",
      "exit_reason": "completed",
      "tokens": {"input": 8432, "output": 2341},
      "tool_trace": [
        {"tool": "read_file", "args_bytes": 45, "result_bytes": 1234, "status": "ok"},
        {"tool": "patch", "args_bytes": 234, "result_bytes": 56, "status": "ok"}
      ]
    }
  ],
  "total_duration_seconds": 52.1
}
```

### ACP 异构编排

通过 ACP 协议委派给外部 Agent（如 Claude Code）：

```python
delegate_task(
    goal="Refactor this module",
    acp_command="claude",
    acp_args=["--acp", "--stdio", "--model", "claude-opus-4-6"]
)
```

Hermes 作为编排器，外部 Agent 作为执行者。

---

## 二、Mixture of Agents — 多模型协同推理

不是子代理，而是**多个外部 LLM 协作回答同一个问题**。

### 架构

```text
                    用户问题
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼            ▼
    Claude Opus    Gemini Pro    GPT-5.4     DeepSeek V3
    (temp=0.6)     (temp=0.6)   (temp=0.6)   (temp=0.6)
          │            │            │            │
          └────────────┼────────────┘
                       ▼
                Claude Opus 聚合器
                  (temp=0.4)
                       │
                  综合最佳答案
```

### 常量

```python
# tools/mixture_of_agents_tool.py
REFERENCE_MODELS = [
    "anthropic/claude-opus-4.6",
    "google/gemini-3-pro-preview",
    "openai/gpt-5.4-pro",
    "deepseek/deepseek-v3.2",
]
AGGREGATOR_MODEL = "anthropic/claude-opus-4.6"

REFERENCE_TEMPERATURE = 0.6     # 多样性
AGGREGATOR_TEMPERATURE = 0.4    # 一致性
MIN_SUCCESSFUL_REFERENCES = 1   # 最少 1 个成功即可聚合
```

### 与 Delegate Task 的区别

|        | Delegate Task | Mixture of Agents       |
| ------ | ------------- | ----------------------- |
| **目的** | 并行执行不同任务      | 同一问题多角度推理               |
| **隔离** | 完全对话隔离        | 只共享参考回复                 |
| **模型** | 同模型或可覆盖       | 4 参考 + 1 聚合（5 个 API 调用） |
| **输出** | 每个任务独立摘要      | 单一综合答案                  |
| **场景** | 研究、调试、多工作流    | 复杂数学、算法、高难度推理           |

---

## 三、Background Review — 后台经验提炼

Agent 在对话过程中**自动 fork 一个静默 Agent**，回顾对话并创建/改进 skill。

### 触发条件

```python
# run_agent.py
self._iters_since_skill  # 每次 tool call +1
self._skill_nudge_interval = 10  # 每 10 次触发一次 review
```

### Fork 机制

```python
def _spawn_background_review(self, messages_snapshot, review_memory, review_skills):
    # 守护线程（非阻塞）
    fork = AIAgent(
        model=self.model,
        provider=self.provider,
        max_iterations=8,         # 轻量级，最多 8 步
        quiet_mode=True,          # stdout → /dev/null
        conversation_history=messages_snapshot,  # 父对话快照
        skip_context_files=True,
    )
    # fork 共享父的 _memory_store 和 skill 目录
    # 可以调用 skill_manage(action='create/patch')
```

### 三种 Review Prompt

| Prompt | 关注点 |
|--------|-------|
| `_MEMORY_REVIEW_PROMPT` | 提取值得记住的事实 → 写入 MEMORY.md |
| `_SKILL_REVIEW_PROMPT` | 提炼可复用的流程 → 创建/改进 skill |
| `_COMBINED_REVIEW_PROMPT` | 同时做 memory + skill review |

### 与 Delegate Task 的区别

| | Delegate Task | Background Review |
|---|---|---|
| **触发** | Agent 主动调用 | 每 10 次迭代自动触发 |
| **阻塞** | 阻塞父 Agent 等结果 | 守护线程，完全非阻塞 |
| **隔离** | 完全隔离 | **共享** memory store 和 skill 目录 |
| **结果** | JSON 结构化摘要 | callback 通知："💾 Skill 'xxx' updated" |
| **用途** | 并行执行用户任务 | 自动提炼经验、改进 skill |

---

## 四、Agent 间通信机制

Hermes 的 agent 间通信**没有消息队列、没有共享内存、没有 IPC**——全部在单进程内通过 Python 原生机制完成。

### Delegate Task 的通信

父子 agent 通过 **ThreadPoolExecutor + Future** 通信，本质是线程间函数调用：

```python
# delegate_tool.py line 619-633
# 父线程：提交任务到线程池
with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_CHILDREN) as executor:
    for i, t, child in children:
        future = executor.submit(
            _run_single_child,              # 子 agent 执行函数
            task_index=i, goal=t["goal"],
            child=child, parent_agent=parent_agent,
        )
        futures[future] = i

    # 父线程：阻塞等待，谁先完成先收谁
    for future in as_completed(futures):
        entry = future.result()             # ← 这就是"通信"
        results.append(entry)
```

```python
# _run_single_child 内部（line 373）
result = child.run_conversation(user_message=goal)  # 子 agent 跑完
summary = result.get("final_response") or ""         # 直接取返回值
```

**单任务时更简单**，连线程池都不用（line 612）：
```python
result = _run_single_child(0, _t["goal"], child, parent_agent)
```

### Mixture of Agents 的通信

MoA 连线程都没有，是**同一线程内的异步 HTTP 请求 + 内存聚合**：

```python
# mixture_of_agents_tool.py line 311
# 4 个 HTTP 请求并发发出（asyncio 协程，不是多线程）
model_results = await asyncio.gather(*[
    _run_reference_model_safe(model, user_prompt, REFERENCE_TEMPERATURE)
    for model in ref_models
])

# 结果收集到 list 里（纯内存变量）
successful_responses = []
for model_name, content, success in model_results:
    if success:
        successful_responses.append(content)

# 拼成 prompt 发第 5 个请求
aggregator_system_prompt = _construct_aggregator_prompt(
    AGGREGATOR_SYSTEM_PROMPT, successful_responses
)
```

4 个模型的中间回答存在函数栈的 list 里，聚合完成后垃圾回收，不落盘。

### 子 agent 之间

**完全不通信。** 多个子 agent 并行跑在各自的线程里，互不知道对方存在，没有任何协调机制。

### 中断时的结果处理

用户在子 agent 执行期间发新消息时：

```python
# run_agent.py line 2527-2538
def interrupt(self, message):
    self._interrupt_requested = True
    # 传播到所有正在跑的子 agent
    with self._active_children_lock:
        children_copy = list(self._active_children)
    for child in children_copy:
        child.interrupt(message)    # 逐个中断
```

中断后：
- 子 agent 返回 `status: "interrupted"`，已产出的部分结果保留在返回值中
- 父 agent 的 `_persist_session` 触发，把包含中断结果的消息写入 SQLite
- **但中断结果不会作为有效答案展示给用户**——父 agent 标记 `completed: False`，进入处理新消息的下一轮
- 子 agent 自身 `persist_session=False`，不会独立写 DB——其部分结果以"父 agent 对话中的工具返回消息"形式存在 DB 里

### 通信模型总结

| 机制 | 通信方式 | 并发模型 | 中间结果存储 |
|------|---------|---------|------------|
| Delegate Task | `Future.result()`（线程间返回值） | ThreadPoolExecutor 多线程 | 不落盘，函数返回值 |
| Mixture of Agents | `asyncio.gather`（异步协程收集） | 单线程异步 | 不落盘，内存 list |
| Background Review | 守护线程 fire-and-forget | 单独守护线程 | 直接写 skill/memory 文件 |

**一句话：上述三种全部在单进程内完成，没有进程间通信。** Goal Loop 同样在单进程内但跨多个 turn；Kanban 则是**跨进程 / 跨 profile**，靠 SQLite + WAL 锁 + CAS 协调，详见 [[kanban-architecture]]。

---

## 五、Goal Loop —— Ralph 循环

`/goal <text>` 进入 *持续目标* 模式：每个 turn 结束后辅助模型判官评判是否完成，未完成则注入续转 prompt（普通 user message），直到 done / budget / pause / cleared / 新用户消息抢占。

要点（**不**同于 Delegate / MoA / Background Review）：

- **不 fork**：全程在主 session 里跑，prompt cache 持续命中
- **不改 system prompt / toolset**：续转 prompt 是 user message 追加
- **跨 turn 持久**：`state_meta` 表 `goal:<session_id>`，`/resume` 接续
- **fail-OPEN**：judge 出错 = continue，turn budget (默认 20) 是最后保险

详见 [[goal-loop-architecture]]。

---

## 六、Kanban —— 持久协作看板

v0.13.0 引入的 **durable multi-profile board**（`hermes_cli/kanban*.py` + `tools/kanban_tools.py`，~10.9k 行）。

唯一**跨 session、跨 profile**的协作机制：

- SQLite 存储 (`<root>/kanban.db`)
- dispatcher 守护进程从 `ready` 队列 spawn worker 子进程（独立 hermes 进程）
- worker 通过 9 个 `kanban_*` tool 把状态写回 DB
- 心跳 + reclaim + zombie detection + per-task `max_retries` + hallucination gate
- dashboard / `/kanban` 斜杠 / `hermes kanban` CLI 三个面绕过 agent 直接操作

详见 [[kanban-architecture]]。

---

## 七、迭代预算系统

所有多 Agent 机制共享的资源管理层。

### IterationBudget 类

```python
class IterationBudget:
    """线程安全的迭代计数器（run_agent.py:167-209）"""
    
    def __init__(self, max_total: int):
        self.max_total = max_total
        self._used = 0
        self._lock = threading.Lock()
    
    def consume(self) -> bool:
        """原子检查+递减。每次 LLM turn 调用一次。"""
    
    def refund(self) -> None:
        """退还一次（execute_code 调用后退还，鼓励多验证）。"""
    
    @property
    def remaining(self) -> int: ...
```

### 预算隔离

```text
父 Agent:  IterationBudget(90)   ← 默认 90
子代理 A:  IterationBudget(50)   ← 独立，不消耗父预算
子代理 B:  IterationBudget(50)   ← 独立
子代理 C:  IterationBudget(50)   ← 独立
──────────────────────────────
理论总迭代: 90 + 150 = 240
```

### 预算压力警告

```python
self._budget_caution_threshold = 0.7   # 70% — "开始收尾"
self._budget_warning_threshold = 0.9   # 90% — "立即响应"
```

警告注入到工具结果 JSON 中（不破坏消息结构、不使 prompt cache 失效）。

---

## 六、配置

```yaml
# config.yaml
delegation:
  provider: openrouter            # 可选：子代理用专用 provider
  model: google/gemini-3-flash    # 可选：子代理用廉价模型
  max_iterations: 50              # 每个子代理最大迭代次数
  reasoning_effort: low           # 可选：控制子代理推理深度（low/medium/high/xhigh）
  # 或直接指定端点
  base_url: https://api.openai.com/v1
  api_key: sk-xxx
```

### 使用示例

```python
# 单任务
delegate_task(
    goal="Debug the login failure issue",
    context="User reports 500 error on /api/login",
    toolsets=["terminal", "file"]
)

# 并行 3 个任务
delegate_task(tasks=[
    {"goal": "Fix login bug", "toolsets": ["terminal", "file"]},
    {"goal": "Update API docs", "toolsets": ["terminal", "file"]},
    {"goal": "Run test suite", "toolsets": ["terminal"]},
])

# 多模型协同推理
mixture_of_agents(user_prompt="证明 P ≠ NP 的已知最强结果是什么？")
```

## 多 Agent 的两个层面

Hermes 实际上有两种多 Agent 方案，服务于不同场景：

|                  | 会话内 multi-agent（本页）   | 多 Profile                 |
| ---------------- | --------------------- | ------------------------- |
| 粒度               | 一个会话内的子任务             | 完全独立的 agent 实例            |
| 上下文              | 子 agent 继承父 agent 的对话 | 完全隔离，互不可见                 |
| terminal backend | 继承父 agent，**不能切换**    | 每个 Profile **独立配置**       |
| 记忆               | 共享（同一个 MemoryManager） | 各自独立的 MEMORY.md / USER.md |
| 模型               | 可以不同                  | 可以不同                      |
| 协作方式             | 自动派发 + 结果回传           | 人工切换，无自动协作                |

**会话内 multi-agent 是"一个大脑指挥多只手"**——适合一次任务内的并行分工。

**多 Profile 是"多个独立的人各管各的"**——适合按职能隔离不同安全边界、模型、技能集。例如：`coder` Profile 用 `local` backend 做日常开发，`ops` Profile 用 `docker` backend 做危险操作。

### 多 Profile 之间能通信吗？

**没有原生通信通道。** 每个 Profile 是独立进程、独立 DB、独立记忆，互不知道对方存在。

但可以通过**消息平台间接交互**——两个 Profile 各绑一个 bot，在同一个频道里：

```text
Profile A (Bot A) → send_message 工具主动发消息到频道
                              ↓
                      Discord / Slack 频道（消息中转）
                              ↓
Profile B (Bot B) → ALLOW_BOTS=all → 收到，当普通用户消息处理
```

Discord 和 Slack 都支持 `allow_bots` 配置（三模式：none/mentions/all）：

```bash
# Discord — Bot B 的 .env
DISCORD_ALLOW_BOTS=none       # 默认：忽略所有 bot 消息
DISCORD_ALLOW_BOTS=mentions   # 只接收 @提及自己的 bot 消息
DISCORD_ALLOW_BOTS=all        # 接收所有 bot 消息

# Slack — Bot B 的 .env
SLACK_ALLOW_BOTS=none         # 同上
SLACK_ALLOW_BOTS=mentions
SLACK_ALLOW_BOTS=all
```

Discord 还有**多 bot 过滤**：消息 @了其他 bot 但没 @自己时自动跳过，避免多 bot 频道互相干扰。

**注意**：这不是 Hermes 设计的 agent 间通信功能，是两个独立 bot 通过平台消息碰巧交互。有延迟、无事务保证，且容易产生死循环（A 发 → B 回 → A 又回 → 无限循环），使用时需注意控制。

详见 → [[configuration-and-profiles]]

## 四、Kanban — 跨 profile 持久看板（v0.13.0+）

**post-revert 重写版**，从前一次（已撤回）的多 profile 协作板重新设计为「先持久化、再多 worker」。整张板存在共享 SQLite，多个 profile 的 Hermes worker 通过心跳竞争任务，僵尸 worker 自动回收，每个任务有重试预算。

### 组件

| 组件 | 文件 | 行数 |
|------|------|------|
| CLI 入口 | `hermes_cli/kanban.py` | 2252 |
| SQLite 状态层 | `hermes_cli/kanban_db.py` | 4839 |
| Worker 健康诊断 | `hermes_cli/kanban_diagnostics.py` | 776 |
| Agent 内工具 | `tools/kanban_tools.py` | 1139 |
| 分发器 systemd unit | `plugins/kanban/systemd/hermes-kanban-dispatcher.service` | — |
| Dashboard 插件 | `plugins/kanban/dashboard/` | — |
| Worker / Orchestrator 技能 | `skills/devops/kanban-{worker,orchestrator}/` | — |

### 任务状态机

```
todo → ready → running → done
                  ↓
                blocked → todo（重试）
                  ↓
                archived（终态，可被消费）
```

`hermes_cli/kanban.py` 暴露 38 个 `_cmd_*` 子命令，覆盖 boards（multi-board 多看板）、init、heartbeat、assignees、create、list、show、assign、reclaim、reassign、diagnostics、link、unlink、claim、comment、complete、edit、block、unblock、archive、tail、dispatch、daemon、watch、stats、notify_*、log、runs、context、specify、gc。

### Agent 内工具：9 个 kanban_* 工具

Agent 在 kanban worker 模式下（环境变量 `HERMES_KANBAN_TASK` 被设置）或 profile 显式启用 `kanban` toolset 时才可见：

- `kanban_show` / `kanban_list` — 只读视图
- `kanban_complete` / `kanban_block` / `kanban_unblock` — 推进任务
- `kanban_heartbeat` — worker 主动心跳（默认 dispatcher 每 30s 自动 ping）
- `kanban_comment` — 留言（包括给 orchestrator 的交付证据）
- `kanban_create` / `kanban_link` — orchestrator 角色才能用，建子任务 + 依赖链

源码 `tools/kanban_tools.py:1061-1133` 列出全部 9 个工具的 `register_tool()`。`_enforce_worker_task_ownership`（行 115）强制 worker 只能改自己被 claim 的任务，防止 cross-worker 互踩。

### 可靠性保障

| 机制 | 实现 |
|------|------|
| 心跳 + reclaim | dispatcher 周期扫描 stale heartbeat，自动 reassign |
| 僵尸检测 | macOS / Linux 平台特有的 zombie worker 检测，分发器主动回收 |
| 退出无完成 → auto-block | worker 进程退出但任务未完成时强制移入 blocked，避免「悄悄死掉」 |
| 重试预算 | 每个任务 `max_retries` 字段，超出后停止再分发 |
| 幻觉门 | worker 声称「创建了新任务」时校验该任务在数据库中确实存在，否则拒绝并要求重试 |
| 一致性失败计数 | spawn / timeout / crash 统一计入 `failure_count`，避免不同失败路径计数器漂移 |

### 多 board 支持

一台机器可以同时跑多块看板：`hermes kanban boards create <slug>`、`boards switch <slug>`、`boards rm <slug>`、`boards show <slug>`。每块看板独立的 SQLite + 独立的 dispatcher service。多 profile 共享同一块看板时通过 `assignees` 表实现 worker 注册。

详见 → `skills/devops/kanban-orchestrator/` 和 `kanban-worker/`，里面有具体 prompt 和工作流。

## 五、`/goal` — Ralph loop 持久目标（v0.13.0+）

`hermes_cli/goals.py`（593 行）。给 Agent 一个跨 turn 持续追逐的目标，每轮结束后由一个**判断模型**（aux client）裁决目标是否达成；没达成就自动注入续作 prompt 继续。Ralph loop 作为一等公民。

### 工作流

```text
用户：/goal 把 src/ 下所有 TODO 注释清掉，PR 提上去
       │
       ▼
GoalState{goal=..., status="active", turns_used=0, max_turns=20}
持久化到 SessionDB.state_meta["goal:<session_id>"]
       │
每轮结束后：
       ▼
judge_goal(goal_text, last_response) → {"done": bool, "reason": str}
       │
   ┌───┴───┐
   ▼       ▼
 done   continue
   │       │
   ▼       ▼
clear  注入 CONTINUATION_PROMPT_TEMPLATE 当作新 user message
       │
       ▼
不修改系统 prompt / toolset → prompt cache 保留
```

### 关键不变量

1. **不修改系统 prompt 或 toolset**：续作 prompt 就是普通的 user message，prefix cache 保持完整（见 [[prompt-caching-optimization]] 的 prefix_and_2 路径）。
2. **Judge 失败 fail-OPEN**：判断模型异常 → `continue`，turn budget 是兜底。
3. **用户新消息抢占**：真实用户输入到达时立即抢占续作 prompt，且把循环暂停一回合（用户消息本身可能完成目标，下一轮再判）。
4. **解析失败自动暂停**：连续 3 次 judge 解析失败（小模型不遵守严格 JSON 协议）自动暂停 + 提示用户改 `goal_judge` 配置，防止预算被「judge returned empty response」一类垃圾消耗光。

GoalState 序列化字段：`goal, status, turns_used, max_turns, created_at, last_turn_at, last_verdict, last_reason, paused_reason, consecutive_parse_failures`。状态写在 SessionDB 的 `state_meta` 表，键 `goal:<session_id>`，所以 `/resume` 自动恢复目标。

## 六、Autonomous Curator — 自治技能维护（v0.12.0+ 升级）

不同于 Background Review（per-session 计数器触发），**Curator** 是 gateway 上**独立**跑的代理，在 cron ticker 上每 N 小时（默认 7 天）自动跑一次 skill review：

- 给每个 agent-created skill 用**类一级 rubric**评分（v0.12 起改成 rubric-based，之前是自由文本）
- consolidate（合并）/ prune（淘汰）/ pin（保护）/ archive（可恢复）
- 每次运行写报告：`logs/curator/run.json` + `REPORT.md`
- 归档时分两类：consolidated（已被另一个 skill 吞并）vs pruned（独立淘汰），由模型 + 启发式联合分类
- 严格不动 bundled / hub skill（按 frontmatter `name` 保护）
- 用 `auxiliary.curator` slot 选模型，`hermes curator status` 看最近一次 run 摘要 + 最常用 / 最少用 skill 排行

源码：`agent/curator.py`（1781 行）、`agent/curator_backup.py`、`hermes_cli/curator.py`。CLI 子命令：`status / run / pause / resume / pin / unpin / restore / archive / prune / backup / rollback / list-archived`。

v0.13 起 `hermes curator run` 是同步的（直接看输出，不用 tail log），并新增 `archive / prune / list-archived` 三个手动子命令。

详见 → [[skills-system-architecture]] 的 Curator 章节。

## 相关页面

- [[configuration-and-profiles]] — 多 Profile 架构（另一种多 Agent 方案）；kanban 多 profile worker
- [[tool-registry-architecture]] — 子代理通过 registry 获取受限工具集；kanban tool gating
- [[auxiliary-client-architecture]] — 子代理可配置独立的辅助模型
- [[credential-pool-and-isolation]] — 凭证池共享与轮换
- [[skills-system-architecture]] — Background Review、kanban-orchestrator/worker skills
- [[trajectory-and-data-generation]] — Batch Runner（Nous 内部训练工具，不属于 Agent 运行时）
- [[2026-05-07-update]] — Kanban 首次发布（v0.13.0）
- [[2026-05-11-update]] — Kanban 安全 + worker mode 修复

## 相关文件

- `tools/delegate_tool.py` — 子代理委派实现
- `tools/mixture_of_agents_tool.py` — 多模型协同推理
- `tools/send_message_tool.py` — 跨平台消息投递（不属于多 Agent，归类于 messaging-gateway）
- `tools/kanban_tools.py` — Kanban worker / orchestrator 工具
- `hermes_cli/kanban_db.py` — Kanban SQLite store
- `hermes_cli/kanban_diagnostics.py` — 诊断引擎
- `hermes_cli/kanban_specify.py` — Spec 自动充实
- `run_agent.py` — IterationBudget 类、Background Review、中断传播
- `tools/kanban_tools.py` — Kanban worker agent 工具（schema-gated）
- `hermes_cli/kanban.py` — `hermes kanban` CLI
- `hermes_cli/kanban_db.py` — SQLite schema + WAL + CAS + 多 board 路由
- `hermes_cli/kanban_diagnostics.py` — zombie 检测、reclaim、hallucination gate
- `hermes_cli/kanban_specify.py` — 任务规范化 / 模板

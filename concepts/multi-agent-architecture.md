---
title: Hermes 多 Agent 架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, agent, delegation, concurrency]
sources: [tools/delegate_tool.py, tools/send_message_tool.py, tools/mixture_of_agents_tool.py, run_agent.py]
---

# Hermes 多 Agent 架构

## 概述

Hermes 的多 Agent 能力分为**四种运行时机制**，全部在 Agent 对话过程中触发，不涉及外部脚本或离线工具：

| 机制 | 触发方式 | 用途 |
|------|---------|------|
| **Delegate Task** | LLM tool call（模型自主决定） | 并行子任务，最多 3 路 |
| **Mixture of Agents** | LLM tool call（模型自主决定） | 多模型协同推理 |
| **Background Review** | 系统计数器自动触发 | 后台提炼经验 → 创建/改进 skill |
| **Send Message** | LLM tool call（模型自主决定） | 跨平台消息投递 |

## 触发机制

四种机制分为两类触发方式：

### LLM 自主调用（Delegate Task / MoA / Send Message）

和 `web_search`、`read_file` 完全一样 — 模型在系统 prompt 中看到工具描述，根据用户问题**自己判断**是否调用，没有任何代码逻辑强制触发。

```text
用户提问 → LLM 推理 → 决定调用 delegate_task / mixture_of_agents / send_message
                              │
                              ▼
                  run_agent._invoke_tool()
                              │
            ┌─────────────────┼──────────────────┐
            ▼                 ▼                  ▼
    delegate_task         registry.dispatch()  registry.dispatch()
    (特殊分支，需注入      → mixture_of_agents   → send_message
     parent_agent 引用)
```

LLM 看到的工具描述：

| 工具 | LLM 看到的描述（决策依据） |
|------|------------------------|
| `delegate_task` | *"Spawn subagents to work on tasks in isolated contexts. Only the final summary is returned."* |
| `mixture_of_agents` | *"Route a hard problem through multiple frontier LLMs collaboratively. Makes 5 API calls — use sparingly."* |
| `send_message` | *"Send a message to a connected messaging platform, or list available targets."* |

`delegate_task` 在 `_invoke_tool()` 中有显式分支（line 6108），因为需要注入 `parent_agent`。其他两个走通用 registry dispatch。

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
    "send_message",    # 不能产生跨平台副作用
    "execute_code",    # 子代理应逐步推理
])

MAX_DEPTH = 2                # 父(0) → 子(1) → 孙子被拒绝(2)
MAX_CONCURRENT_CHILDREN = 3  # 最多 3 个并行子代理
DEFAULT_MAX_ITERATIONS = 50  # 每个子代理默认迭代上限
DEFAULT_TOOLSETS = ["terminal", "file", "web"]
```

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

| | Delegate Task | Mixture of Agents |
|---|---|---|
| **目的** | 并行执行不同任务 | 同一问题多角度推理 |
| **隔离** | 完全对话隔离 | 只共享参考回复 |
| **模型** | 同模型或可覆盖 | 4 参考 + 1 聚合（5 个 API 调用） |
| **输出** | 每个任务独立摘要 | 单一综合答案 |
| **场景** | 研究、调试、多工作流 | 复杂数学、算法、高难度推理 |

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

## 四、Send Message — 跨平台通信

Agent 主动向其他平台/会话发送消息。

### 目标格式

```text
"telegram"                    → home channel
"telegram:#general"           → 人类可读频道名（解析为 ID）
"telegram:123456789"          → 数字 chat_id
"telegram:123456789:42"       → Telegram topic（thread_id）
"signal:+1234567890"          → 手机号
```

### 支持的 14 个平台

Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeChat(WeCom), Webhook

### 媒体附件

图片（jpg/png/webp/gif）、视频（mp4/mov）、音频（ogg/mp3/wav）、语音。完整媒体支持仅 Telegram 和 Feishu，其他平台仅文本。

---

## 五、迭代预算系统

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

## 相关页面

- [[tool-registry-architecture]] — 子代理通过 registry 获取受限工具集
- [[auxiliary-client-architecture]] — 子代理可配置独立的辅助模型
- [[credential-pool-and-isolation]] — 凭证池共享与轮换
- [[skills-system-architecture]] — Background Review 自动创建/改进的 skill 存储在这里
- [[trajectory-and-data-generation]] — Batch Runner（Nous 内部训练工具，不属于 Agent 运行时）

## 相关文件

- `tools/delegate_tool.py` — 子代理委派实现
- `tools/mixture_of_agents_tool.py` — 多模型协同推理
- `tools/send_message_tool.py` — 跨平台消息投递
- `run_agent.py` — IterationBudget 类、Background Review、中断传播

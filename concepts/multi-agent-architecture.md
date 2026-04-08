---
title: Hermes 多 Agent 体系架构
created: 2026-04-08
updated: 2026-04-08
type: concept
tags: [architecture, module, component, agent, delegation, performance, concurrency]
sources: [tools/delegate_tool.py, batch_runner.py, tools/send_message_tool.py]
---

# Hermes 多 Agent 体系架构

## 概述

Hermes 的多 Agent 体系不是简单的"一个 Agent 调用另一个"，而是一个**分层、隔离、可编排**的子代理系统。包含三个核心维度：

1. **Delegate Task** — 运行时动态委派，单任务或最多 3 个并行子代理
2. **Batch Runner** — 大规模批量处理，数千 prompts 的分布式执行
3. **Send Message** — 跨平台通信，Agent 间的异步消息传递

核心理念：**子代理完全隔离，父 Agent 只看到摘要，不暴露中间过程。**

## 架构原理

### 整体拓扑

```
父 Agent (Parent)
    │
    ├── delegate_task(goal) ──→ 单个子代理 (隔离会话)
    │
    ├── delegate_task(tasks=[...]) ──→ 最多 3 个并行子代理
    │                                     │
    │                                     ├── 子代理 A (独立 terminal, 独立 toolsets)
    │                                     ├── 子代理 B (独立 terminal, 独立 toolsets)
    │                                     └── 子代理 C (独立 terminal, 独立 toolsets)
    │
    ├── batch_runner ──→ 大规模批量处理
    │                      ├── Worker Pool (并发)
    │                      │   ├── Prompt 1 → AIAgent → 结果
    │                      │   ├── Prompt 2 → AIAgent → 结果
    │                      │   └── ...
    │                      └── 汇总统计
    │
    └── send_message ──→ 跨平台投递
                          ├── 发送到 Telegram
                          ├── 发送到 Discord
                          ├── 发送到其他 session
                          └── 发送到 home channels
```

## 核心组件一：Delegate Task（子代理委派）

### 安全沙箱设计

```python
DELEGATE_BLOCKED_TOOLS = frozenset([
    "delegate_task",   # 禁止递归委派（防止无限嵌套）
    "clarify",         # 子代理不能向用户提问
    "memory",          # 不能写入共享 MEMORY.md
    "send_message",    # 不能产生跨平台副作用
    "execute_code",    # 子代理应逐步推理，而非写脚本
])

MAX_DEPTH = 2  # 父(0) → 子(1) → 禁止孙子(2)
MAX_CONCURRENT_CHILDREN = 3  # 最多 3 个并行
DEFAULT_MAX_ITERATIONS = 50  # 每个子代理独立的迭代预算
```

**安全哲学**：子代理是**受限的特化工作者**，不是完整的 Agent。

### 子代理构建流程

```
1. 解析配置（delegation.provider / delegation.base_url）
2. 确定工具集（从父继承，减去被禁工具，与用户指定交集）
3. 解析工作空间路径（从父 Agent 继承 cwd）
4. 构建专属系统提示（focused prompt: task + context + workspace）
5. 创建 AIAgent 实例（继承认证、平台、技能等）
6. 分配独立迭代预算（不受父预算限制）
7. 注册中断传播（父被中断时子也被中断）
```

### 凭证继承与隔离

```python
def _resolve_delegation_credentials(cfg, parent_agent):
    """
    凭证解析优先级:
    1. delegation.base_url → 直接端点（专用模型）
    2. delegation.provider → 通过 runtime_provider 解析完整凭证
    3. 无配置 → 完全继承父 Agent 的凭证
    """
```

**凭证池共享**：如果子代理和父使用相同 provider，共享 credential pool，实现速率限制同步轮换。

### 并行执行机制

```python
def delegate_task(goal=None, tasks=None, ...):
    # 单任务：直接运行（无线程池开销）
    if n_tasks == 1:
        result = _run_single_child(0, goal, child, parent)
    
    # 批量：ThreadPoolExecutor 并行
    else:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_run_single_child, ...): i for i, ...}
            for future in as_completed(futures):
                results.append(future.result())
```

**设计考量**：单任务不走线程池，避免不必要的线程创建开销。

### 进度反馈机制

子代理执行时，父 Agent 显示实时进度：

```
🔀 3 tasks remaining
  [1/3] Fix login bug  (reading file...)  ✓
  [2/3] Update docs    (writing file...)   ✓
  [3/3] Run tests      (running pytest...)  ✗
```

CLI 模式：通过 spinner.print_above() 在旋转器上方打印树状视图
Gateway 模式：批量收集工具名，定期推送给父进度回调

### 结果结构

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

**关键**：父 Agent 只看到这个结构化的摘要和 trace，**不看到子代理的中间工具调用和推理过程**。

### ACP 子代理支持

```python
# 通过 ACP 协议在子代理中运行 Claude Code 等外部 Agent
delegate_task(
    goal="Refactor this module",
    acp_command="claude",
    acp_args=["--acp", "--stdio", "--model", "claude-opus-4-6"]
)
```

这允许**异构 Agent 编排**：Hermes 作为编排器，Claude Code 作为执行者。

## 核心组件二：Batch Runner（批量处理）

### 架构

```python
class BatchRunner:
    """大规模批量处理引擎"""
    
    def __init__(self, prompts, config):
        self.prompts = prompts        # 数千个 prompts
        self.config = config           # 模型、工具集等配置
        self.stats = {}               # 统计追踪
    
    def run(self):
        # 1. 分发到 worker pool
        # 2. 并行执行（每个 prompt 一个 AIAgent 实例）
        # 3. 收集结果
        # 4. 生成统计报告
```

### 应用场景

- **数据生成**：批量生成 RL 训练数据
- **基准测试**：对数千个 prompts 进行模型评估
- **技能验证**：批量验证技能配置
- **Trajectory 收集**：为 fine-tuning 收集对话轨迹

### 统计功能

```python
def _extract_tool_stats(messages):
    """提取工具使用统计"""

def _extract_reasoning_stats(messages):
    """提取推理统计"""

def _normalize_tool_stats(stats):
    """归一化统计"""
```

## 核心组件三：Send Message（跨平台通信）

### 功能

```python
def send_message_tool(target, content, ...):
    """
    跨平台消息投递:
    - 发送到特定平台 (telegram, discord, slack, whatsapp)
    - 发送到特定 chat_id
    - 发送到 home channel
    - 支持媒体附件
    """
```

### 应用场景

- **Cron 结果投递**：定时任务完成后发送结果到指定平台
- **跨 Agent 通信**：一个 Agent 的结果作为另一个 Agent 的输入
- **监控通知**：检测到异常时主动发送通知

## 设计优越性

### 对比传统单 Agent

| 维度 | 单 Agent | Hermes 多 Agent |
|---|---|---|
| 上下文窗口 | 受限于单个模型 | 每个子代理独立窗口 |
| 并行能力 | 串行 | 最多 3 路并行 |
| 模型多样性 | 单一模型 | 子代理可使用不同模型 |
| 安全性 | 全部权限 | 子代理受限沙箱 |
| 成本可见性 | 总成本不透明 | 每个子代理独立 token 追踪 |
| 异构编排 | 不支持 | ACP 支持外部 Agent |

### 子代理隔离的优越性

```
传统方案: 父 Agent 看到所有子 Agent 的每一步
→ 上下文窗口爆炸（每个工具调用都计入）
→ 中间错误干扰父 Agent 判断

Hermes 方案: 父 Agent 只看到摘要和 tool_trace
→ 上下文窗口节省（90%+ 的中间过程被隐藏）
→ 父 Agent 专注于编排和决策
→ 每个子代理有独立的迭代预算
```

## 配置与操作

### 子代理配置

```yaml
# config.yaml
delegation:
  provider: openrouter          # 使用专用 provider（可选）
  model: google/gemini-3-flash  # 使用廉价模型处理子任务
  max_iterations: 50            # 每个子代理最大迭代次数

# 或完全独立的端点
delegation:
  base_url: https://api.openai.com/v1
  api_key: sk-xxx
  model: gpt-4o-mini
```

### 使用示例

```python
# 单任务委派
delegate_task(
    goal="Debug the login failure issue",
    context="User reports 500 error on /api/login. Log shows: ...",
    toolsets=["terminal", "file"]
)

# 并行委派
delegate_task(
    tasks=[
        {"goal": "Fix login bug", "toolsets": ["terminal", "file"]},
        {"goal": "Update API docs", "toolsets": ["terminal", "file"]},
        {"goal": "Run test suite", "toolsets": ["terminal"]},
    ]
)
```

### 批量处理

```bash
# 命令行批量处理
hermes batch run --input prompts.jsonl --output results.jsonl \
  --model qwen3.6-plus --workers 4
```

## 与其他系统的关系

- [[tool-registry-architecture]] — 子代理通过 registry 获取受限工具集
- [[auxiliary-client-architecture]] — 子代理可配置独立的辅助模型
- [[credential-pool-and-isolation]] — 子代理共享或独立凭证池
- [[iteration-budget-and-delegation]] — 子代理独立的迭代预算
- [[gateway-session-management]] — send_message 跨平台投递依赖会话管理
- [[cron-scheduling]] — cron 任务通过 send_message 投递结果

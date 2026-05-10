---
title: /goal — Ralph 循环目标锁定
created: 2026-05-10
updated: 2026-05-10
type: concept
tags: [agent, agent-loop, goal, ralph-loop, persistence]
sources: [hermes_cli/goals.py]
---

# `/goal` — Ralph 循环目标锁定

## 概述

v0.13.0 把 **Ralph loop**（让 Agent 锁在一个目标上，每轮检查是否达成，没达成就继续）做成 Hermes 的一等公民斜杠命令。

**问题域**：长任务里，Agent 容易在多轮对话后**忘掉最初目标**——上下文压缩、工具结果占带宽、用户中途插话都会稀释。`/goal <text>` 把目标写到 session 元数据里，每轮用辅助模型作为**judge** 评估"是否达成"，未达成自动继续。

源码：`hermes_cli/goals.py`（593 行）。

## 状态结构

```python
# goals.py:108  GoalState
@dataclass
class GoalState:
    goal: str
    status: str = "active"           # active | paused | done | cleared
    turns_used: int = 0
    max_turns: int = DEFAULT_MAX_TURNS
    created_at: float = 0.0
    last_turn_at: float = 0.0
    last_verdict: Optional[str] = None        # "done" | "continue" | "skipped"
    last_reason: Optional[str] = None
    paused_reason: Optional[str] = None       # 例如 "max_turns_reached"
    consecutive_parse_failures: int = 0       # judge JSON 解析失败连击
```

`to_json` / `from_json` 保证持久化。

## Judge Prompt

`goals.py:GOAL_JUDGE_SYSTEM_PROMPT` 原文：

> You are a strict judge evaluating whether an autonomous agent has achieved a user's stated goal. You receive the goal text and the agent's most recent response. Your only job is to decide whether the goal is fully satisfied based on that response.
>
> A goal is DONE only when:
> - The response explicitly confirms the goal was completed, OR
> - The response clearly shows the final deliverable was produced, OR
> - The response explains the goal is unachievable / blocked / needs user input (treat this as DONE with reason describing the block).
>
> Otherwise the goal is NOT done — CONTINUE.
>
> Reply ONLY with a single JSON object on one line:
> `{"done": <true|false>, "reason": "<one-sentence rationale>"}`

判定输入是 `goal` + agent 最近一次 response，**不灌整段对话**——judge 关注"最新输出"而不是过程。

## 触发流程

```text
用户: /goal 把 fixtures 目录的 SQL 全部从 MySQL 转成 Postgres

GoalManager.set(goal=...)  → 保存 GoalState
                            ↓
Agent 跑一轮（read files, edit, run tests）
                            ↓
judge_goal(goal, last_response)  → {"done": false, "reason": "..."}
                            ↓
状态机：turns_used += 1
                            ↓
未达 max_turns → 注入隐式 user message "continue"，再跑一轮
达 max_turns → status="paused", paused_reason="max_turns_reached"
              用户可 /goal resume 继续

judge {"done": true, "reason": "..."} → status="done"
                                        last_verdict="done"
```

`/goal resume` 在 `goals.py:546` 注释里显式给出 UX：

```
"Then /goal resume to continue."
"Use /goal resume to keep going, or /goal clear to stop."
```

## 持久化

```python
# goals.py:175
def load_goal(session_id: str) -> Optional[GoalState]: ...
def save_goal(session_id: str, state: GoalState) -> None: ...
def clear_goal(session_id: str) -> None: ...
```

存储介质：**SessionDB.state_meta**，key = `f"goal:{session_id}"`（`_meta_key`，`goals.py:148-`）。
和 session 同生命周期——`/resume <session>` 切回老 session 时 goal 状态跟着回来。

`_DB_CACHE` 按 `hermes_home` 路径缓存 SessionDB 实例，防止每次 `/goal` 都重新打开 sqlite 文件（profile 切换时缓存按 home 路径分隔）。

## 防御性设计

- **`consecutive_parse_failures`**：judge 返回的不是合法 JSON 时累加，超过阈值停止自动续跑，避免坏 judge 导致死循环
- **`max_turns`** 默认值在 `DEFAULT_MAX_TURNS`，用户可在 `/goal <text> --max-turns N` 覆盖
- **judge 用辅助模型**（`auxiliary.task=goal_judge` 或回退到 main），不污染主对话 prompt cache
- **`paused_reason`** 用于 UI 显示具体停止原因（max_turns / parse_failures / 用户手动）

## 与其它机制的关系

| 机制 | 解决什么 | 持久层 |
|---|---|---|
| Agent loop（每轮 LLM 决定下一步） | 短任务 | conversation history |
| Context Compressor | 长对话超 token 时压缩 | 修改 conversation history |
| `/steer <prompt>` | 中段插入提示 | next-turn note，不入 history |
| `/queue <prompt>` | 排队下一指令 | next-user-message queue |
| **`/goal <text>`** | **跨多轮锁住目标** | **SessionDB.state_meta** |
| [[kanban-multi-agent]] | 跨多 worker / 跨进程 | SQLite tasks 表 |

## CLI / TUI 接口

| 命令 | 行为 |
|---|---|
| `/goal <text>` | 设置 active goal，下轮起 judge |
| `/goal status` | 显示当前 goal、turns_used、last_verdict、last_reason |
| `/goal pause` | 暂停自动续跑（active → paused，paused_reason="user") |
| `/goal resume` | 恢复（paused → active） |
| `/goal clear` | 清空，等价 status=cleared |

ACP 客户端（Zed/VS Code/JetBrains）同样支持 `/goal`，因为它本质上是 Session 上的元数据操作，不依赖具体 frontend。

## 关键源码锚点

- `hermes_cli/goals.py:108` — `GoalState` dataclass
- `hermes_cli/goals.py:148` — `_meta_key` SessionDB 命名
- `hermes_cli/goals.py:174-208` — load/save/clear
- `hermes_cli/goals.py:282` — `judge_goal` 核心
- `hermes_cli/goals.py:391-410` — `GoalManager.set / has_goal`
- `hermes_cli/goals.py:546-562` — pause/resume UX 文案

## 相关页面

- [[agent-loop-and-prompt-assembly]] — Agent 主循环
- [[kanban-multi-agent]] — 多 worker 版的"完成不放弃"
- [[gateway-session-management]] — SessionDB 是 goal 的持久化底层
- [[auxiliary-client-architecture]] — judge 走辅助客户端

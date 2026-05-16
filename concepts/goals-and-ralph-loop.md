---
title: Goals 与 Ralph Loop
created: 2026-05-16
updated: 2026-05-16
type: concept
tags: [agent, agent-loop, cli, automation, context-management]
sources: [hermes_cli/goals.py, cli.py, gateway/run.py]
---

# Goals 与 Ralph Loop

## 概述

Goals 是 v2026.5.x 引入的**跨轮次持久目标**机制（`feat: /goal — persistent cross-turn goals (Ralph loop) #18262`）。实现位于 `hermes_cli/goals.py`（756 行），模块文档字符串直接称其为 "the Ralph loop for Hermes"。

一个 goal 是一个**长期存在的用户目标**，会跨多个对话轮次保持，直到达成或耗尽预算。

## Ralph Loop 是什么

每一轮结束后，一个小型 **judge 调用**（辅助模型）被询问："助手最后这条回复是否满足了目标？"

- **未满足** → 一条 **continuation prompt** 被喂回**同一个 session**，Hermes 继续工作
- **满足** / 轮次预算耗尽（`DEFAULT_MAX_TURNS = 20`）/ 用户暂停或清除 / 真实用户消息到达（抢占并暂停循环）→ 循环停止

judge 契约由 `JUDGE_SYSTEM_PROMPT` 定义，遵循 **fail-OPEN**（judge 出错时视为未阻塞继续），连续 3 次解析失败后自动暂停。

## 关键设计：不污染 prompt cache

Goal **不注入系统提示**。continuation 是作为**普通用户消息**通过 `run_conversation` 追加的（`CONTINUATION_PROMPT_TEMPLATE` / `CONTINUATION_PROMPT_WITH_SUBGOALS_TEMPLATE`）。

这是刻意为之——保持 [[prompt-caching-optimization]] 的 prefix cache 完好，避免 toolset 切换。

## 数据模型与持久化

- **`@dataclass GoalState`**：goal 文本、状态、轮次计数器、`subgoals: List[str]`
- **`GoalManager`** 类把它接入 `cli.py` 和 `gateway/run.py`
- **存储**：SessionDB 的 `state_meta` 表，键 `goal:<session_id>`，通过 `get_meta` / `set_meta` 读写（JSON 序列化 `to_json` / `from_json`）

因为存在 SessionDB，`/resume` 能重新接上 goal。

## 命令

| 命令 | 处理函数 | 说明 |
|---|---|---|
| `/goal <text>\|status\|pause\|resume\|clear` | `_handle_goal_command`（cli.py:8516） | 设置/查询/暂停/恢复/清除目标 |
| `/subgoal <text>\|remove <n>\|clear` | `_handle_subgoal_command`（cli.py:8582） | 用户追加的子目标，附加到当前 `/goal` |

## 配置

- `goals.max_turns`：轮次预算（`hermes_cli/config.py:1189`）
- `auxiliary.goal_judge.max_tokens`：judge 模型可调项

## 相关页面

- [[agent-loop-and-prompt-assembly]] — goal continuation 走标准对话循环
- [[prompt-caching-optimization]] — goal 刻意不进系统提示以保护缓存
- [[cron-scheduling]] — 另一种自动化触发机制
- [[auxiliary-client-architecture]] — judge 调用走辅助模型

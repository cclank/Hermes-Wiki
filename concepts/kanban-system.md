---
title: Kanban 协作看板系统
created: 2026-05-16
updated: 2026-05-16
type: concept
tags: [architecture, module, agent, delegation, concurrency, kanban]
sources: [tools/kanban_tools.py, hermes_cli/kanban_db.py, hermes_cli/kanban_diagnostics.py, plugins/kanban/]
---

# Kanban 协作看板系统

## 概述

Kanban 是 Hermes 在 v2026.5.x 引入的**持久化、SQLite 支撑的多 Agent 协作看板**（`feat(kanban): durable multi-profile collaboration board #17805`，2026-04-30 落地，squash 自 PR #16100 的 22 个迭代提交）。

它是 Hermes 的**第 5 种多 Agent 运行时机制**——与 [[multi-agent-architecture]] 中的 delegate_task / Mixture of Agents / Background Review / send_message 并列。区别在于：其他四种都是**进程内、同步、临时**的；Kanban 是**跨进程、异步、可崩溃恢复、可人工介入、可审计**的方案。

## 数据模型

- **存储**：`~/.hermes/kanban/<board>/kanban.db`（SQLite，WAL 模式）
- **DB 内核**：`hermes_cli/kanban_db.py`（约 4839 行）
- **核心表**（`CREATE TABLE` ~754-890 行）：`tasks`、`task_links`（parent→child DAG）、`task_runs`（尝试历史）、`task_comments`、`task_events`（审计日志）、`kanban_notify_subs`
- **任务生命周期列**：`triage → todo → ready → running → blocked → done → archived`
- **`Task` dataclass**（line 559）：id、title、body、assignee、status、priority、`tenant`、`workspace_kind`（`scratch`/`dir`/`worktree`）、`workspace_path`、`skills`（JSON 数组）、`max_runtime_seconds`、`max_retries`、`current_run_id`

并发安全：CAS 原子认领（claim）、通过 `/proc/<pid>/status` 检测崩溃、认领 TTL `DEFAULT_CLAIM_TTL_SECONDS = 15min`、幂等键。

## 多 Board / 多 Profile

「一次安装，多个看板」。`kanban_db.py` 提供完整 board 管理：`create_board` / `list_boards` / `remove_board` / `get_current_board` / `set_current_board`。每个 board 有独立的 DB、workspace 目录和 dispatcher。

Board 选择优先级：`HERMES_KANBAN_DB` 环境变量 → `HERMES_KANBAN_BOARD` 环境变量 → 当前 board 文件。Board 内部任务再按 `tenant` 命名空间隔离。

## Dispatcher 与 Orchestrator

### Dispatcher

默认**嵌在 gateway 进程内运行**（`kanban.dispatch_in_gateway: true`），每 60 秒 tick 一次。`dispatch_once()`（line 3666）：

1. 回收过期认领
2. 把 ready 任务提升为 running
3. spawn `hermes -p <assignee> chat -q "work kanban task <id>"`，注入 `HERMES_KANBAN_TASK` / `HERMES_KANBAN_RUN_ID` / `HERMES_KANBAN_BOARD` 环境变量，自动加载 `--skills kanban-worker`

`hermes kanban daemon` 独立守护进程模式已**废弃**。

### Orchestrator

Orchestrator = 一个加载了 `kanban` 工具集但**没有** `HERMES_KANBAN_TASK` 的 profile（`_check_kanban_orchestrator_mode` 判定）。它把大目标拆解，用 `kanban_create` 带 `parents=[...]` 依赖边 fan-out，然后完成自己那张卡。

`skills/devops/kanban-orchestrator/SKILL.md` 在 v2026.5.x 从 2.0.0 升到 3.0.0：去掉了硬编码的 8 个专家角色，改为 **Step-0 用 `hermes profile list` 发现可用 profile**（dispatcher 会静默丢弃未知 assignee，卡片会烂在 ready 列）。

## 工具集 — `tools/kanban_tools.py`（1139 行）

注册 9 个工具：`kanban_show`、`kanban_list`、`kanban_complete`、`kanban_block`、`kanban_heartbeat`、`kanban_comment`、`kanban_create`、`kanban_unblock`、`kanban_link`。

通过 `check_fn` 门控——普通 `hermes chat` 下 **schema 占用为零**。`kanban_list` / `kanban_unblock` 仅 orchestrator 可见。

## 诊断引擎 — `hermes_cli/kanban_diagnostics.py`（约 776 行）

对 `(task, events, runs)` 运行的通用规则引擎，输出带 `DiagnosticAction` 恢复建议的 `Diagnostic` 对象。`_RULES` 包含：

| 规则 | 说明 |
|---|---|
| `_rule_hallucinated_cards` | 检测 worker 声称的「我创建的卡」实际不存在 |
| `_rule_prose_phantom_refs` | 检测散文里引用的幽灵任务 |
| `_rule_repeated_failures` | 反复失败 |
| `_rule_repeated_crashes` | 反复崩溃 |
| `_rule_stuck_in_blocked` | 卡在 blocked |
| `_rule_stranded_in_ready` | ready 任务有 assignee 但无认领，超过 30 分钟（#23578） |

**幻觉门（hallucination gate）**：`complete_task`（line 2351）若发现幻觉卡片会抛 `HallucinatedCardsError`，发出 `completion_blocked_hallucination` 事件，且**不修改任务**，让 worker 重试。

**per-task `max_retries`** 列覆盖 dispatcher 级的 `kanban.failure_limit` 熔断阈值。

## Dashboard 插件 — `plugins/kanban/dashboard/`

`plugin_api.py`（约 1612 行）：dashboard session-token 鉴权后的 FastAPI router。端点 `/board`、`/tasks/{id}`、POST/PATCH `/tasks`、`/comments`、带 `reclaim_first` 的批量重新分配。Linear 风格 UI（拖拽列、任务抽屉、评论线程、运行历史、按 profile 分泳道、WebSocket 实时刷新、诊断徽章）。另附 `systemd/hermes-kanban-dispatcher.service`。

## 与其他多 Agent 机制对比

| 机制 | 进程模型 | 持久化 | 适用 |
|---|---|---|---|
| `delegate_task` | 进程内子 Agent | 否 | 一次性并行子任务 |
| Mixture of Agents | 进程内多模型 | 否 | 单次难题协同 |
| Background Review | 进程内守护线程 | 否 | 后台提炼 skill |
| `send_message` | 跨平台投递 | 部分 | Agent 间消息 |
| **Kanban** | **跨进程多 worker** | **是（SQLite）** | **持久、并行、可审计、可人工介入的工作流** |

orchestrator skill 明确指引：一次性推理优先用 `delegate_task`，需要持久/并行/可审计的工作才用看板。

## 相关页面

- [[multi-agent-architecture]] — 其他四种多 Agent 运行时机制
- [[worktree-isolation]] — Kanban 任务的 `worktree` workspace_kind
- [[configuration-and-profiles]] — 多 Profile 是 orchestrator fan-out 的基础

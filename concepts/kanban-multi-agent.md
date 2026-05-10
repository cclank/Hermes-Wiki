---
title: Kanban — 持久化多 Agent 协作板
created: 2026-05-10
updated: 2026-05-10
type: concept
tags: [architecture, agent, delegation, concurrency, durability]
sources: [hermes_cli/kanban.py, hermes_cli/kanban_db.py, hermes_cli/kanban_diagnostics.py, tools/kanban_tools.py, plugins/kanban/]
---

# Kanban — 持久化多 Agent 协作板

## 概述

v0.13.0 引入的**第 5 种多 Agent 运行机制**（前 4 种见 [[multi-agent-architecture]]）：

> 一个**持久化**的看板数据库 + 多个 Hermes 实例从板上**领任务、心跳上报、互相接力、最终交付**——一个安装可以挂多个 board，跨 profile 共享 worker logs/工作区。

与 `delegate_task`（同进程内 fork 子 Agent，最深 3 层）相比，Kanban 是**跨进程、跨重启、跨机器**的，靠 SQLite 状态机和 heartbeat 协议达成"team that actually finishes"。

## 模块组成

| 文件 | 行数 | 职责 |
|---|---|---|
| `hermes_cli/kanban_db.py` | 4740 | SQLite schema（tasks / runs / boards / profiles）、claim/heartbeat/reclaim 原语、迁移 |
| `hermes_cli/kanban.py` | 2228 | CLI 子命令 argparse 树（15 verb）+ 输出格式化 + `/kanban …` 路由 |
| `hermes_cli/kanban_diagnostics.py` | 649 | distress signal engine（无心跳/反复 crash/超时/spawn 失败/reclaim） |
| `tools/kanban_tools.py` | 1130 | LLM 可调用工具（worker 与 dispatcher 用） |
| `hermes_cli/kanban_specify.py` | — | `/kanban specify` 流程，让用户自然语言描述要拆几张卡 |
| `plugins/kanban/dashboard/plugin_api.py` | 1604 | dashboard 插件 API |
| `plugins/kanban/systemd/` | — | 独立 dispatcher 的 systemd unit（**DEPRECATED**——默认 dispatcher 跑在 gateway 内） |

## 任务模型

```python
# kanban_db.py:Task
@dataclass
class Task:
    id: str
    title: str
    body: str
    assignee: Optional[str]
    status: str          # todo|ready|running|blocked|done|archived
    priority: int
    tenant: Optional[str]
    workspace_kind: str  # scratch|worktree|dir:<path>
    workspace_path: Optional[str]
    created_by: str
    created_at: int
    started_at: Optional[int]
    completed_at: Optional[int]
    result: Optional[str]
    skills: list[str]    # 推荐 worker 装上的 skill 列表
    max_retries: int     # per-task 重试预算
```

## 状态机

```text
                ┌────────┐
created  →   ┌──│  todo  │──→ ready ──→ running ──→ done
             │  └────────┘             ↑    │
             │                         │    ├─→ blocked  (need user)
             │                         │    ├─→ failed → retry until max_retries
             │                         │    └─→ archived (curator/user)
             │                         │
             │   heartbeat (every N s) │
             │                         │
             └─── dispatcher tick ─────┴── reclaim if last_heartbeat_at expired
```

**核心字段**（`kanban_db.py:781,843` 表结构）：

- `tasks.last_heartbeat_at INTEGER` —— worker 周期性写入
- `runs` 表跟踪同一 task 多次 run（complete/block/crash/timeout/spawn_failure/reclaim）
- 每个 run 有自己的 `last_heartbeat_at`、PID、handoff summary

`kanban_db.py:98` 注释明确写：

> dispatcher tick reclaims it. Workers that outlive this window should call `heartbeat_claim(task_id)` periodically.

## Workspace 隔离

`--workspace` 接受三种：

- **scratch** —— 临时目录，跑完丢
- **worktree** —— Git worktree，并发 worker 不会互相覆盖文件
- **dir:&lt;path&gt;** —— 指定目录

并发 sibling worker 通过**文件协调层**（v0.11 引入的 cross-agent file state coordination）共享文件状态，不抢同一行。

## 幻觉防护

`#20017 closed by` worker-created-card hallucination gate：worker 在自己 stdout 里说"我创建了卡片 K-42"时，dispatcher 必须校验该卡是否真的写进了 `tasks` 表，否则触发 **recovery UX**：

- 把幻觉报告标红
- 给 worker 一次 retry 机会，要求"实际去调 kanban tool 创建卡片"

避免 worker 编造已完成的工作。

## 诊断引擎

`kanban_diagnostics.py` 是**通用 distress signal**——它不绑死 hermes worker，理论上任何 worker 都能加：

| 信号 | 解释 |
|---|---|
| `no_heartbeat` | `last_heartbeat_at` 超过阈值 |
| `repeated_crash` | 同一 task 多次 spawn_failure |
| `timeout` | running 超过 task 上限 |
| `reclaim_loop` | 反复被 reclaim 没人完成 |

对应的修复路径由 dispatcher 决定：reassign / retry / mark failed。

## 多板与跨 profile 共享

v0.13 把**多板**作为基础原语：

- 一个 `$HERMES_HOME` 可以有多个 board（按 `tenant` 字段分）
- `--share` 让多个 profile 看同一个 board（共享 workspace、worker logs）

适合：在 dev/prod profile 分别有 LLM 凭据，但都要从同一个 task 池领活。

## Hallucination 之外的可靠性

- **Per-task `max_retries`**：超过就标 failed，不无限自循环
- **Auto-block on incomplete exit**：worker 异常退出但没填 result → 自动 block，要人介入
- **多 worker 心跳**：dispatcher 看心跳决定是否 reclaim，不靠 PID 单一信号

## CLI 接口

`hermes_cli/kanban.py:189` argparse 树（节选）：

```
hermes kanban init                  # 初始化 board
hermes kanban task create ...       # 加任务
hermes kanban task list             # 列任务（icon 状态指示）
hermes kanban boards [list|switch|share]
hermes kanban daemon [--force ...]  # 独立 dispatcher（DEPRECATED；默认走 gateway）
hermes kanban specify               # 自然语言拆卡
hermes kanban archive/restore
hermes kanban logs <task-id>        # 查 worker log
```

`/kanban …` 在 gateway / classic CLI / TUI 接同一套 argparse 树（`kanban.py:2181`）——单一真相源。

## Dashboard 集成

`plugins/kanban/dashboard/plugin_api.py` 1604 行——通过 dashboard plugin system（v0.13.0）注册 Kanban 标签页：任务列表、状态柱状图、worker log 实时流。

## 与其它机制对比

| 维度 | delegate_task | Mixture of Agents | Background Review | send_message | **Kanban** |
|---|---|---|---|---|---|
| 触发方 | LLM 自主调用 | LLM 自主调用 | 系统计数器 | LLM 自主调用 | **用户 / cron / API** |
| 并发数 | ≤ 3 同进程 | ≤ N 模型 | 1 fork | 1 平台投递 | **任意 worker** |
| 持久化 | ❌（进程内） | ❌ | ❌ | ❌ | ✅（SQLite） |
| 跨重启 | ❌ | ❌ | ❌ | ❌ | ✅ |
| 跨机器 | ❌ | ❌ | ❌ | ❌ | ✅（共享 db） |
| 失败重试 | ❌ | ❌ | ❌ | ❌ | ✅（max_retries） |
| 适用场景 | 一次性并行子任务 | 多模型 ensemble | 后台改 skill | 跨平台广播 | **长跑/可恢复的多任务流水线** |

## 相关页面

- [[multi-agent-architecture]] — 同一伞下的另外 4 种机制
- [[cron-scheduling]] — Cron + Kanban 联动：定时投递任务
- [[hook-system-architecture]] — dashboard plugin API
- [[goal-and-ralph-loop]] — 单 Agent 持久化的 `/goal`，与 Kanban 是不同层次的解法

## 相关源码

- `hermes_cli/kanban_db.py:781` — `tasks` 表 schema
- `hermes_cli/kanban_db.py:843` — `runs` 表 schema
- `hermes_cli/kanban_db.py:98-99` — heartbeat 文档
- `hermes_cli/kanban.py:189` — argparse 顶层
- `hermes_cli/kanban.py:2181` — `/kanban …` 路由桥
- `hermes_cli/kanban_diagnostics.py:1-` — distress engine
- `tools/kanban_tools.py:1-` — LLM tool 入口
- `plugins/kanban/dashboard/plugin_api.py` — dashboard 集成

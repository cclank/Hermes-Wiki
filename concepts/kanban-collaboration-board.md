---
title: Kanban 多 Profile 协作板
created: 2026-05-04
updated: 2026-05-04
type: concept
tags: [kanban, multi-profile, collaboration, sqlite, dispatcher, worker]
sources: [hermes_cli/kanban_db.py, hermes_cli/kanban.py, tools/kanban_tools.py, plugins/kanban/]
---

# Kanban 多 Profile 协作板

## 概述

`hermes kanban` 提供一个**SQLite 持久化、profile 无关的任务看板**，让多个 Profile 在同一台机器上协调工作——dispatcher（调度器）认领任务并 spawn worker agent，worker 用结构化 tool calls 回写状态，gateway 把 `completed` / `blocked` 事件 push 给最初的请求者。源码：

| 模块 | 行数 | 职责 |
|------|------|------|
| `hermes_cli/kanban_db.py` | 2765 | SQLite schema + CAS 写、claim 锁、worker 上下文构造 |
| `hermes_cli/kanban.py` | 1393 | `hermes kanban` CLI 子命令（15 动词）+ `--json` 输出 |
| `tools/kanban_tools.py` | 726 | Worker agent 用的 7 个结构化 tool（show/complete/block/heartbeat/comment/create/link） |
| `plugins/kanban/dashboard/` | — | Dashboard 看板 UI |
| `plugins/kanban/systemd/` | — | systemd unit 模板（dispatcher 守护进程） |

## 设计核心

### profile-agnostic 的协调原语

`kanban_db.py:1-11`：
> The board lives at `$HERMES_HOME/kanban.db` (profile-agnostic on purpose: multiple profiles on the same machine all see the same board, which IS the coordination primitive).

跨 Profile 共享同一个 `kanban.db` 文件——这本身就是协调机制。

### 并发 = WAL + BEGIN IMMEDIATE + CAS

`kanban_db.py:13-17`：
- WAL mode + `BEGIN IMMEDIATE` 写事务
- `tasks.status` / `tasks.claim_lock` 上的 CAS（compare-and-swap）更新
- SQLite 的 WAL lock 序列化 writer，最多一个 claimer 赢
- 输家观察到 0 行被影响，直接放弃——**没有重试循环、没有分布式锁机器**

### 解耦 workspace 与 git

`workspace_kind` 字段把协作从 git worktree 解耦——research / ops / digital-twin 工作流和编码工作流共存：

```python
VALID_WORKSPACE_KINDS = {"scratch", "worktree", "dir"}
```

- `scratch`: `$HERMES_HOME/kanban/workspaces/<task_id>/`
- `worktree`: 独立 git worktree（编码工作流）
- `dir:<path>`: 用户指定路径

## SQLite Schema

`kanban_db.py:244-361` 定义 5 张表：

### tasks

```sql
CREATE TABLE tasks (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    body                 TEXT,
    assignee             TEXT,
    status               TEXT NOT NULL,    -- triage|todo|ready|running|blocked|done|archived
    priority             INTEGER DEFAULT 0,
    created_by           TEXT,
    created_at           INTEGER NOT NULL,
    started_at           INTEGER,
    completed_at         INTEGER,
    workspace_kind       TEXT NOT NULL DEFAULT 'scratch',
    workspace_path       TEXT,
    claim_lock           TEXT,             -- CAS guard
    claim_expires        INTEGER,          -- 默认 15 分钟
    tenant               TEXT,
    result               TEXT,
    idempotency_key      TEXT,
    spawn_failures       INTEGER NOT NULL DEFAULT 0,
    worker_pid           INTEGER,
    last_spawn_error     TEXT,
    max_runtime_seconds  INTEGER,
    last_heartbeat_at    INTEGER,
    current_run_id       INTEGER,          -- 指向 task_runs（denormalized）
    workflow_template_id TEXT,             -- v2 forward-compat
    current_step_key     TEXT,             -- v2 forward-compat
    skills               TEXT              -- JSON array
);
```

### task_runs（重试历史）

`kanban_db.py:312-332`：每次 dispatcher 认领任务都新插一行——claim 状态、PID、心跳、runtime cap、structured summary 都在 run 上而不是 task 上，**支持重试历史**。

```sql
CREATE TABLE task_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id             TEXT NOT NULL,
    profile             TEXT,
    step_key            TEXT,                -- v2
    status              TEXT NOT NULL,       -- running|done|blocked|crashed|timed_out|failed|released
    claim_lock          TEXT,
    claim_expires       INTEGER,
    worker_pid          INTEGER,
    max_runtime_seconds INTEGER,
    last_heartbeat_at   INTEGER,
    started_at          INTEGER NOT NULL,
    ended_at            INTEGER,
    outcome             TEXT,                -- completed|blocked|crashed|timed_out|spawn_failed|gave_up|reclaimed
    summary             TEXT,
    metadata            TEXT,
    error               TEXT
);
```

### kanban_notify_subs（gateway 闭环）

`kanban_db.py:338-347`：gateway 的 kanban-notifier watcher 订阅 `task_events`，把 `completed` / `blocked` / `spawn_auto_blocked` 事件 push 给最初下单的 (platform, chat, thread)：

```sql
CREATE TABLE kanban_notify_subs (
    task_id       TEXT NOT NULL,
    platform      TEXT NOT NULL,
    chat_id       TEXT NOT NULL,
    thread_id     TEXT NOT NULL DEFAULT '',
    user_id       TEXT,
    created_at    INTEGER NOT NULL,
    last_event_id INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, platform, chat_id, thread_id)
);
```

### task_links / task_comments / task_events

- `task_links` — 父子任务关系，索引覆盖双向查询
- `task_comments` — 人和 worker 的评论流
- `task_events` — append-only 审计日志（payload 为 JSON）

## Claim TTL

`DEFAULT_CLAIM_TTL_SECONDS = 15 * 60`（15 分钟）。运行任务的 worker 应定期调 `heartbeat_claim()`。超时后下一个 dispatcher tick 回收任务。

## Worker 上下文上限

`kanban_db.py:48-58` 防止病态 board 把 LLM prompt 撑爆：

| 常量 | 值 | 含义 |
|------|---|------|
| `_CTX_MAX_PRIOR_ATTEMPTS` | 10 | 最近 N 次重试展开 |
| `_CTX_MAX_COMMENTS` | 30 | 最近 N 条评论展开 |
| `_CTX_MAX_FIELD_BYTES` | 4 KB | 单 summary/error/metadata/result |
| `_CTX_MAX_BODY_BYTES` | 8 KB | task.body（开题贴） |
| `_CTX_MAX_COMMENT_BYTES` | 2 KB | 单条评论 |

## Worker 工具集（HERMES_KANBAN_TASK gating）

`tools/kanban_tools.py:42-49`：

```python
def _check_kanban_mode() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK"))
```

普通 `hermes chat` schema 中**零** kanban tools。Dispatcher spawn worker 时设环境变量 `HERMES_KANBAN_TASK=<task_id>`，worker 才看到 7 个 tool（`tools/kanban_tools.py:665-726`）：

| 工具 | Emoji | 用途 |
|------|------|------|
| `kanban_show` | 📋 | 读任务全状态（task row、parents、children、comments） |
| `kanban_complete` | ✔ | 标记 done + 写 result |
| `kanban_block` | ⏸ | 标记 blocked + 写 reason |
| `kanban_heartbeat` | 💓 | 续 claim（防 15 分钟超时被回收） |
| `kanban_comment` | 💬 | 加评论 |
| `kanban_create` | ➕ | 创建子任务（fan-out workflow） |
| `kanban_link` | 🔗 | 显式连边 parent-child |

### 为什么不直接 shell 调 `hermes kanban`

`tools/kanban_tools.py:7-19`：

1. **后端可移植**：worker 的 terminal 可能指向 Docker / Modal / Singularity / SSH——容器里没有 `hermes` 也没有 mount kanban.db。Tool 在 agent 的 Python 进程里跑，永远能到 `~/.hermes/kanban.db`。
2. **避开 shell 引号陷阱**：`--metadata '{"x": [...]}'` 经 shlex+argparse 易碎，结构化 tool args 直接跳过。
3. **更好的错误**：tool failure 返回结构化 JSON，模型能 reason，不用 parse stderr。

## 三种触发路径

| 用户 | 路径 |
|------|------|
| 人类终端 | `hermes kanban list / show / create / assign / ...` |
| 人类 Web | `hermes dashboard` 的 kanban tab |
| 人类聊天 | `/kanban list` 网关斜杠命令 |
| Worker agent | 7 个结构化 tool |

前三条路径**完全绕过 agent**——不动 prompt cache，不耗模型 token。

## 状态流转

```
triage / todo  ──[ready]──▶  ready
ready          ──[claim]──▶  running
running        ──[heartbeat]─▶ running
running        ──[complete]─▶ done
running        ──[block]──▶  blocked
running        ──[timeout]─▶ ready  (claim_lock 过期，下一个 tick 回收)
blocked        ──[unblock]─▶ ready
done / blocked ──[archive]─▶ archived
```

## 相关 Skills

```
skills/devops/kanban-orchestrator   — 编排者 skill（拆分任务、派单）
skills/devops/kanban-worker         — 工人 skill（消费 7 工具）
optional-skills/creative/kanban-video-orchestrator — 视频流水线编排
```

## CLI 验证

```bash
hermes kanban list                              # 列任务
hermes kanban create --title "..." --body "..." # 建任务
hermes kanban show <id>                         # 看详情
hermes kanban assign <id> <profile>             # 派单
hermes kanban list --json                       # 机器可读
```

## 验证 PR

- `c868425` `feat(kanban): durable multi-profile collaboration board (#17805)`
- `97d6f25` `test(toolsets): include kanban in expected post-#17805 toolset assertions`
- `0dd8e3f` `rename: video-orchestrator → kanban-video-orchestrator`

## 与其他系统的关系

| 系统 | 关系 |
|------|------|
| **多 Agent 架构** | 第 5 种多 Agent 模式：跨 Profile 通过共享 SQLite 协调（区别于 delegate_task / MoA / Background Review / send_message） |
| **Worktree Isolation** | `workspace_kind=worktree` 直接复用 worktree 隔离 |
| **Gateway** | `kanban_notify_subs` 让网关把 task 完成事件推回原会话 |
| **Tool Registry** | 7 个 kanban tool 都通过 `registry.register(check_fn=_check_kanban_mode)` 注册——env 变量 gating 是注册系统的一等公民 |
| **Dashboard** | `plugins/kanban/dashboard/` 提供看板 UI |

## 相关概念

- [[multi-agent-architecture]] — 现已扩展为 5 种多 Agent 机制
- [[tool-registry-architecture]] — `check_fn` gating 机制
- [[worktree-isolation]] — workspace_kind=worktree 复用
- [[messaging-gateway-architecture]] — gateway notify 闭环

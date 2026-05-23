---
title: Kanban — 持久多 Agent 看板
created: 2026-05-14
updated: 2026-05-14
type: concept
tags: [kanban, multi-agent, durable, sqlite, dispatcher, architecture, module]
sources: [tools/kanban_tools.py, hermes_cli/kanban.py, hermes_cli/kanban_db.py, hermes_cli/kanban_diagnostics.py, plugins/kanban/dashboard/plugin_api.py, hermes_cli/commands.py]
version: v0.13.0
---

# Kanban — 持久多 Agent 看板

## 概述

v0.13.0 落地的 **durable multi-profile collaboration board**：一份 SQLite 库 + 一个 dispatcher，把任务分发给多个 Hermes worker，全部具备心跳、reclaim、zombie 检测、retry budget、hallucination gate。它取代了之前几次实验性的看板尝试（首版被 revert 后重写，`#17805`）。

> ⚠️ 关键定位：Kanban 是 Hermes 第 4 类多 Agent 运行时机制（前三是 Delegate Task / Mixture of Agents / Background Review，见 [[multi-agent-architecture]]）。它是唯一**持久 + 跨 profile**的协作面。

## 文件清单

| 文件 | 行数 | 角色 |
|------|------|------|
| `hermes_cli/kanban_db.py` | 4839 | SQLite schema + connection + dispatcher core |
| `hermes_cli/kanban.py` | 2252 | `hermes kanban` CLI (15+ verbs) |
| `tools/kanban_tools.py` | 1139 | Worker / orchestrator 用的结构化工具 |
| `hermes_cli/kanban_diagnostics.py` | 776 | distress signal 诊断引擎 |
| `hermes_cli/kanban_specify.py` | 266 | 任务规范化辅助 |
| `plugins/kanban/dashboard/plugin_api.py` | 1612 | Dashboard 接入 |
| `plugins/kanban/systemd/` | — | 长跑服务 unit |

总计 ~10.9k 行新代码。

## 数据模型

`SCHEMA_SQL`（`hermes_cli/kanban_db.py:754`）：

```sql
CREATE TABLE tasks (
    id                   TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    body                 TEXT,
    assignee             TEXT,
    status               TEXT NOT NULL,           -- VALID_STATUSES
    priority             INTEGER DEFAULT 0,
    created_by           TEXT,
    created_at           INTEGER NOT NULL,
    started_at           INTEGER,
    completed_at         INTEGER,
    workspace_kind       TEXT NOT NULL DEFAULT 'scratch',
    workspace_path       TEXT,
    claim_lock           TEXT,                    -- CAS token for ownership
    claim_expires        INTEGER,
    tenant               TEXT,
    result               TEXT,
    idempotency_key      TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    worker_pid           INTEGER,
    last_failure_error   TEXT,
    max_runtime_seconds  INTEGER,
    last_heartbeat_at    INTEGER,
    current_run_id       INTEGER,
    workflow_template_id TEXT,                    -- v2 forward-compat
    current_step_key     TEXT,
    skills               TEXT,                    -- JSON 数组，附加给 worker
    max_retries          INTEGER                  -- per-task circuit breaker override
);

CREATE TABLE task_links     (parent_id, child_id);     -- 父子依赖
CREATE TABLE task_comments  (...);                       -- 评论流
CREATE TABLE task_events    (...);                       -- 事件流
CREATE TABLE task_runs      (...);                       -- 每次 run 的记录
CREATE TABLE kanban_notify_subs (...);                   -- 订阅通知
```

`VALID_STATUSES = {"triage", "todo", "ready", "running", "blocked", "done", "archived"}`（line 93）。

## Board 与 profile 模型

**Profile 共享**：board 落在 `<root>/kanban.db`，`<root>` 是 *shared Hermes root* —— 所有 profile 的父目录。设计意图是 profile **必须**坍缩到一个 board，因为 board 本身就是跨 profile 的协调原语。

**多 board**：可以再开 `<root>/kanban/boards/<slug>/kanban.db` —— 每个 board 自成 SQLite，互不可见。第一个 board 仍叫 `default` 且为 backwards compat 存于 `<root>/kanban.db`（不在 `boards/default/` 下）。

**Board 选择优先级**（最高在前，`hermes_cli/kanban_db.py:28-43`）：

1. `--board` CLI 参数 / dashboard `?board=` query
2. `HERMES_KANBAN_BOARD` env（dispatcher 注给 worker）
3. `HERMES_KANBAN_DB` env（pin 路径）
4. `<root>/kanban/current` 文件（`hermes kanban boards switch <slug>` 写入）
5. 默认 `default`

dispatcher 把 `HERMES_KANBAN_DB / HERMES_KANBAN_WORKSPACES_ROOT / HERMES_KANBAN_BOARD` 注入到 worker 子进程的 env，确保 worker 看到的是 dispatcher claim 时的同一份 DB，避免 symlink / Docker 布局差异。

## 并发模型

- WAL mode SQLite
- 写事务用 `BEGIN IMMEDIATE`
- **CAS** 更新 `tasks.status` 与 `tasks.claim_lock`
- SQLite 自身的 WAL 锁串行化写者 —— 同一 task 最多一个 claimer 获胜
- 失败者看到 affected rows = 0 即放手，**不重试**，**不需要分布式锁机制**
- CAS 是 *per-board* 的（每个 board 独立 DB），多 board 安装自动获得相同原子性保证

## 工具表面（worker / orchestrator）

`tools/kanban_tools.py` 注册 9 个工具，全部归入 `kanban` toolset：

| 工具 | 用途 |
|------|------|
| `kanban_show`      | 看单 task 详情 |
| `kanban_list`      | board 列表 (orchestrator-only) |
| `kanban_complete`  | worker 完成自己 claim 的 task |
| `kanban_block`     | worker 标记 task 为 blocked |
| `kanban_heartbeat` | 续约心跳 |
| `kanban_comment`   | 写评论 |
| `kanban_create`    | 创建 task |
| `kanban_unblock`   | unblock task (orchestrator-only) |
| `kanban_link`      | 建 parent→child 依赖 |

注册门 (`_check_kanban_mode` line 60)：

```python
def _check_kanban_mode() -> bool:
    if os.environ.get("HERMES_KANBAN_TASK"):
        return True               # dispatcher-spawned worker
    return _profile_has_kanban_toolset()
                                  # orchestrator profile 显式启用
```

普通 `hermes chat` session **看不到任何 kanban 工具**——它们既不在 schema 里也不在 system prompt 里。这把 kanban "面" 完全隐藏在 dispatcher / orchestrator 之外。

为什么用 tool 而不是 shell 调用 `hermes kanban`：

1. **后端可移植性**：worker 跑在 Docker / Modal / Singularity / SSH 时，容器里没 `hermes` 命令，DB 路径也不一定挂得到。Tool 走 Python 进程内 SQLite，永远到得了 `~/.hermes/kanban.db`。
2. **无 shell 引用陷阱**：`--metadata '{"x": [...]}'` 通过 shlex+argparse 极脆弱。结构化 tool args 跳过。
3. **更好的错误**：tool failure 返回结构化 JSON，模型能推理；shell 失败只能解析 stderr。

人类用户继续使用 CLI / dashboard / `/kanban` 斜杠命令，三条路径**都绕过 agent**。Tools 只服务于 worker agent 把控制权交还给 kernel 的那一步。

## CLI 表面

`hermes kanban <verb>`（`hermes_cli/kanban.py`）—— 15 个 verb（`hermes_cli/commands.py:173-177`）：

```
list / ls / show / create / assign / link / unlink /
claim / comment / complete / block / unblock / archive /
tail / dispatch / context / init / gc
```

所有 verb 都有 `--json` 输出。`/kanban …` 斜杠命令复用同一 argparse surface（用 shlex 解析单字符串）。

## 可靠性栈

### Heartbeat + reclaim

- worker 周期性 `kanban_heartbeat` 续约
- 长时间未续约的 task 被 dispatcher 视为放弃，重新分配
- `claim_lock` + `claim_expires` 字段提供时间窗口
- darwin zombie worker 检测（`#20188`，`tools/kanban_db.py:3005` 注释 + `Z (zombie)` proc state 检查）

### Retry budget

- `tasks.consecutive_failures` 在 spawn 失败 / timeout / crash 任一情形递增（line 2887 `DEFAULT_FAILURE_LIMIT = 2`）
- 成功完成时清零
- `max_retries` 字段允许 per-task 覆盖（`#21330`）—— `max_retries=1` 即首次失败就 block，不再尝试

### Hallucination gate

worker 声称"我创建了卡片 X"但卡片 X 不存在时不静默失败，回报错误（`#20232`）。

### Distress 诊断

`hermes_cli/kanban_diagnostics.py`（776 行）—— 通用 distress signal 引擎（`#20332`），从异常文本中提炼 "task is stuck because Y"。

### Worker task-ownership 强制

`_enforce_worker_task_ownership(tid)`（`tools/kanban_tools.py`）防止 worker 用自己持有的 claim_lock 操作不属于自己的 task。

### Auto-block on incomplete exit

worker 进程退出但 task 还在 `running` —— dispatcher 自动 block（`#21214`，含 shutdown race 修复）。

## Dispatcher

dispatcher 是 *gateway 内嵌* 的 cron-ticker 线程默认启动；也可以 `hermes kanban dispatch` 独立跑。

工作步骤：

1. 选 `ready` 状态的 task（按 priority 降序）
2. CAS 把 status → `running` + 写 claim_lock + 注入 env
3. spawn `hermes` 子进程（profile / workspace 按 task 字段决定），env 注入 `HERMES_KANBAN_TASK=<id>` + board pin
4. monitor 心跳 + 进程状态
5. 完成 / 失败 / timeout / crash 走 `_record_task_failure` / `_record_task_success`

## Dashboard 集成

`plugins/kanban/dashboard/plugin_api.py` (1612 行) 提供：

- inline create form 含 workspace kind + path 选择（`#19679`）
- per-platform home-channel 通知开关（`#19864`）
- 任务编辑 + 完成总结保留（`#20195`）
- pending / running / done 列拖拽（drop → running 受限，dashboard API 拒绝直接转 running，`#19705`）
- code/pre styling 跨主题（`#21247`）
- per-tenant 过滤（`#21349`）
- event-stream cancellation 视为正常 shutdown（`#21222`）

## Worker logs + workspaces

- `<root>/kanban/workspaces/` — per-task workspace 根（profile 共享）
- `<root>/kanban/logs/` — per-task 日志根
- `HERMES_KANBAN_WORKSPACES_ROOT` env 可独立 pin（dispatcher 注入 worker，确保两端一致）

## 相关页面

- [[multi-agent-architecture]] — Kanban 是第 4/5 种多 Agent 协作机制
- [[configuration-and-profiles]] — Profile 模型；为什么 board 跨 profile 共享
- [[cron-scheduling]] — gateway 内嵌 cron-ticker 同时驱动 Kanban dispatcher
- [[hook-system-architecture]] — kanban dashboard 通过插件 API 暴露

## 相关文件

- `tools/kanban_tools.py` — Worker / orchestrator tool 注册
- `hermes_cli/kanban.py` — CLI argparse 构造与 dispatch
- `hermes_cli/kanban_db.py` — schema + dispatcher core
- `hermes_cli/kanban_diagnostics.py` — distress signal
- `plugins/kanban/dashboard/plugin_api.py` — Dashboard 接入
- `plugins/kanban/systemd/` — 长跑 unit

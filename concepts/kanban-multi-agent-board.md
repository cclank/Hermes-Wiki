---
title: Kanban Multi-Agent Board
created: 2026-05-22
type: concept
tags: [kanban, multi-agent, delegation, durable, sqlite, dispatcher, worker]
sources: [plugins/kanban/, hermes_cli/kanban.py, hermes_cli/kanban_db.py, hermes_cli/kanban_decompose.py, hermes_cli/kanban_swarm.py, hermes_cli/kanban_diagnostics.py, tools/kanban_tools.py, gateway/run.py]
---

# Kanban 多 Agent 看板

> **2026-05-23 更新**：新增 `hermes kanban promote <id> [--ids id...]` 子命令，手动 todo→ready 恢复（详见 § CLI 命令一览）。
>
> **2026-05-29 更新（hermes-agent `689ef5e2`）— 可靠性 wave**：
>
> - **`POST /api/plugins/kanban/runs/{run_id}/terminate`** 端点（commit `9d4fda995`）—— `plugins/kanban/dashboard/plugin_api.py:1317-1318`（`@router.post("/runs/{run_id}/terminate")` → `terminate_run_endpoint(...)`），测试 `tests/plugins/test_kanban_worker_runs.py:306-425`
> - **per-profile 并发上限 + `default_assignee` 回退**（`3b6347af1`，#34244, #27145, #21582）
> - **CLI dispatch 遵循 config 的 `max_in_progress`/`max_spawn`**（`69b74c15a`，#34337）
> - **SQLite 抗撕裂写**：`secure_delete` + `cell_size_check` + `synchronous=FULL`（`6416dd518`）
> - **zombie reaper 从 `dispatch_once` 上提** + 崩溃 worker 宽限期检测（`ffdc937c1` / `c002668ff`）
> - **blocked / iteration-exhausted 三处缺口修复**（`592a4ffb6`，#29747）
> - **worker SIGTERM 必须终止进程**（`f30db14ce`，#28181）
> - **worker 运行时活动桥接到看板心跳**（`bc31ee5cf`，#31752）
> - **Windows init lock guard + sqlite 并发加固**（`3ba896273` / `90b6b3d18`）
> - **close kanban.db FD after every connect()**（`ebe04c66c`）
> - **corrupt-DB 备份文件名改为内容寻址**（`6f9182cb3`）
> - **`unblock` 加 `--reason` flag 对称 `block`**（`ae6817f7f`，#30897）
> - **STATUS_DEAD for terminal OAuth failures**（凭据池侧，`86a389fee`，#32849）
>
> 详见 [[2026-05-29-update#7-kanban-可靠性-wave]]。

## 概述

Kanban 是 Hermes 在 v0.13 (v2026.5.7) 引入的**可持久化多 Agent 协作看板**。和 [[multi-agent-architecture]] 中的 4 种 in-process 机制（delegate_task / MoA / Background Review / send_message）不同，Kanban 是**跨 Session、跨 Profile、跨进程**的协调原语：

- 任务存在 SQLite，重启不丢
- 多个 Hermes worker 并发跑，靠 WAL + CAS 原子认领
- 嵌入 Gateway 的 dispatcher 每 60s tick 一次，自动发任务
- 心跳 / claim TTL / 僵尸进程检测 / 失败熔断 / 幻觉拦截，全套可靠性栈

简言之：把"一个 agent 干一件事"扩展成"**一支 AI 团队真正能跑完的项目板**"。

源码位置：

- `hermes_cli/kanban_db.py` —— 数据模型 + 调度核心
- `hermes_cli/kanban.py` —— `hermes kanban *` CLI
- `hermes_cli/kanban_decompose.py` / `kanban_specify.py` —— LLM 驱动的任务拆解
- `hermes_cli/kanban_swarm.py` —— 拓扑助手
- `tools/kanban_tools.py` —— MCP 工具
- `plugins/kanban/dashboard/plugin_api.py` —— Dashboard 后端
- `gateway/run.py` —— 嵌入式 dispatcher tick

---

## 数据模型

### Task（`kanban_db.py:600-729`）

| 字段 | 说明 |
|------|------|
| `id` | `t_<hex>` 形式的任务 ID |
| `status` | 9 状态：triage / todo / scheduled / ready / running / blocked / review / done / archived |
| `assignee` | 执行 Profile 名（即用哪个 hermes profile 跑） |
| `priority` | 调度优先级 |
| `workspace_kind` | scratch / worktree / dir |
| `workspace_path` | 显式路径（worktree/dir 模式） |
| `claim_lock` | UUID，持有此锁的 worker 独占运行 |
| `claim_expires` | unix ts，dispatcher 超时回收 |
| `consecutive_failures` | 失败计数，达 `max_retries` 自动 block |
| `worker_pid` | 派生 worker 的 PID（活性检测用） |
| `last_heartbeat_at` | worker 自报心跳时间 |
| `current_run_id` | 指向 `task_runs` 当前活动行 |
| `skills` | JSON 数组，强制加载这些 skill 进 worker |
| `max_retries` | per-task 熔断阈值 |
| `session_id` | 来源 chat / agent session id |

### Run（`kanban_db.py:731-782`）

每次执行一个 Task 都产生一行 `task_runs`，记录 profile、outcome（success/failed/crashed/timed_out/gave_up）、summary、metadata、error、起止时间。**结构化 handoff** 通过 `summary` + `metadata`（JSON）传给下游任务。

### Board（`kanban_db.py:396-472`）

多看板支持，每个 board 一个独立 SQLite。

- 默认 board：`~/.hermes/kanban.db`
- 其他 board：`~/.hermes/kanban/boards/<slug>/kanban.db`
- workspace 目录：`~/.hermes/kanban/workspaces/<task_id>/`
- worker 日志：`~/.hermes/kanban/logs/<task_id>.log`
- 当前 board 指针：`~/.hermes/kanban/current`（单行文本文件）

### 表结构（`kanban_db.py:808-966`）

- `tasks` —— 主板行
- `task_links` —— 父子依赖边 (`parent_id`, `child_id`)
- `task_comments` —— 审计评论
- `task_events` —— append-only 事件流（状态变更、完成、崩溃、心跳）
- `task_runs` —— 每次尝试历史

**并发策略**（`kanban_db.py:61-68`）：WAL mode + `BEGIN IMMEDIATE` 写串行化，CAS 保证最多一个 claimer。

---

## 状态机

```
triage ──[decompose/specify]──> todo
todo ─────[依赖满足]──────> ready
ready ────[dispatcher claim]──> running
running ──[complete / block]──> done | blocked
blocked ──[manual unblock]────> ready
scheduled ─[人工/cron]────> ready
review ───[reviewer 完成]──> done | running
done ─────[archive]──> archived
```

- `todo → ready`：dispatcher 的 `recompute_ready()` 检查所有 parent 都 done 后自动晋升
- `ready → running`：dispatcher 用 CAS（`status='ready' AND claim_lock IS NULL`）原子认领
- `running → blocked`：worker 或人工标 stuck，需手动 unblock
- `scheduled`：时间等待态（v1 靠人工/cron 拨到 ready，未来可能 auto-promote）

---

## Worker 生命周期

### Claim（`kanban_db.py:claim_task` @ 2156）

```python
def claim_task(conn, task_id, ttl_seconds=None):
    """原子转 ready → running，创建 task_runs 行。"""
```

- CAS：`status='ready' AND claim_lock IS NULL`
- 返回 Run 对象，含 `claim_lock`（UUID）+ `claim_expires`（now + TTL）
- TTL 默认 `DEFAULT_CLAIM_TTL_SECONDS = 15 * 60`（`kanban_db.py:109`），可 `HERMES_KANBAN_CLAIM_TTL_SECONDS` 覆盖

### Dispatch tick（`kanban_db.py:dispatch_once` @ 4702）

每 60s（`kanban.dispatch_interval_seconds`）：

1. `os.waitpid(-1, os.WNOHANG)` 回收僵尸子进程
2. **释放过期 claim**：`claim_expires < now` 的 task 回到 ready
3. **检测 stuck running**：`now - last_heartbeat_at > dispatch_stale_timeout_seconds` 时回收（0 = 禁用）
4. **检测崩溃 worker**：`os.kill(pid, 0)` 抛错 → 进程死了，回收 + 增 `consecutive_failures`，超 `max_retries` 自动 block（`detect_crashed_workers` @ 4223）
5. **晋升 ready**：`recompute_ready()` @ 2096 把所有 parent 都 done 的 todo 转 ready
6. **派发 worker**：对 ready+assignee+无 claim 的，原子 claim + 调 `_default_spawn` @ 5267

### Default spawn

```bash
hermes -p <assignee> --board <board> kanban-worker <task_id>
```

env：

- `HERMES_KANBAN_TASK=<task_id>`
- `HERMES_KANBAN_RUN_ID=<run_id>`
- `HERMES_KANBAN_BOARD=<board>`

### 心跳（`kanban_db.py:heartbeat_worker` @ 3906）

worker 主动调 `hermes kanban heartbeat <task_id> [--note ...]` 或 MCP `kanban_heartbeat`：

- 更新 `task.last_heartbeat_at`
- 追加 `heartbeat` 事件
- 隐式延长 claim TTL

### Reclaim（`kanban_db.py:reclaim_task` @ 2489）

人工或自动释放 running 任务的 claim：

- 追加 reclaim 事件 + reason
- 回到 ready（或 todo 若依赖未满足）

### 僵尸检测（`kanban_db.py:detect_crashed_workers` @ 4223）

```python
def detect_crashed_workers(conn):
    """找 status='running' AND worker_pid IS NOT NULL 但进程已死的任务。"""
```

- 查所有 `running` 任务
- `os.kill(pid, 0)`，抛 ProcessLookupError → 进程死
- 调 `_record_worker_exit` @ 3728（Windows 走 Popen GC）
- 自动 block 若 `consecutive_failures >= max_retries`

### 熔断（`kanban_db.py` `_record_task_failure`）

`consecutive_failures` 三类失败共享：

- spawn 失败
- timeout（worker 超 `max_runtime_seconds`）
- 崩溃（PID 消失）

阈值：

- per-task：`hermes kanban create --max-retries N`
- per-board：`kanban.failure_limit`（默认 3）

**只有成功完成才清零**。

### 幻觉拦截（`kanban_db.py:complete_task` @ 2721）

```python
def complete_task(conn, task_id, result=None, summary=None, metadata=None):
```

- 扫描 `summary` + `created_cards` 中的 `t_<hex>` 引用
- 查数据库验证存在
- **存在性失败 → 拒绝完成**，追加 `completion_blocked_hallucination` 事件
- 引用存疑但还能完成时追加 `suspected_hallucinated_references` 警告

Dashboard diagnostics widget 浮出这些事件 + 恢复操作。

---

## 任务编排

### 依赖（`task_links` 表 + `recompute_ready()`）

```sql
CREATE TABLE task_links (parent_id TEXT, child_id TEXT, PRIMARY KEY ...)
```

dispatcher 每 tick 查所有 `status='todo'`，验证 `task_links` 中所有 parent 都 `done`，全满足则晋升 ready。

### 重派守卫（`kanban_db.py:check_respawn_guard` @ 4576）

防止确定性 blocker（额度耗尽、auth 失败）抖动：

```python
def check_respawn_guard(conn, task_id):
    """检查上次失败错误是否为确定性 blocker，是则推迟派发。"""
```

匹配 auth / quota 关键词后返回延迟原因，dispatcher 跳过该 tick。

### 自动分解（`kanban_decompose.py`）

读 triage 列任务 → 辅助 LLM（带 profile roster） → JSON `{fanout: bool, tasks: [{title, body, assignee, parents: [indices]}]}` → 原子创建子任务 + links → root triage → todo。

不适合 fanout 时降级到 `kanban_specify`（单任务晋升）。

### Swarm 拓扑（`kanban_swarm.py:77`）

```
root (立即 done，做共享黑板)
├─ worker_1 (ready)
├─ worker_2 (ready)
└─ verifier (todo, 依赖所有 workers)
   └─ synthesizer (todo, 依赖 verifier)
```

- root 标 done 仍可挂评论（共享黑板）
- workers 互读 sibling summary
- verifier + synthesizer 读所有 worker 输出 + 评论
- 结构化 handoff 走 root 上的 JSON 评论

---

## CLI 命令一览

完整命令 `hermes kanban --help`。主要：

### 看板管理
- `hermes kanban boards list/create <slug>/switch <slug>`

### 任务生命周期
- `hermes kanban create <title> [--body ...] [--assignee <profile>] [--max-retries N] [--skills s1,s2]`
- `hermes kanban list [--mine] [--status s] [--assignee p]`
- `hermes kanban show <id>` —— 详情 + 事件 + 评论
- `hermes kanban complete/block/unblock/archive <id>`
- `hermes kanban promote <task_id> [reason ...] [--ids id1 id2 ...] [--force] [--dry-run] [--json]` —— **手动 todo→ready 恢复路径**（2026-05-23，`d46adad`/`b207dc2`），用于 auto-promote daemon 漏掉的父任务 done 转换（issue #28822）；`--ids` 批量；写 `task_events` `kind="promoted_manual"` 与 daemon 自动 `kind="promoted"` 区分，audit 消费者可过滤人为；`--force` 父依赖未 done 也强行 promote。源码：`hermes_cli/kanban.py:553-584` + `hermes_cli/kanban_db.py:+71` 新方法 `promote_task()`

### Claim + dispatch
- `hermes kanban claim <id> [--ttl 900]`
- `hermes kanban reclaim <id> [--reason ...]`
- `hermes kanban dispatch [--dry-run] [--max 10]` —— 跑一个 tick

### Worker 信号
- `hermes kanban heartbeat <id> [--note ...]`
- `hermes kanban comment <id> <text...>`

### 依赖
- `hermes kanban link <parent> <child>` / `unlink <parent> <child>`

### Triage 晋升
- `hermes kanban specify <id>`
- `hermes kanban decompose <id> [--all]`

### 观察
- `hermes kanban diagnostics [--severity warning|error|critical]`
- `hermes kanban stats`
- `hermes kanban watch [--assignee ...]`
- `hermes kanban runs <id>`
- `hermes kanban log <id> [--tail N]`

---

## MCP 工具（`tools/kanban_tools.py`）

注册条件：worker 内（`HERMES_KANBAN_TASK` env 设置）或 profile 启用 `kanban` toolset（orchestrator）。

### Worker 工具（仅能改自己的 task_id）
- `kanban_complete(task_id, result, summary, metadata)`
- `kanban_block(task_id, reason)`
- `kanban_heartbeat(task_id, note)`
- `kanban_comment(task_id, text, author)`

### Orchestrator 工具
- `kanban_create(title, body, assignee, ...)`
- `kanban_list(assignee, status, ...)` —— max 50-200
- `kanban_unblock(task_ids)`
- `kanban_show(task_id)`

---

## Dashboard 集成

后端（`plugins/kanban/dashboard/plugin_api.py`）：

| 端点 | 用途 |
|------|------|
| `GET /api/plugins/kanban/board` | 按状态分组的整板 |
| `GET /api/plugins/kanban/tasks/<id>` | 抽屉视图 |
| `POST /api/plugins/kanban/tasks` | 创建 |
| `PATCH /api/plugins/kanban/tasks/<id>` | 改状态/受让人/优先级 |
| `POST /api/plugins/kanban/tasks/<id>/reclaim` | 释放 claim |
| `POST /api/plugins/kanban/tasks/<id>/reassign` | 换 assignee |
| `POST /api/plugins/kanban/tasks/<id>/specify` | aux LLM 晋升 |
| `GET /api/plugins/kanban/diagnostics` | 异常信号 |
| `GET /api/plugins/kanban/workers/active` | 当前 running worker |
| `GET /api/plugins/kanban/runs/<id>/inspect` | psutil 进程统计 |

前端：看板拖拽 + 抽屉 + 恢复浮窗 + WebSocket 事件流。

---

## 多看板支持

每个 board 独立：DB + workspace + log，完全隔离。`hermes kanban boards switch <slug>` 写 `~/.hermes/kanban/current`。dispatcher 每 tick 枚举所有 board 独立跑 `dispatch_once`（`gateway/run.py:5204-5219`）。新建 board 下一个 tick 自动接管。

---

## 配置

### config.yaml

```yaml
kanban:
  dispatch_in_gateway: true       # gateway 跑 dispatcher（默认 true）
  dispatch_interval_seconds: 60   # tick 间隔
  max_spawn: null                 # 并发派生上限（null = 无限）
  max_in_progress: null           # 同时 running 上限
  failure_limit: 3                # 熔断阈值
  dispatch_stale_timeout_seconds: 0  # 0 = 禁用 stale 检测

auxiliary:
  triage_specifier: {...}         # specify 的 aux LLM
  kanban_decomposer: {...}        # decompose 的 aux LLM

dashboard:
  kanban:
    default_tenant: ""
    lane_by_profile: true
    include_archived_by_default: false
    render_markdown: true
```

### 环境变量

| 变量 | 用途 |
|------|------|
| `HERMES_KANBAN_DISPATCH_IN_GATEWAY` | falsy → 禁用 gateway dispatcher |
| `HERMES_KANBAN_BOARD` | 固定 current board |
| `HERMES_KANBAN_DB` | 显式 DB 路径（最高优先级） |
| `HERMES_KANBAN_WORKSPACES_ROOT` | 显式 workspace 根 |
| `HERMES_KANBAN_CLAIM_TTL_SECONDS` | 覆盖默认 900s |
| `HERMES_KANBAN_TASK` | worker 进程的 task ID |
| `HERMES_KANBAN_RUN_ID` | worker 进程的 run ID |

---

## 与 [[multi-agent-architecture]] 的关系

Kanban 是 Hermes 多 Agent 体系的**第 5 种机制**，区别于 in-process 的 delegate_task / MoA / Background Review / send_message：

| 维度 | in-process | Kanban |
|------|-----------|--------|
| 存活范围 | 单 session | 跨 session / restart |
| 协调粒度 | 单父 → 子任务 | 任意 DAG |
| 持久化 | 无（IPC + memory） | SQLite WAL |
| 失败恢复 | 父 retry | 心跳 + reclaim + 熔断 |
| Profile 隔离 | 单 profile | 跨 profile，每任务独立 |
| 用户接口 | 工具调用 | CLI + Dashboard + MCP |

适用场景：长跑迭代工作（重构、研究）、人机协作（人定优先级，AI 跑实现）、多 Profile 工作流分发。

---

## DB 抗污染（2026-05-23, PR #30858 + #30862）

v0.14.0 之后用户社区出现"kanban.db 神秘损坏 → 自动重建覆盖旧任务"事故，根因是 [[interrupt-and-fault-tolerance|TLS FD recycling]] 把一个 24-byte TLS application-data record 写到了 SQLite header 上。本次 wave 加 **DB 端的失败闭合**：

### `_guard_existing_db_is_healthy` + `KanbanDbCorruptError`（`kanban_db.py:1010-1132`）

```
connect(path)                              # kanban_db.py:1135
  └─ _guard_existing_db_is_healthy(path)   # :1077-1132
       ├─ resolve() + size>0 检查
       ├─ sqlite3.connect(...) PRAGMA integrity_check
       ├─ ok        → _INITIALIZED_PATHS 缓存
       ├─ corrupt   → _backup_corrupt_db(path) + raise KanbanDbCorruptError
       └─ Locked    → 让 sqlite3.OperationalError 透传（不当作 corrupt）
```

- **失败闭合**：integrity_check 非 `"ok"` → 直接 raise `KanbanDbCorruptError`（`:1010-1026`），调用者不能默写重建 schema。
- **保留证据**：损坏 DB 拷到 `<db>.corrupt.<YYYYMMDD_HHMMSS>.bak`，WAL/SHM sidecar 一并备份（`:1029-1074`）。
- **缓存友好**：探针成功后路径入 `_INITIALIZED_PATHS`，同进程后续 `connect()` 跳过重检（`:1113`）。
- **锁争用不误判**：`sqlite3.OperationalError` 直接 `raise`，避免对 WAL checkpoint 中的 DB 误备份（`:1124-1126`）。

### 备份路径 CodeQL 硬化（`c4b8f5e`）

`_backup_corrupt_db` 所有写发生在 `path.resolve().parent` 之内，每次构造 `candidate = parent / basename_only` 后断言 `candidate.parent != parent → return None`（`kanban_db.py:1051-1052, 1057-1058, 1069-1070`）。WAL/SHM sidecar 同样走 resolved-parent 路径，`..` 段在任何 I/O 之前被 collapsed。功能等价，仅给静态分析器看 containment 证明。163/163 测试通过。

## Scratch workspace 一次性可见性（2026-05-23, PR #30949）

`hermes_cli/kanban_db.py:3109-3181`：用户社区报告"progress files vanished, no warning anywhere"，本 commit 把"scratch = ephemeral by design"补成"by design **且可见**"。

首次在该 install 创建 scratch workspace 时：

1. 一次性 warning log："scratch workspaces are ephemeral — they're deleted when the task completes."（`:3117-3121`）
2. 在 task 上 append `tip_scratch_workspace` 事件（`:3174`）—— Dashboard 等 `task_events` 消费者可见
3. Touch sentinel `~/.hermes/kanban/.scratch_tip_shown`（`:3141-3181`），整 install 静默后续创建

行为不变，scratch 还是 ephemeral；只是把契约显性化。docs（en + ko）也加 "Deleted when the task completes" / "Preserved on completion"。

---

## 文件 / 函数索引

| 功能 | 位置 |
|------|------|
| 数据模型 (Task / Run / Board) | `kanban_db.py` Task / Run / Board dataclass |
| Schema (5 tables) | `kanban_db.py` 内的 `CREATE TABLE` |
| `DEFAULT_CLAIM_TTL_SECONDS` | `kanban_db.py:109`（900s） |
| `claim_task` | `kanban_db.py:2156` |
| `reclaim_task` | `kanban_db.py:2489` |
| `complete_task` + 幻觉拦截 | `kanban_db.py:2721` |
| `heartbeat_worker` | `kanban_db.py:3906` |
| `_record_worker_exit` | `kanban_db.py:3728` |
| `detect_crashed_workers` | `kanban_db.py:4223` |
| `check_respawn_guard` | `kanban_db.py:4576` |
| `dispatch_once` | `kanban_db.py:4702` |
| `recompute_ready` | `kanban_db.py:2096` |
| `_default_spawn` | `kanban_db.py:5267` |
| Decompose | `hermes_cli/kanban_decompose.py` |
| Specify | `hermes_cli/kanban_specify.py` |
| Swarm 拓扑 | `hermes_cli/kanban_swarm.py:77` |
| Diagnostics 规则 | `hermes_cli/kanban_diagnostics.py` |
| CLI 子命令 | `hermes_cli/kanban.py:191+` |
| MCP 工具 | `tools/kanban_tools.py:49-90` |
| Dashboard API | `plugins/kanban/dashboard/plugin_api.py` |
| Gateway dispatcher | `gateway/run.py:4996-5219` |
| `KanbanDbCorruptError` + `_guard_existing_db_is_healthy` | `kanban_db.py:1010-1132`（2026-05-23+） |
| `_backup_corrupt_db`（CodeQL 硬化） | `kanban_db.py:1029-1074` |
| Scratch tip + sentinel | `kanban_db.py:3109-3181`（2026-05-23+） |

---

*Last verified: 2026-05-22, HEAD `09afafb87`*

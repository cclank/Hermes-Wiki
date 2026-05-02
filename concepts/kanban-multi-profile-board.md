---
title: Kanban — durable multi-profile collaboration board
created: 2026-05-02
updated: 2026-05-02
type: concept
tags: [kanban, multi-agent, sqlite, collaboration, dispatcher, dashboard, plugin]
sources: [hermes_cli/kanban_db.py, hermes_cli/kanban.py, tools/kanban_tools.py, plugins/kanban/dashboard/plugin_api.py]
---

# Kanban — Durable Multi-profile Collaboration Board

## 一句话

跨 Hermes profile 共享的 SQLite 任务板：在一处声明任务，多个 profile（每个 profile 跑自己的 agent / 模型 / toolset）原子领取、跑、回写。**Profile-agnostic on purpose**——同机所有 profile 看到同一面板，这就是协作原语。

> 实现源码：
> - `hermes_cli/kanban_db.py`（2,765 行）— 数据层
> - `hermes_cli/kanban.py`（1,393 行）— CLI 表面
> - `tools/kanban_tools.py`（726 行）— Worker 工具
> - `plugins/kanban/dashboard/plugin_api.py` — Dashboard 插件
> v0.12.0 在 v2026.4.30 重新引入（v0.11.0 曾 land 后 revert，#16098）

## 架构基石

`kanban_db.py:1-18` 自述：

- 路径：`$HERMES_HOME/kanban.db`（profile-agnostic）
- 表：`tasks`、`task_links`、`task_comments`、`task_events`、`task_runs`、`task_subscriptions`
- `workspace_kind` 字段：把协作和 git worktree 解耦——research / ops / digital-twin workload 与 coding workload 共存
- **并发策略**：WAL 模式 + `BEGIN IMMEDIATE` 写事务 + CAS 更新 `tasks.status` 与 `tasks.claim_lock`
- **零分布式锁**：SQLite 自身串行化 writers，losers 看到 0 affected rows 直接走人——no retry loops, no distributed-lock machinery

## 状态机

`VALID_STATUSES`（`kanban_db.py:38`）：

```
triage → todo → ready → running ──────→ done
                  ↓        ↑              ↓
                  ↓     blocked          archived
                  └──────────────────────→ archived
```

| 状态 | 触发 |
|------|-----|
| `triage` | `--triage` 创建，等 specifier 补 spec |
| `todo` | 默认创建状态 |
| `ready` | dispatcher promote，依赖满足 |
| `running` | 某 profile 原子 `claim` 成功 |
| `blocked` | 阻塞，需要 `unblock` |
| `done` | 正常完成 |
| `archived` | gc 后保留 |

## Workspace 分类

`VALID_WORKSPACE_KINDS`（`kanban_db.py:39`）：

| Kind | 说明 |
|------|-----|
| `scratch` | 默认。`kanban/workspaces/<task_id>` 临时目录 |
| `worktree` | git worktree，与 [[worktree-isolation]] 集成 |
| `dir` | 直接指向已有目录 |

## Claim 协议

`DEFAULT_CLAIM_TTL_SECONDS = 15 * 60`（`kanban_db.py:45`）。

- worker 跑 `kanban claim <id>`——CAS 设 `claim_lock` + `claim_expires`
- 超期后下一次 dispatcher tick 自动回收
- 长跑 worker 调 `heartbeat_claim(task_id)` 续期；典型 workload 要么 15 分钟内完，要么显式开长 claim
- `--max-runtime`（kanban.py:193-197）支持 `300` / `90s` / `30m` / `2h` / `1d`，超期 dispatcher SIGTERM → SIGKILL 后重排队

## CLI 表面（15+ verbs）

`hermes_cli/kanban.py:156-419` build_parser，挂在 `hermes kanban …`：

| Verb | 用途 |
|------|------|
| `init` | idempotent 创库 |
| `create` | 新 task（`--body / --assignee / --parent / --workspace / --priority / --triage / --idempotency-key / --max-runtime / --skill ...`）|
| `list` (`ls`) | 列表（`--mine / --assignee / --status / --tenant / --archived`）|
| `show` | 单 task + comments + events |
| `assign` | 重分配 profile（`none` 取消）|
| `link` / `unlink` | 父子依赖 |
| `claim` | 原子领取 |
| `comment` | 追加 comment |
| `complete` | 完成（多 ID + `--result / --summary / --metadata`）|
| `block` / `unblock` | 阻塞/解除（多 ID 批量）|
| `archive` | 归档 |
| `tail` | follow event stream |
| `dispatch` | 单次 dispatcher pass（`--dry-run / --max / --failure-limit`）|
| `daemon` | **deprecated**——dispatcher 改为 gateway 嵌入；保留 `--force` 隐藏 escape hatch |
| `watch` | 实时 event stream（按 assignee/tenant/kind 过滤）|
| `stats` | per-status / per-assignee 计数 + oldest-ready age |
| `notify-{subscribe,list,unsubscribe}` | gateway 终端事件订阅 |
| `log` | 打印 worker log |
| `runs` | per-attempt 历史 |
| `heartbeat` | worker liveness signal |
| `assignees` | 已知 profile + per-profile 计数 |
| `context` | 打印 worker 看到的完整 context（title + body + parent results + comments）|
| `gc` | 清归档 workspace、老 events、老 logs |

`/kanban …` 同样表面（CLI 与 gateway 各装一个 wrapper subparser，formatting 一致——`kanban.py:1352-1383`）。

## Worker Tools — 仅在 dispatcher 环境注册

`tools/kanban_tools.py:42-49`：

```python
def _check_kanban_mode() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK"))
```

—— `HERMES_KANBAN_TASK` 由 dispatcher spawn worker 时设置。普通 `hermes chat` 看到 **零** kanban 工具。

7 个工具（`tools/kanban_tools.py:665-727`）：

| Tool | Emoji |
|------|-------|
| `kanban_show` | 📋 |
| `kanban_complete` | ✔ |
| `kanban_block` | ⏸ |
| `kanban_heartbeat` | 💓 |
| `kanban_comment` | 💬 |
| `kanban_create` | ➕ |
| `kanban_link` | 🔗 |

### 为什么 tool 而不是 shell out 调 `hermes kanban`

`tools/kanban_tools.py:8-25` 列了三条：

1. **Backend portability**：worker 在 Docker / Modal / Singularity / SSH，容器里没装 `hermes`、没挂 DB；tool 直接走 Python 进程读 `~/.hermes/kanban.db`
2. **No shell-quoting footguns**：`--metadata '{"x":[...]}'` 透 shlex+argparse 易碎
3. **Better errors**：tool-call 失败返回结构化 JSON，模型可解析

## Worker Context Caps

防止病态 board（retry 风暴 / comment 风暴 / 巨型 summary）撑爆 LLM prompt（`kanban_db.py:53-57`）：

```python
_CTX_MAX_PRIOR_ATTEMPTS = 10        # 最近 10 个 prior runs 全文
_CTX_MAX_COMMENTS       = 30        # 最近 30 个 comments 全文
_CTX_MAX_FIELD_BYTES    = 4 * 1024  # 4KB per summary/error/metadata/result
_CTX_MAX_BODY_BYTES     = 8 * 1024  # 8KB per task.body
_CTX_MAX_COMMENT_BYTES  = 2 * 1024  # 2KB per comment
```

每个 cap 独立调——只想放宽一个时不必全放。

## 强制 Skill 注入

`Task.skills` 字段（`kanban_db.py:108-113`）—— JSON 数组，存到表里：

- `None`：仅用 dispatcher 内置 `kanban-worker` skill
- `[]`：显式空——只 worker skill
- `["translation", "github-code-review"]`：附加注入

CLI 创建：`--skill translation --skill github-code-review`（kanban.py:200-204）。

## Dashboard 插件

`plugins/kanban/dashboard/plugin_api.py:1-46` 自述：

- 挂在 `/api/plugins/kanban/`
- 写路径与 CLI/gateway `/kanban` **共享 `kanban_db`**——三处不会漂移
- 实时更新走 `/events` WebSocket，poll `task_events` 表（WAL 让读跑在 dispatcher 的 IMMEDIATE 写事务旁）
- **HTTP 路由**：dashboard 插件路由全局豁免 auth middleware（`/api/plugins/` 开放），因为 dashboard 默认 bind localhost
- **WebSocket auth**：`?token=<session_token>` 查询参数（浏览器无法在 upgrade 请求设 Authorization 头），匹配 `web_server.py` 的 in-browser PTY bridge 模式

> 警告（plugin_api.py:21-25）：用 `--host 0.0.0.0` 跑 dashboard 时，**所有插件路由（含 kanban）对网络开放**——别在共享主机上这么干。

## Dispatcher 嵌入 gateway

旧：`hermes kanban daemon` 60s tick。
新：dispatcher 嵌入 gateway 的 cron-ticker（与 [[cron-scheduling]] 共用线程）。

`kanban.py:299-315`：`daemon` subcommand 仍存在但标 **DEPRECATED**。`--force` flag 通过 `argparse.SUPPRESS` 隐藏，刻意不让用户随手发现，避免**双 dispatcher 模式**复活。

## Idempotency

`create --idempotency-key <key>`：

- 若有非 archived task 用这个 key，**返回它的 id 而非新建**
- 用于 cron / hook 重入安全

## 失败处理

- `spawn_failures` 字段（`kanban_db.py:101`）：连续 spawn 失败计数
- `--failure-limit`（kanban.py:290-293，默认 `DEFAULT_SPAWN_FAILURE_LIMIT`）：达阈值 auto-block task
- `last_spawn_error`（`kanban_db.py:103`）：最近一次错误文本
- gateway 状态故障 atomic 写入（`f43b126`）：sibling recovery / dedup state files

## 与其它机制对比

| | Kanban | delegate_task | batch_runner | cron |
|---|---|---|---|---|
| 触发 | 用户 / 任意 hook / cron | LLM tool call | CLI 显式 | 时间表达式 |
| 跨 profile | ✓（共享 db）| ✗（同 profile）| ✗ | ✗（cron 自己有 platform）|
| 持久化 | SQLite | 无 | trajectory 文件 | crontab |
| 并发 | 多 profile 抢 | 最多 3 路 | 用户配置 | 单线程 |
| Workspace 隔离 | scratch/worktree/dir | 父 cwd | trajectory cwd | 父 cwd |

## `gc` 子命令

`kanban.py:410-417` 默认值：

- `--event-retention-days 30`：删除 30 天前的 task_events（仅 terminal 状态 task）
- `--log-retention-days 30`：删除 30 天前的 worker log

## 来源

- DB 层：`hermes_cli/kanban_db.py:1-2765`
- CLI 层：`hermes_cli/kanban.py:1-1393`
- Worker tools：`tools/kanban_tools.py:1-727`
- Dashboard 插件：`plugins/kanban/dashboard/plugin_api.py`
- Release notes：`RELEASE_v0.12.0.md` ([#17805](https://github.com/NousResearch/hermes-agent/pull/17805))

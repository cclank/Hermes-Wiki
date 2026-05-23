---
title: Cron 调度与自动化工作流
created: 2026-04-07
updated: 2026-05-20
type: concept
tags: [architecture, cron, automation, scheduling, webhook]
sources: [cron/scheduler.py, cron/jobs.py, tools/cronjob_tools.py, gateway/platforms/webhook.py]
---

> **v2026.5.7 增量**：
>
> - **`no_agent` 模式**（#19709）—— cron job 跳过 agent，仅运行脚本。空 stdout 静默；非空原样投递。源码 `cron/jobs.py:438` `no_agent: bool = False` 参数 + line 457「the script IS the job — its stdout is delivered verbatim」。适用看门狗 / uptime / 状态检查类。
> - **`context_from` chaining 文档化**（#20394）。
> - **Fix #21354**：在构造 cron AIAgent 前初始化 MCP servers（之前 cron job 会拿到空 MCP 工具集）。
> - **Fix #21371**：在 fallback restart 前 reset-failed，让 gateway 不会被卡住。
> - **Fix**：扫描 cron job 注入时**包含 skill content**（#21350，P0 安全闭环）。
> - **Fix**：cron job 加载 skill 时 bump skill usage（#19433） —— curator 才能看到 cron 持有的 skill 是「活的」。

# Cron 调度与自动化工作流

## 设计原理

Hermes 内置 Cron 调度器，支持**自然语言定时任务**，可以自动执行重复性工作并将结果推送到任意平台。截至 v0.13.0 支持三种执行模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **agent**（默认） | 完整 Agent 推理，可调用所有工具 | 摘要 / 分析 / 多步研究 |
| **no_agent**（v0.13.0） | 只跑 shell script，stdout 直接投递；空 stdout 完全静默 | 监控 / 健康检查 / 看门狗 |
| **prerun-only**（v0.12） | 先跑 prerun script；脚本无输出时跳过 AI 调用 | "有变更才告诉我"类任务 |

`no_agent` 模式（PR #19709）是 watchdog 模式的一等公民：每分钟跑一条 shell，非空输出原样投递到 Discord/Telegram，省掉 LLM 调用，零成本。

其他 v0.12 / v0.13 增强：
- **`context_from` 字段（v0.12 PR #15606）**：把上一个 cron job 的输出作为下一个 job 的 context，链式工作流
- **per-job `workdir`（v0.12）**：项目感知的 cron job
- **per-job `enabled_toolsets`（v0.11 PR #14767）**：限定 toolsets 防止 token 预算爆炸
- **`croniter` 升级到 core 依赖（v0.12 PR #17577）**：之前是 optional，破坏 fresh install
- **MCP server 初始化先于 AIAgent 构造（v0.13 PR #21354）**：cron 模式下 MCP 工具不再缺席
- **prompt injection 扫描 assembled prompt + skill 内容（v0.13 P0 #21350）**：堵住 cron 任务被 prompt injection 操控的漏洞

## 三种执行模式（HEAD）

| 模式 | 是否走 Agent | 用途 |
|------|-------------|------|
| **Agent 模式**（默认） | 是 | LLM 收到 prompt → 工具调用 → 输出投递 |
| **`no_agent` 脚本模式**（v0.13.0） | **否** | 只跑用户脚本；空 stdout 安静，非空逐字投递 |
| **Webhook 直送**（v0.11.0） | **否** | gateway/platforms/webhook.py 的 `deliver_only=true` route，外部 HTTP 事件**绕过 agent** 直投平台/频道 |

源码事实：

- `no_agent`：`cron/jobs.py` 解析 `no_agent: true` 字段后调 subprocess 跑命令。
- webhook 直送：`gateway/platforms/webhook.py:485-518` `[webhook] direct-deliver` 路径。
- 注入扫描：`cron/scheduler.py:50 class CronPromptInjectionBlocked` —— 拼装好的 prompt 触发注入扫描时抛出，operator 看到"job blocked"清洁错误而不是 scheduler 崩。这是 v0.13.0 安全潮的一部分（扫描已组装 skill 内容）。

## Cron 工具

```python
# tools/cronjob_tools.py

def cronjob(
    action: str,           # create/list/update/pause/resume/remove
    prompt: str = None,    # 任务提示
    schedule: str = None,  # 调度表达式
    name: str = None,      # 任务名称
    deliver: str = None,   # 投递目标
    job_id: str = None,    # 任务 ID
    profile: str = None,   # 可选：运行该任务的 Hermes profile
) -> dict:
    """管理定时任务"""
    
    if action == "create":
        return _create_job(prompt, schedule, name, deliver)
    elif action == "list":
        return _list_jobs()
    elif action == "update":
        return _update_job(job_id, prompt, schedule, name, deliver)
    elif action == "pause":
        return _pause_job(job_id)
    elif action == "resume":
        return _resume_job(job_id)
    elif action == "remove":
        return _remove_job(job_id)
```

### 按名称查找任务（2026-05-15）

`run`/`pause`/`resume`/`remove` 操作及 `hermes cron edit` 不再强制要求 hex ID——也接受**任务名称**（大小写不敏感）。当多个任务重名时，操作会拒绝执行并列出所有匹配任务（id、name、schedule、next_run_at），由调用方挑选具体 ID。`cron/jobs.py` 的 `get_job()` 保持 ID-only 语义（供 web_server/api_server/curator/scheduler 等调用点使用），名称解析在 CLI 层完成。

## 调度器

调度器使用**模块级函数**架构（非类），由 Gateway 每 60 秒调用 `tick()` 驱动：

```python
# cron/scheduler.py — 模块级函数架构

def tick():
    """由 Gateway 每 60 秒调用一次，检查并执行到期任务"""
    now = datetime.now()
    jobs = _load_jobs()  # 从 jobs.json 加载
    for job in jobs.values():
        if _should_run(job, now):
            run_job(job)

def run_job(job: dict):
    """执行单个任务"""
    # 创建新的 Agent 实例
    agent = AIAgent(
        model=job.get("model"),
        platform="cron",
        enabled_toolsets=job.get("toolsets", ["terminal", "web", "file"]),
    )
    
    # 执行任务
    result = agent.run_conversation(job["prompt"])
    
    # 投递结果
    if job.get("deliver"):
        _deliver_result(job["deliver"], result)

async def _deliver_result(target: str, result: dict):
    """投递结果到目标平台"""
    ...
```

## 任务数据结构

任务以**纯 dict** 形式存储在 `jobs.json` 中（非类）：

```python
# cron/jobs.py — 任务是纯 dict，存储在 jobs.json

# 任务 dict 结构示例
job = {
    "id": "daily-report",
    "prompt": "生成今日工作总结报告",
    "schedule": "0 18 * * *",       # cron 表达式
    "name": "daily-report",
    "deliver": "telegram",
    "model": "gpt-4",
    "toolsets": ["terminal", "web", "file"],
    "profile": None,                # 可选：运行该任务的 Hermes profile（未设则用调度器自身 profile）
    "is_paused": False,
    "created_at": "2026-04-07T10:00:00",
    "last_run": None,
    "next_run": "2026-04-07T18:00:00",
}

# 调度表达式支持格式：
# - cron: "0 9 * * *" (每天 9 点)
# - 相对: "30m", "every 2h", "daily"
# - ISO: "2026-04-08T09:00:00"
```

## `no_agent` 模式（v0.12.0+，3db6b9c）

为典型的 watchdog / 数据采集场景增加 LLM-free 通道：script **就是** job，stdout 直接投递，不经过 agent。

```python
# cron/jobs.py:1041-1106
if job.get("no_agent"):
    # 必须配 script，否则错误：
    #   "no_agent=True but no script is set for this job"
    # script 路径相对于 ~/.hermes/scripts/；.sh/.bash 走 bash，其他走 python
    # script 的 cwd 就是 subprocess cwd（不接入 workdir 系统）
    # stdout 非空 → 作为 "**Mode:** no_agent (script)\n..." 投递
    # stdout 空 → silent run（不打扰用户）
    # wakeAgent=false gate → 即使有输出也静默
```

**两种 script 模式的区别**：

| 模式 | `no_agent` 取值 | script 用途 | LLM 介入 |
|------|----------------|------------|---------|
| **传统数据采集** | `False`（缺省） | script stdout 作为 context 注入 agent prompt | ✅ Agent 处理 → 投递 |
| **`no_agent` watchdog** | `True` | script stdout **就是**投递内容 | ❌ 完全不用 LLM |

适用场景：磁盘空间预警、备份校验、上行链路探测——这些不需要 LLM 推理，每次跑都消耗 token 反而浪费。

**CLI 暴露**（`hermes_cli/cron.py:96, 177, 233`）：`hermes cron create --no-agent` 创建，`hermes cron list` 显示 `Mode: no-agent (script stdout delivered directly)`。

**并发测试**：`tests/cron/test_cron_no_agent.py`（专用回归）+ `1c7f47a` 加入并行 job 状态写入回归。

## 投递目标

```python
# 已知投递平台
_KNOWN_DELIVERY_PLATFORMS = {
    "telegram", "discord", "slack", "whatsapp", "signal",
    "matrix", "mattermost", "homeassistant",
    "dingtalk", "feishu", "wecom",
    "sms", "email", "webhook",
}

async def _deliver_result(target: str, result: dict):
    """投递结果到目标"""
    if target == "origin":
        # 返回到原始聊天（通过 Gateway）
        await self.gateway.send_message(result["final_response"])
    elif target == "local":
        # 保存到本地文件
        output_dir = get_hermes_home() / "cron" / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{self.job_id}.txt"
        output_file.write_text(result["final_response"])
    elif target in DELIVER_TARGETS:
        # 通过平台发送
        await self.platform_send(target, result["final_response"])
```

## 使用示例

```python
# 创建每日报告任务
cronjob(
    action="create",
    name="daily-report",
    prompt="生成今日工作总结报告，包括完成的任务、待办事项和明日计划",
    schedule="0 18 * * *",  # 每天 18:00
    deliver="telegram",
)

# 创建每小时检查任务
cronjob(
    action="create",
    name="hourly-check",
    prompt="检查服务器状态，如有异常发送告警",
    schedule="every 1h",
    deliver="origin",
)

# 创建一次性任务
cronjob(
    action="create",
    name="backup-database",
    prompt="备份数据库并上传到云存储",
    schedule="2026-04-08T02:00:00",  # ISO 时间
    deliver="local",
)
```

## 任务 Profile 支持

Cron 任务支持可选的 `profile` 字段，让单个任务在与调度器自身不同的 Hermes profile 下运行（隔离 config、`.env`、记忆、技能、session store）。

- **任务字段**：`cron/jobs.py:131-132` 解析 `profile` 字段，并通过 `_normalize_profile()`（`cron/jobs.py:485-505`）归一化与校验——名称按 `hermes -p` 同样规则规范化，命名 profile 必须在创建/更新时已存在；`default` 始终有效；空字符串清除该字段。
- **工具参数**：`cronjob()` 工具新增 `profile` 参数（`tools/cronjob_tools.py`），可在创建/更新任务时指定。
- **运行时切换**：调度器通过 `_job_profile_context()`（`cron/scheduler.py:150-199`）为每个任务施加一个 context-local 的 Hermes-home override，使 `_get_hermes_home()`、`.env`/config 加载、脚本解析、`AIAgent` 构造等都指向该 profile 目录。
- **顺序执行**：带 `profile` 的任务**串行执行**（非并行），以保持 profile 作用域的运行时状态相互隔离。
- **环境恢复**：profile `.env` 加载对进程环境造成的临时改动会在任务退出后还原。
- **优雅降级**：若任务配置的 profile 已被删除，调度器记录告警并回退到调度器默认 profile，不会中断其他任务。

```python
# 在指定 profile 下运行的任务
cronjob(
    action="create",
    name="work-report",
    prompt="生成今日工作总结报告",
    schedule="0 18 * * *",
    deliver="telegram",
    profile="work",
)
```

## 网关集成

```bash
# 启动 Gateway（包含调度器）
hermes gateway start

# Gateway 每 60 秒调用 scheduler.tick()
# 调度器无独立事件循环，由 Gateway 驱动
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Claude Code | Cursor |
|------|--------|-------------|--------|
| 内置调度器 | ✅ | ❌ | ❌ |
| 自然语言调度 | ✅ | ❌ | ❌ |
| 多平台投递 | ✅ 19 平台 | ❌ | ❌ |
| 脚本-only watchdog | ✅ `no_agent` | ❌ | ❌ |
| Cron 表达式 | ✅ | ❌ | ❌ |
| 相对时间 | ✅ "30m", "every 2h" | ❌ | ❌ |
| 任务管理 | ✅ CLI/Gateway | ❌ | ❌ |

## 配置

```yaml
# ~/.hermes/config.yaml
cron:
  enabled: true
  timezone: "Asia/Shanghai"
  output_dir: "~/.hermes/cron/output"
```

## `no_agent` 模式 —— script-only watchdog（v0.13.0+）

`hermes_cli/cron.py:96,181` + `tools/cronjob_tools.py:322-372`：cron 任务可以**完全跳过 agent**，只跑脚本。

```yaml
cron:
  jobs:
    - name: heartbeat-check
      schedule: "*/5 * * * *"
      command: "curl -fsS https://api.example.com/health || echo 'DOWN'"
      mode: no_agent           # 不调 LLM，纯脚本执行
      deliver_to: telegram     # 仅非空 stdout 才投递
```

- **空 stdout 静默** —— 健康时不打扰
- **非空 stdout 原样投递** —— 异常立即推送
- **零 LLM 成本** —— 适合监控/轮询/状态检查

`tools/cronjob_tools.py:44,133-139` **同时**对 prompt-injection 进行**预扫描**（v0.13.0 安全 wave 之一）：cron 组装好的 prompt（含已加载 skill 内容）走 injection 正则，命中返回 `"Blocked: prompt contains injection"` 阻止执行。

### Watchers Skill（v0.14.0+）

`optional-skills/watchers/` 利用 `no_agent` cron 模式轮询 RSS / HTTP JSON / GitHub，实现变更检测：检测到新条目时再投递给 agent 处理。

## 相关页面

- [[messaging-gateway-architecture]] — 网关驱动调度器 tick() 循环；deliver=all
- [[hook-system-architecture]] — `standalone_sender_fn` 跨进程投递（PR `93e25ceb1`）
- [[gateway-session-management]] — 会话 origin 用于 Cron 投递路由
- [[kanban-multi-agent]] — Cron + Kanban 组合：定时投递 task 到 board
- [[security-defense-system]] — Cron prompt-injection 扫描

## 相关文件

- `tools/cronjob_tools.py` — Cron 工具（含 `profile` 参数）
- `cron/scheduler.py` — 调度器（`_job_profile_context()` 见 line 150-199）
- `cron/jobs.py` — 任务定义（`profile` 字段见 line 131-132，`_normalize_profile()` 见 line 485-505）
- `gateway/run.py` — 网关集成

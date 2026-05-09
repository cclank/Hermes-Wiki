---
title: Cron 调度与自动化工作流
created: 2026-04-07
updated: 2026-05-09
type: concept
tags: [architecture, cron, automation, scheduling, no-agent, watchers]
sources: [tools/cronjob_tools.py, cron/scheduler.py, cron/jobs.py, optional-skills/devops/watchers/]
---

# Cron 调度与自动化工作流

## 设计原理

Hermes 内置 Cron 调度器，支持**自然语言定时任务**，可以自动执行重复性工作并将结果推送到任意平台。

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
| 多平台投递 | ✅ 14 平台 | ❌ | ❌ |
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

## `no_agent` 看门狗模式（v0.13.0+，PR #19709）

`cron/jobs.py:498` 新增字段 `no_agent: bool = False`，让 cron job **完全跳过 agent**，纯执行 `script`：

```python
def schedule_cron(
    ...,
    script: str | None = None,
    no_agent: bool = False,         # script 模式（看门狗）
    ...
):
    """
    no_agent=True 时:
      - script 是必需的（cron/jobs.py:581 强制）
      - script 的 stdout 决定行为：空 = 静默，非空 = 原样投递
      - prompt 仅作 name hint
      - workdir 仍作 script 的 cwd
    """
```

**适用场景**：

```yaml
# 一个监视 RSS 的 watchdog
schedule: "*/15 * * * *"
no_agent: true
script: "python ~/.hermes/skills/watchers/scripts/rss_watch.py https://feed.url"
deliver: telegram:home
```

**watchers skill** 是 no_agent 模式的官方实现（`optional-skills/devops/watchers/`）：

- RSS / Atom 订阅、HTTP JSON endpoint polling、GitHub repo issues / pulls / releases / commits
- watermark dedup（只投递新 item）
- 共享 watermark helper

详见 [`optional-skills/devops/watchers/SKILL.md`](https://github.com/NousResearch/hermes-agent/tree/main/optional-skills/devops/watchers/SKILL.md)。

## `deliver=all` 路由意图（v0.13.0+，PR #21495）

cron job 的 `deliver` 字段支持特殊值 `all`，表示**扇出到所有连接的 channel**（不指定具体平台）。

## 安全：扫描 skill 内容做注入检测（v0.13.0+，PR #21350）

P0 修复——cron prompt-injection 扫描器之前只看 `prompt` 字段，**v0.13.0** 起扫描组装后的完整 prompt（含 skill 内容），防止恶意 skill 注入指令通过 cron 触发。

详见 [[security-defense-system]]。

## 相关页面

- [[messaging-gateway-architecture]] — 网关驱动调度器 tick() 循环；deliver=all
- [[hook-system-architecture]] — `standalone_sender_fn` 跨进程投递（PR `93e25ceb1`）
- [[gateway-session-management]] — 会话 origin 用于 Cron 投递路由
- [[skills-system-architecture]] — watchers skill 是 no_agent 配套
- [[security-defense-system]] — cron 注入扫描

## 相关文件

- `tools/cronjob_tools.py` — Cron 工具
- `cron/scheduler.py` — 调度器
- `cron/jobs.py:498` — `no_agent` 字段
- `cron/jobs.py:581` — `no_agent + script` 强制共存
- `optional-skills/devops/watchers/` — RSS / HTTP / GitHub watcher 脚本
- `gateway/run.py` — 网关集成

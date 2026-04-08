---
title: Cron 调度与自动化工作流
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, cron, automation, scheduling]
sources: [hermes-agent 源码分析 2026-04-07]
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

## 相关页面

- [[messaging-gateway-architecture]] — 网关驱动调度器 tick() 循环
- [[hook-system-architecture]] — 网关事件钩子与 Cron 任务的协作
- [[gateway-session-management]] — 会话 origin 用于 Cron 投递路由

## 相关文件

- `tools/cronjob_tools.py` — Cron 工具
- `cron/scheduler.py` — 调度器
- `cron/jobs.py` — 任务定义
- `gateway/run.py` — 网关集成

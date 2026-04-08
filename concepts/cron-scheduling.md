---
title: Cron 调度与自动化工作流
created: 2026-04-07
updated: 2026-04-07
type: concept
tags: [architecture, cron, automation, scheduling]
sources: [raw/articles/code-analysis-2026-04-07.md]
---

# Cron 调度与自动化工作流

## 设计原理

Hermes 内置 Cron 调度器，支持**自然语言定时任务**，可以自动执行重复性工作并将结果推送到任意平台。

## Cron 工具

```python
# tools/cronjob_tools.py

def cronjob(
    action: str,           # create/list/update/pause/resume/remove/run
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
    elif action == "run":
        return _run_job(job_id)
```

## 调度器

```python
# cron/scheduler.py

class Scheduler:
    """Cron 调度器"""
    
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._running = False
    
    def add_job(self, job: Job):
        """添加任务"""
        self.jobs[job.id] = job
        self._save_jobs()
    
    def remove_job(self, job_id: str):
        """移除任务"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs()
    
    def run(self):
        """运行调度器"""
        self._running = True
        while self._running:
            now = datetime.now()
            for job in self.jobs.values():
                if job.should_run(now):
                    self._execute_job(job)
            time.sleep(60)  # 每分钟检查一次
    
    async def _execute_job(self, job: Job):
        """执行任务"""
        # 创建新的 Agent 实例
        agent = AIAgent(
            model=job.model,
            platform="cron",
            enabled_toolsets=job.toolsets,
        )
        
        # 执行任务
        result = agent.run_conversation(job.prompt)
        
        # 投递结果
        if job.deliver:
            await self._deliver_result(job.deliver, result)
```

## 调度表达式

```python
# cron/jobs.py

class Job:
    """定时任务"""
    
    def __init__(
        self,
        id: str,
        prompt: str,
        schedule: str,
        name: str = None,
        deliver: str = None,
        model: str = None,
        toolsets: list = None,
    ):
        self.id = id
        self.prompt = prompt
        self.schedule = schedule
        self.name = name or id
        self.deliver = deliver
        self.model = model
        self.toolsets = toolsets or ["terminal", "web", "file"]
        self.is_paused = False
        self.created_at = datetime.now()
        self.last_run = None
        self.next_run = self._parse_schedule(schedule)
    
    def _parse_schedule(self, schedule: str) -> datetime:
        """解析调度表达式"""
        # 支持格式：
        # - cron: "0 9 * * *" (每天 9 点)
        # - 相对: "30m", "every 2h", "daily"
        # - ISO: "2026-04-08T09:00:00"
        
        if schedule.startswith("0 ") or schedule.count(" ") == 4:
            # Cron 表达式
            from croniter import croniter
            return croniter(schedule, datetime.now()).get_next(datetime)
        
        elif schedule.startswith("every "):
            # 相对时间
            parts = schedule.split()
            amount = int(parts[1])
            unit = parts[2]
            
            if unit.startswith("m"):
                return datetime.now() + timedelta(minutes=amount)
            elif unit.startswith("h"):
                return datetime.now() + timedelta(hours=amount)
            elif unit.startswith("d"):
                return datetime.now() + timedelta(days=amount)
        
        else:
            # ISO 格式
            return datetime.fromisoformat(schedule)
    
    def should_run(self, now: datetime) -> bool:
        """判断是否应该运行"""
        if self.is_paused:
            return False
        return now >= self.next_run
```

## 投递目标

```python
# 投递目标
DELIVER_TARGETS = {
    "origin",     # 返回到原始聊天
    "local",      # 保存到本地文件
    "telegram",   # Telegram
    "discord",    # Discord
    "slack",      # Slack
    "whatsapp",   # WhatsApp
    "signal",     # Signal
    "email",      # Email
    "sms",        # SMS
    "webhook",    # Webhook
    # ... 更多平台
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

# 调度器作为 Gateway 的一部分运行
# 无需单独启动
```

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Claude Code | Cursor |
|------|--------|-------------|--------|
| 内置调度器 | ✅ | ❌ | ❌ |
| 自然语言调度 | ✅ | ❌ | ❌ |
| 多平台投递 | ✅ 10+ | ❌ | ❌ |
| Cron 表达式 | ✅ | ❌ | ❌ |
| 相对时间 | ✅ "30m", "every 2h" | ❌ | ❌ |
| 任务管理 | ✅ CLI/Gateway | ❌ | ❌ |

## 配置

```yaml
# ~/.hermes/config.yaml
cron:
  enabled: true
  timezone: "Asia/Shanghai"
  max_jobs: 50
  output_dir: "~/.hermes/cron/output"
```

## 相关文件

- `tools/cronjob_tools.py` — Cron 工具
- `cron/scheduler.py` — 调度器
- `cron/jobs.py` — 任务定义
- `gateway/run.py` — 网关集成

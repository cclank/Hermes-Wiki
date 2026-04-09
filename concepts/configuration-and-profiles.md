---
title: 配置管理与多 Profile 架构
created: 2026-04-07
updated: 2026-04-09
type: concept
tags: [architecture, configuration, profile, isolation]
sources: [hermes_cli/profiles.py, hermes_cli/config.py, hermes_cli/main.py, hermes_cli/gateway.py, hermes_constants.py, plugins/memory/honcho/cli.py, agent/prompt_builder.py]
---

# 配置管理与多 Profile 架构

## 概述

Hermes 通过**分层配置 + Profile 隔离**管理复杂的多维配置。Profile 是核心设计——每个 Profile 是一个完全独立的 `HERMES_HOME` 目录，拥有自己的配置、记忆、会话、技能、网关和定时任务。

## 配置层次

```text
优先级从低到高：
  1. 硬编码默认值         (hermes_cli/config.py DEFAULT_CONFIG)
  2. 用户配置文件         (~/.hermes/config.yaml)
  3. 环境变量             (.env 文件 + shell 环境变量)
  4. CLI 参数             (--model, --provider 等命令行参数)
  5. Profile 覆盖         (HERMES_HOME 环境变量指向不同目录)
```

## 配置文件结构

Hermes 有两套配置文件，职责不同：

| 文件 | 存什么 | 生效方式 |
|------|--------|---------|
| `.env` | API Keys、敏感凭证 | 环境变量注入 |
| `config.yaml` | 运行时行为配置 | `load_config()` 读取 |

```yaml
# ~/.hermes/config.yaml 核心配置项
model:
  default: "anthropic/claude-opus-4.6"
  provider: "auto"
  base_url: "https://openrouter.ai/api/v1"

terminal:
  backend: "local"
  cwd: "."
  timeout: 180

compression:
  enabled: true
  threshold: 0.50
  summary_model: "google/gemini-3-flash-preview"

memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
  nudge_interval: 10
  flush_min_turns: 6
```

## 多 Profile 架构

### 核心原理

所有 Hermes 模块通过 `get_hermes_home()` 解析路径：

```python
# hermes_constants.py — 全局唯一的路径来源
def get_hermes_home() -> Path:
    return Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
```

切换 Profile = 改变 `HERMES_HOME` 环境变量。代码库中 119+ 个文件调用 `get_hermes_home()`，Profile 切换时所有路径自动重定向，无需任何模块感知 Profile 的存在。

### 目录结构

```text
~/.hermes/                              ← "default" Profile（向后兼容）
  active_profile                        ← 粘性默认指针（存储 Profile 名称）
  config.yaml, .env, SOUL.md            ← default Profile 的配置
  memories/, sessions/, skills/          ← default Profile 的数据
  state.db                              ← default Profile 的数据库
  profiles/                             ← 命名 Profile 根目录
    coder/                              ← 命名 Profile（激活时成为 HERMES_HOME）
      config.yaml                       ← 独立的模型/终端/压缩配置
      .env                              ← 独立的 API Keys
      SOUL.md                           ← 独立的 Agent 身份定义
      memories/MEMORY.md, USER.md       ← 独立的持久记忆
      sessions/                         ← 独立的会话日志
      skills/                           ← 独立的技能集
      state.db                          ← 独立的 SQLite 数据库
      honcho.json                       ← 独立的 Honcho 配置
      logs/, cron/, skins/, plans/, workspace/
    ops/                                ← 另一个 Profile
      ...

~/.local/bin/
  coder   → #!/bin/sh\nexec hermes -p coder "$@"
  ops     → #!/bin/sh\nexec hermes -p ops "$@"
```

**每个 Profile 内部结构完全相同**，包含以下目录：`memories`、`sessions`、`skills`、`skins`、`logs`、`plans`、`workspace`、`cron`。

### Profile 激活流程

```text
hermes -p coder chat
       │
       ▼
_apply_profile_override()          ← main.py 模块级，在任何 import 之前执行
       │
       ├─ 解析 sys.argv 找 -p/--profile 参数
       ├─ 未找到 → 读 ~/.hermes/active_profile（粘性默认）
       │
       ▼
os.environ["HERMES_HOME"] = "~/.hermes/profiles/coder"
       │
       ▼
get_hermes_home() → 返回 Profile 目录
       │
       ▼
所有模块自动作用于 coder Profile
（config、memory、skills、gateway、session 全部隔离）
```

关键：`_apply_profile_override()` 在**模块级**执行，先于所有 `import`——因为很多模块在 import 时就缓存了 `HERMES_HOME`。

### CLI 命令

```bash
# 创建
hermes profile create coder              # 空白 Profile + 播种内置技能
hermes profile create coder --clone      # 克隆 config.yaml + .env + SOUL.md + 记忆
hermes profile create coder --clone-all  # 完整复制所有状态（去除运行时文件）
hermes profile create coder --no-alias   # 不生成 wrapper 快捷命令

# 使用
hermes -p coder chat                     # 指定 Profile 启动
coder chat                               # 通过 wrapper 快捷启动
hermes profile use coder                 # 设为粘性默认

# 管理
hermes profile list                      # 查看所有 Profile 状态
hermes profile show coder                # 详细信息（模型/网关/技能数）
hermes profile rename coder developer    # 重命名
hermes profile alias coder --name dev    # 自定义别名
hermes profile export coder              # 导出为 tar.gz
hermes profile import archive.tar.gz     # 导入
hermes profile delete coder              # 删除（需确认）
```

### Profile 命名规则

```text
正则：^[a-z0-9][a-z0-9_-]{0,63}$
  ✅ coder, ops-team, dev2, my_profile
  ❌ Coder（大写）, -ops（前缀连字符）, hermes（保留名）, chat（子命令冲突）
```

保留名：`hermes`、`default`、`test`、`tmp`、`root`、`sudo` + 所有 hermes 子命令名。

### 克隆行为

| 模式 | 复制内容 |
|------|---------|
| `--clone` | config.yaml、.env、SOUL.md、MEMORY.md、USER.md |
| `--clone-all` | 完整 copytree（去除 gateway.pid 等运行时文件） |
| 无参数 | 只创建目录结构 + 播种内置技能 |

记忆文件（MEMORY.md / USER.md）在 `--clone` 时一并复制，源码注释："Memory files are part of the agent's curated identity — just as important as SOUL.md for continuity."

### 导出/导入安全

**导出时排除敏感文件：**
- `.env`（API Keys）
- `auth.json`（OAuth tokens）
- `state.db`（可能含敏感对话）
- 各种缓存（image_cache、audio_cache、checkpoints）

**导入时安全检查：**
- 拒绝路径遍历攻击（`../`）
- 拒绝绝对路径（`/etc/passwd`）
- 拒绝 Windows 驱动器号（`C:\`）
- 拒绝符号链接
- 只允许普通文件和目录

## Profile 与子系统的联动

### Gateway 隔离

每个 Profile 可以独立运行自己的 Gateway（Telegram/Slack 等）：

```text
default Profile  → hermes-gateway          (服务名)
coder Profile    → hermes-gateway-coder    (服务名带后缀)
```

- PID 文件作用于各自 HERMES_HOME，互不冲突
- systemd/launchd 服务名自动带 Profile 后缀
- 如果两个 Profile 使用同一个 Bot Token，第二个 Gateway 会被拦截并报错

### Honcho 记忆隔离

每个 Profile 在 Honcho 中有独立的 host block：

```text
default → hermes          (host key)
coder   → hermes.coder    (host key 带后缀)
```

AI Peer 按 Profile 隔离（独立的用户建模），但 workspace 共享（所有 Profile 看到同一个用户的观察数据）。

创建新 Profile 时自动克隆 Honcho 配置；`hermes update` 时自动同步所有 Profile 的 Honcho host blocks。

### SOUL.md 身份

每个 Profile 有自己的 `SOUL.md`，定义 Agent 的身份和行为规范。`prompt_builder.py` 通过 `get_hermes_home() / "SOUL.md"` 加载，Profile 切换后自动指向对应文件。

### 技能同步

`hermes update` 会自动将内置技能同步到**所有** Profile：

```text
hermes update
  → 更新当前 Profile 技能
  → 扫描所有其他 Profile
  → 对每个 Profile 执行 seed_profile_skills()
  → 用户自定义的技能不会被覆盖
```

技能播种通过**子进程**执行（不是 in-process），因为 `sync_skills()` 在模块级缓存了 HERMES_HOME。

### Banner 和 Prompt

- 启动 Banner 显示当前 Profile 名称（非 default 时）
- CLI 输入提示符带 Profile 前缀：`coder >` 而不是 `>`
- Gateway 支持 `/profile` 命令查看当前 Profile

## 典型使用场景

```bash
# 场景：按职能隔离
hermes profile create coder --clone       # 日常开发
hermes profile create ops --clone         # 运维操作
hermes profile create research --clone    # 研究调研

# 分别配置不同的安全边界
hermes -p coder config set terminal.backend local
hermes -p ops config set terminal.backend docker
hermes -p research config set terminal.backend ssh

# 分别配置不同的模型
hermes -p coder config set model.default "anthropic/claude-opus-4.6"
hermes -p research config set model.default "google/gemini-2.5-pro"

# 分别运行各自的 Gateway
hermes -p coder telegram &
hermes -p ops telegram &
```

## 与 Multi-Agent 的关系

多 Profile 可以视为 Hermes 的**第二种多 Agent 方案**。会话内的 multi-agent（delegate_task）适合"一个任务内的并行分工"，多 Profile 适合"不同职能角色的长期隔离"。两者互补：

- delegate_task 子 agent **继承父 agent 的 terminal backend**，无法按任务切换隔离级别
- 多 Profile 可以为每个角色**独立配置 backend**（coder 用 local，ops 用 docker）
- 代价是多 Profile 之间没有自动协作，需要用户手动切换

详见 → [[multi-agent-architecture]]

## 相关页面

- [[multi-agent-architecture]] — 会话内多 Agent（delegate_task / MoA / Background Review）
- [[terminal-backends]] — 终端后端选择（Profile 可为每个角色配置不同后端）
- [[memory-system-architecture]] — 记忆系统（每个 Profile 独立的 MEMORY.md / USER.md）
- [[skills-system-architecture]] — 技能系统（每个 Profile 独立的技能集）
- [[credential-pool-and-isolation]] — 凭证隔离
- [[hook-system-architecture]] — Hook 系统（Gateway Hooks 按 Profile 隔离）

## 关键源码

| 文件 | 职责 |
|------|------|
| `hermes_constants.py` | `get_hermes_home()` — 全局路径来源 |
| `hermes_cli/profiles.py` | Profile CRUD、导出导入、别名管理 |
| `hermes_cli/main.py` | `_apply_profile_override()` — 启动时 Profile 激活 |
| `hermes_cli/config.py` | `load_config()` — 读取 Profile 作用域的 config.yaml |
| `hermes_cli/gateway.py` | Gateway 服务名后缀、PID 隔离 |
| `plugins/memory/honcho/cli.py` | Honcho host block 按 Profile 隔离 |
| `agent/prompt_builder.py` | SOUL.md 按 Profile 加载 |

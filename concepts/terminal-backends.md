---
title: 终端后端与环境抽象层
created: 2026-04-07
updated: 2026-05-31
type: concept
tags: [architecture, environments, terminal, isolation, cwd-persistence, spawn-via-env]
sources: [tools/environments/, tools/terminal_tool.py, tools/process_registry.py]
---

# 终端后端与环境抽象层

## 设计原理

Hermes 支持 7 种终端后端，提供不同级别的隔离和持久化。统一的 `terminal` 工具抽象使 Agent 可以在不同后端间无缝切换。

## v0.14.0+ 性能改进

- **自适应 subprocess poll（post-v0.14.0，PR #29006）**：原 `_run_bash` 用固定 poll 间隔等子进程退出，长 tail 上累积浪费时间。改自适应后**每次工具调用平均减 ~195ms**。
- **Termux TUI 冷启动加速（post-v0.14.0）**：手机端 hermes 启动从 X 秒减到 Y 秒（具体见 commit `c29b4f55d`）。
- **Windows `creationflags` 冲突修复（post-v0.14.0）**：`_run_bash` 用 `windows_hide_flags` 与既有 kwargs 撞名时不再 throw（`hermes_cli/_subprocess_compat.py`）。

## 后端类型

| 后端 | 隔离级别 | 持久化 | 适用场景 |
|------|----------|--------|----------|
| **Local** | 无 | ✅ 本地磁盘 | 开发、个人使用 |
| **Docker** | 容器 | ✅ 卷挂载 | 测试、CI/CD |
| **SSH** | 远程主机 | ✅ 远程磁盘 | 远程服务器 |
| **Modal** | 无服务器 | ✅ 快照 | 云端执行、按需启动 |
| **Daytona** | 沙箱 | ✅ 持久化沙箱 | 安全执行 |
| **Singularity** | 容器 | ✅ 卷挂载 | HPC、科研 |
| **Vercel Sandbox** | microVM | ✅ 快照（按 task_id） | 云端 microVM，FileSyncManager 凭证/技能同步（v2026.4.23+） |

### Docker 容器以宿主用户运行（v2026.4.23+）

`feat(docker): run container as host user` 让容器内进程使用宿主机的 UID/GID 启动，避免 bind mount 出来的文件变成 root 所有，需要 sudo 才能清理。

### docker_extra_args（2026-05-15）

`terminal.docker_extra_args` 是一个可选配置项（默认关闭），其中的额外参数会**逐字追加**到 `docker run` 命令的安全默认项之后，用于添加未被现有配置键暴露的能力（如 `--cap-add SETUID`）。非字符串条目会被记录并跳过。也可通过 `TERMINAL_DOCKER_EXTRA_ARGS='[...]'` 环境变量设置。

## 终端工具

```python
# tools/terminal_tool.py

def terminal(
    command: str,
    background: bool = False,
    timeout: int = 180,
    workdir: str = None,
    pty: bool = False,
) -> dict:
    """执行终端命令"""
    
    # 解析后端类型
    backend = os.getenv("TERMINAL_ENV", "local")
    
    # 分发到对应后端
    if backend == "local":
        return _run_local(command, timeout, workdir)
    elif backend == "docker":
        return _run_docker(command, timeout, workdir)
    elif backend == "ssh":
        return _run_ssh(command, timeout, workdir)
    elif backend == "modal":
        return _run_modal(command, timeout, workdir)
    elif backend == "daytona":
        return _run_daytona(command, timeout, workdir)
    elif backend == "singularity":
        return _run_singularity(command, timeout, workdir)
```

## 统一执行模型：Spawn-per-call

所有 7 种后端共享同一个执行模型——**每次命令独立 spawn `bash -c` 进程**，通过 session snapshot 保持环境一致性：

```text
初始化时:
  login shell → 捕获 session snapshot（env vars、functions、aliases）

每次命令执行:
  spawn bash -c → source snapshot → 执行命令 → 捕获 CWD → 退出
```

**BaseEnvironment**（`tools/environments/base.py`）定义统一接口：

- `init_session()` — 启动一次 login shell，捕获环境快照
- `_wrap_command(cmd)` — 注入 snapshot source + CWD 追踪标记
- `execute(cmd)` — 统一入口：wrap → spawn → 等待 → 返回 `{output, returncode}`
- `_run_bash(wrapped_cmd)` → 抽象方法，各后端实现具体的进程创建

**CWD 跨调用持久化**通过输出标记实现：
- 本地后端：临时文件
- 远程后端（Docker/SSH/Modal）：stdout 内嵌标记

> 注：旧版的 `PersistentShellMixin`（`persistent_shell.py`）已在 2026-04-09 删除，被 spawn-per-call + session snapshot 完全替代。

## 环境上下文

```python
# environments/tool_context.py

class ToolContext:
    """工具执行上下文"""
    
    def __init__(self, environment: BaseEnvironment):
        self.environment = environment
        self.working_directory = "/root"
        self.env_vars = {}
    
    async def run_command(self, command: str, **kwargs) -> dict:
        return await self.environment.run_command(
            command,
            workdir=self.working_directory,
            env=self.env_vars,
            **kwargs
        )
```

## 统一文件同步（file_sync.py，2026-04-10）

SSH/Modal/Daytona 后端使用 `tools/environments/file_sync.py` 在本机和远程环境之间同步文件（凭证、技能、缓存等）。Docker/Singularity 用 bind mount 不需要。

- **变更检测**：基于 mtime + 文件大小，只上传有变化的文件
- **删除检测**：本地文件被删除后，远程对应文件也被清理
- **事务回滚**：上传/删除任一步失败，回滚到上次状态，下次重试
- **速率限制**：默认 5 秒同步一次（`HERMES_FORCE_FILE_SYNC=1` 强制每次同步）

## 后台进程监控（watch_patterns，2026-04-10）

`terminal` 工具新增 `watch_patterns` 参数，后台进程输出匹配指定字符串时实时通知 agent：

```python
terminal(command="pytest -v", background=True, watch_patterns=["ERROR", "FAIL", "listening on port"])
```

| 参数 | 值 |
|------|-----|
| 匹配方式 | 子串匹配（非正则） |
| 速率限制 | 10 秒窗口最多 8 次通知 |
| 过载保护 | 持续超载 45 秒自动禁用 |
| 输出截断 | 最多 20 行、2000 字符 |

通知通过 `ProcessRegistry.completion_queue` 传递给 CLI/Gateway 的主循环，触发 agent 自动响应。

### `background=true` 静默运行警告（2026-05-23，`d97c324`，#31289）

`tools/terminal_tool.py:1962-1990`：`background=true` 没配 `notify_on_complete=true` **也**没配 `watch_patterns` 时，tool result 内嵌 `hint` 字段告诉 agent："this process runs SILENTLY"。

```text
background=true without notify_on_complete=true means this process runs
SILENTLY — you will not be told when it exits. If this is a bounded task
(test suite, build, CI poller, deploy, anything with a defined end), you
almost certainly wanted notify_on_complete=true so the system pings you
on exit. Re-launch with notify_on_complete=true, or call
process(action='poll') / process(action='wait') yourself to learn the
outcome. Only ignore this hint for genuine long-lived processes that
never exit (servers, watchers, daemons).
```

背景：2026-05 PR #31231 incident —— bg CI poller 跑完，agent 没注意到，用户手动 surface 结果。该 hint 对 bounded task 是必需提醒（false negative 比 false positive 严重）；对 server/watcher 是 false positive，agent 应忽略。

## Windows 进程树终止（2026-05-23，`7ce6b50`）

`tools/process_registry.py:436-475 _terminate_host_pid` —— Windows 分支改用 `taskkill /PID <pid> /T /F`（之前 `os.kill(pid, SIGTERM)` → `TerminateProcess`，**只**杀目标 handle，Chromium renderer / GPU / network helper 子进程残留）。POSIX 分支与 `taskkill.exe` 缺失时回退到 `os.kill` 链。

配套（`22f3f5a`）：`tools/browser_tool.py:9` Browser daemon cleanup 改用 `ProcessRegistry._terminate_host_pid()`（psutil 叶到根遍历），不再 orphan Chromium 子进程。

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | Claude Code |
|------|--------|--------|-------------|
| 后端数量 | ✅ 7 种 | ❌ 1 | ❌ 1 |
| 无服务器支持 | ✅ Modal | ❌ | ❌ |
| 沙箱隔离 | ✅ Daytona | ❌ | ❌ |
| HPC 支持 | ✅ Singularity | ❌ | ❌ |
| Session Snapshot | ✅ | ❌ | ❌ |
| 环境快照 | ✅ Modal | ❌ | ❌ |

## 配置文件

```yaml
# ~/.hermes/config.yaml
terminal:
  backend: "local"  # local/docker/ssh/modal/daytona/singularity/vercel_sandbox
  
  docker:
    image: "ubuntu:22.04"
    volumes: ["~/work:/root/work"]
  
  ssh:
    host: "remote-server"
    user: "ubuntu"
    key_path: "~/.ssh/id_rsa"
  
  modal:
    app_name: "hermes-agent"
    image: "python:3.11"
  
  daytona:
    api_key: "${DAYTONA_API_KEY}"
    image: "ubuntu:22.04"
```

## Lazy-Install 终端后端（v0.14.0+）

`tools/lazy_deps.py`（613 行）列出 `terminal.modal` / `terminal.daytona` / `terminal.vercel` 等 entry：**只在第一次使用时**才装 SDK。`pip install hermes-agent` 默认仅含 local + docker + singularity，云端后端按需 lazy install。`pyproject.toml:174-207` 的 `[all]` extras 也对应 drop 掉这些已 lazy 覆盖的依赖。

效果：
- **更轻安装** —— 不用 cloud terminal 的用户不下载 Modal/Daytona/Vercel SDK
- **更少传递漏洞面** —— 攻击面随实际使用而扩展，不一次性全暴露

## 相关页面

- [[credential-pool-and-isolation]] — 凭证池与环境隔离（终端后端环境）
- [[multi-agent-architecture]] — 子代理使用独立终端后端执行
- [[tool-registry-architecture]] — 终端工具通过 registry 注册

## 2026-05-31 增量 — cwd 持久化 + spawn_via_env 防双包裹

### 1. 终端 cwd 持久化（`7a315bd70`）

`fix(tools): preserve live session cwd in terminal_tool, and keep ACP update_cwd authoritative`：

**问题**：`terminal_tool` 每次 command **强制**重发 init-time / config cwd，覆盖了会话内 `cd` 的累积状态。环境侧 `env.cwd` 已经更新到新目录，但每次 foreground / background call 又被踩回旧值。

**修**：`tools/terminal_tool.py:1738 _resolve_command_cwd(env, explicit_cwd, init_cwd)` 加 resolver，按以下优先级：

1. **ACP-explicit `update_cwd`**（最高优先；ACP 协议显式告知 cwd 时不能被其他源覆盖）
2. **live `env.cwd`**（会话累积状态，含 agent 自己 `cd ...` 的结果）
3. **`init_cwd`** / config cwd（fallback）

调用点：

- `tools/terminal_tool.py:2034` foreground execute
- `tools/terminal_tool.py:2255` background spawn（`cwd` field of `process_registry.spawn_via_env(...)`）

### 2. spawn_via_env 防双 compound-rewrite 包裹（`6f8975dcd`）

`fix(tools): don't compound-rewrite spawn_via_env background wrappers`：

**问题**：

- 非 local backend（SSH / Docker / Modal / Daytona / Singularity）的 background task 经 `tools/process_registry.py:651 spawn_via_env`，后者构建**手工 shell-safe wrapper**（已含 `nohup` / `&` / `disown` / output redirection / `setsid` 适配 backend）。
- `tools/environments/base.py:843` execute 路径默认还会过 `_rewrite_compound_background`（防 `A && B &` subshell-wait 陷阱），把已经构造好的 wrapper **当用户裸命令二次重写** —— 破坏正确语义（如 `nohup` 不再 detach、`disown` 失败）。

**修**（`tools/environments/base.py:843-846`）：

```python
# Some callers (spawn_via_env) already produce shell-safe wrappers and
# pass rewrite_compound_background=False.
if rewrite_compound_background:
    from tools.terminal_tool import _rewrite_compound_background
    exec_command = _rewrite_compound_background(exec_command)
```

`spawn_via_env` 调用 execute 时传 `rewrite_compound_background=False`，跳过二次 rewrite。

---

## 相关文件

- `tools/terminal_tool.py` — 终端工具
- `tools/environments/` — 7 种后端实现（含 vercel_sandbox.py）
- `tools/lazy_deps.py` — Lazy 安装清单（v0.14.0+，line 77-173 含 terminal.modal/daytona/vercel）
- `environments/tool_context.py` — 工具执行上下文

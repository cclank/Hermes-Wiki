---
title: 终端后端与环境抽象层
created: 2026-04-07
updated: 2026-04-09
type: concept
tags: [architecture, environments, terminal, isolation]
sources: [hermes-agent 源码分析 2026-04-07]
---

# 终端后端与环境抽象层

## 设计原理

Hermes 支持 6 种终端后端，提供不同级别的隔离和持久化。统一的 `terminal` 工具抽象使 Agent 可以在不同后端间无缝切换。

## 后端类型

| 后端 | 隔离级别 | 持久化 | 适用场景 |
|------|----------|--------|----------|
| **Local** | 无 | ✅ 本地磁盘 | 开发、个人使用 |
| **Docker** | 容器 | ✅ 卷挂载 | 测试、CI/CD |
| **SSH** | 远程主机 | ✅ 远程磁盘 | 远程服务器 |
| **Modal** | 无服务器 | ✅ 快照 | 云端执行、按需启动 |
| **Daytona** | 沙箱 | ✅ 持久化沙箱 | 安全执行 |
| **Singularity** | 容器 | ✅ 卷挂载 | HPC、科研 |

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

所有 6 种后端共享同一个执行模型——**每次命令独立 spawn `bash -c` 进程**，通过 session snapshot 保持环境一致性：

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

## 优越性分析

### 与其他 Agent 框架对比

| 特性 | Hermes | Cursor | Claude Code |
|------|--------|--------|-------------|
| 后端数量 | ✅ 6 种 | ❌ 1 | ❌ 1 |
| 无服务器支持 | ✅ Modal | ❌ | ❌ |
| 沙箱隔离 | ✅ Daytona | ❌ | ❌ |
| HPC 支持 | ✅ Singularity | ❌ | ❌ |
| Session Snapshot | ✅ | ❌ | ❌ |
| 环境快照 | ✅ Modal | ❌ | ❌ |

## 配置文件

```yaml
# ~/.hermes/config.yaml
terminal:
  backend: "local"  # local/docker/ssh/modal/daytona/singularity
  
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

## 相关页面

- [[credential-pool-and-isolation]] — 凭证池与环境隔离（终端后端环境）
- [[multi-agent-architecture]] — 子代理使用独立终端后端执行
- [[tool-registry-architecture]] — 终端工具通过 registry 注册

## 相关文件

- `tools/terminal_tool.py` — 终端工具
- `tools/environments/` — 6 种后端实现
- `environments/tool_context.py` — 工具执行上下文

---
title: 终端后端与环境抽象层
created: 2026-04-07
updated: 2026-04-07
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

## 后端基类

```python
# tools/environments/base.py

class BaseEnvironment:
    """终端后端基类（同步方法，非异步）"""
    
    def __init__(self, cwd: str, timeout: int, env: dict = None):
        self.cwd = cwd
        self.timeout = timeout
        self.env = env or {}
    
    def execute(
        self,
        command: str,
        cwd: str = None,
        timeout: int = None,
        stdin_data: str = None,
    ) -> dict:
        """执行命令，返回 {"output": str, "returncode": int}"""
        raise NotImplementedError
    
    def cleanup(self):
        """清理环境资源"""
        raise NotImplementedError
```

## Modal 后端

```python
# tools/environments/modal.py

class ModalEnvironment(BaseEnvironment):
    """Modal 无服务器环境"""
    
    async def start(self):
        import modal
        
        # 创建或获取沙箱
        self.sandbox = modal.Sandbox.create(
            "bash", "-c", "sleep infinity",
            app=self.app,
        )
    
    async def run_command(self, command: str, timeout: int = 180) -> dict:
        process = self.sandbox.exec("bash", "-c", command)
        output = process.stdout.read()
        exit_code = process.wait()
        
        return {
            "output": output,
            "exit_code": exit_code,
        }
    
    async def snapshot(self):
        """创建快照用于持久化"""
        # Modal 支持沙箱快照
        pass
```

## Daytona 后端

```python
# tools/environments/daytona.py

class DaytonaEnvironment(BaseEnvironment):
    """Daytona 沙箱环境"""
    
    async def start(self):
        from daytona import Daytona
        
        self.client = Daytona(api_key=self.config.get("api_key"))
        self.sandbox = self.client.create(
            image=self.config.get("image", "ubuntu:22.04"),
        )
    
    async def run_command(self, command: str, timeout: int = 180) -> dict:
        result = self.sandbox.process.execute(command, timeout=timeout)
        return {
            "output": result.output,
            "exit_code": result.exit_code,
        }
```

## 持久化 Shell

```python
# tools/environments/persistent_shell.py

class PersistentShellMixin:
    """持久化 Shell Mixin（基于文件 IPC 的进程间通信）
    
    不是独立类，而是作为 mixin 混入具体后端实现。
    使用临时文件进行命令输入/输出的 IPC，而非 async stdin/stdout 流。
    """
    
    def _start_persistent_shell(self):
        """启动持久化 shell 进程，使用临时文件进行 IPC"""
        import tempfile
        self._cmd_file = tempfile.NamedTemporaryFile(delete=False, suffix=".cmd")
        self._out_file = tempfile.NamedTemporaryFile(delete=False, suffix=".out")
        # 通过文件系统传递命令和读取输出
    
    def _send_command_via_file(self, command: str) -> str:
        """通过临时文件发送命令并读取输出"""
        # 写入命令到 cmd 文件
        # 等待 out 文件产生输出
        # 返回输出内容
        pass
```

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
| 持久化 Shell | ✅ | ❌ | ❌ |
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
